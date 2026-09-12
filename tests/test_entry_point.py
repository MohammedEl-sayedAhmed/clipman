import os
import re
import subprocess
import sys
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


def _run(*args):
    """Run the entry point in a subprocess with no display."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
    env["GDK_BACKEND"] = "x11"
    env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/nonexistent/clipman-test"
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
