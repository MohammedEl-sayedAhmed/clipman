import os
import re
import subprocess
import sys
import tempfile
import unittest
from importlib import import_module, resources
from pathlib import Path

from clipman._version import __version__

ROOT = Path(__file__).resolve().parent.parent
CLI_SOURCE = (ROOT / "clipman" / "cli.py").read_text()
# Text, not tomllib: that module only exists from Python 3.11.
PYPROJECT = (ROOT / "pyproject.toml").read_text()
# Everything from ``def main(`` to the end of the module.
MAIN_BODY = CLI_SOURCE[CLI_SOURCE.index("def main("):]


def _run(*args, home=None, path_first=None):
    """Run the entry point in a subprocess with no display, bus or real home.

    With wl-paste installed, `toggle` finds no daemon and starts one, and
    the daemon opens its database under HOME. So the run gets a scratch
    HOME (``home``, or a temporary one).
    """
    env = {k: v for k, v in os.environ.items()
           if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
    env["GDK_BACKEND"] = "x11"
    env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/nonexistent/clipman-test"
    env["GSETTINGS_BACKEND"] = "memory"
    if path_first:
        env["PATH"] = f"{path_first}{os.pathsep}{env.get('PATH', '')}"
    with tempfile.TemporaryDirectory(prefix="clipman-entry-") as scratch:
        env["HOME"] = str(home or scratch)
        for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
            env[name] = os.path.join(env["HOME"], name[4:-5].lower())
        return subprocess.run(
            [sys.executable, *args], capture_output=True, timeout=10,
            cwd=ROOT, env=env,
        )


class TestDBusMainLoopInit(unittest.TestCase):
    """The GLib main loop must be the default before any bus connection.

    A toggle client that connected first without it handed the daemon a
    connection that never dispatched method calls.
    """

    def test_mainloop_set_before_toggle_or_daemon_start(self):
        setup = MAIN_BODY.find("DBusGMainLoop(set_as_default=True)")
        self.assertNotEqual(setup, -1)
        for call in ("_toggle()", "_start_daemon()"):
            self.assertLess(setup, MAIN_BODY.index(call), call)

    def test_dependency_check_runs_before_mainloop_setup(self):
        check = MAIN_BODY.find("_check_dependencies()")
        self.assertNotEqual(check, -1)
        self.assertLess(check, MAIN_BODY.index("DBusGMainLoop"))

    def test_toggle_without_daemon_does_not_hang(self):
        """'clipman.py toggle' must exit quickly with no daemon."""
        # Without a display or a bus the toggle falls through to the
        # daemon start, which must fail fast rather than run the loop.
        result = _run("clipman.py", "toggle")
        output = result.stdout + result.stderr
        expected = (b"not running", b"missing system dependencies")
        self.assertTrue(any(m in output for m in expected), output[-500:])

    def test_toggle_daemon_start_stays_in_the_scratch_home(self):
        """The daemon start behind 'toggle' must not open the real database.

        A fake wl-paste passes the dependency check, so the daemon start
        runs and creates clipman.db. It must land in the run's own HOME.
        """
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            for tool in ("wl-paste", "wl-copy"):
                stub = bin_dir / tool
                stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                stub.chmod(0o700)
            home = Path(tmp) / "home"
            home.mkdir()
            result = _run("clipman.py", "toggle", home=home, path_first=bin_dir)
            output = result.stdout + result.stderr
            self.assertIn(b"Starting it now", output, output[-500:])
            self.assertTrue((home / ".local/share/clipman/clipman.db").exists())


class TestDependencyCheck(unittest.TestCase):
    """The entry point names the system packages it needs."""

    def test_covers_gi(self):
        self.assertIn('import_module("gi")', CLI_SOURCE)
        self.assertIn("python3-gi", CLI_SOURCE)

    def test_covers_dbus(self):
        self.assertIn('import_module("dbus")', CLI_SOURCE)
        self.assertIn("python3-dbus", CLI_SOURCE)

    def test_covers_wl_clipboard(self):
        self.assertIn("wl-paste", CLI_SOURCE)
        self.assertIn("wl-clipboard", CLI_SOURCE)


class TestEntryPoints(unittest.TestCase):
    """What pip installs must resolve and ship its data file."""

    def test_console_script_target_resolves(self):
        match = re.search(r'^clipman = "([\w.]+):(\w+)"$', PYPROJECT, re.M)
        self.assertIsNotNone(match, "no clipman console script in pyproject")
        module, attr = match.groups()
        self.assertTrue(callable(getattr(import_module(module), attr)))

    def test_style_css_is_package_data(self):
        section = PYPROJECT[PYPROJECT.index("[tool.setuptools.package-data]"):]
        self.assertRegex(section.split("\n[", 1)[0], r'clipman = \[.*"style.css"')
        self.assertTrue(resources.files("clipman").joinpath("style.css").is_file())

    def test_shim_and_module_report_version(self):
        for args in (("clipman.py", "--version"), ("-m", "clipman", "--version")):
            result = _run(*args)
            self.assertEqual(result.returncode, 0, result.stderr[-500:])
            self.assertEqual(result.stdout.strip(), f"clipman {__version__}".encode())
