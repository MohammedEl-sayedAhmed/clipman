import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from importlib import import_module, resources
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from clipman import cli
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

    @staticmethod
    def _fake_wl_clipboard(tmp):
        """A bin folder whose wl-paste and wl-copy pass the dependency
        check, so the daemon start runs."""
        bin_dir = Path(tmp) / "bin"
        bin_dir.mkdir()
        for tool in ("wl-paste", "wl-copy"):
            stub = bin_dir / tool
            stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            stub.chmod(0o700)
        return bin_dir

    def test_toggle_daemon_start_stays_in_the_scratch_home(self):
        """The daemon start behind 'toggle' must not open the real database.

        The daemon start runs and creates clipman.db. It must land in the
        run's own HOME.
        """
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = self._fake_wl_clipboard(tmp)
            home = Path(tmp) / "home"
            home.mkdir()
            result = _run("clipman.py", "toggle", home=home, path_first=bin_dir)
            output = result.stdout + result.stderr
            self.assertIn(b"Starting it now", output, output[-500:])
            self.assertTrue((home / ".local/share/clipman/clipman.db").exists())

    def test_daemon_that_cannot_start_exits_non_zero(self):
        """With no display GTK cannot start. The daemon used to exit 0
        then, so systemd's Restart=on-failure never tried again."""
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = self._fake_wl_clipboard(tmp)
            for args in (("clipman.py",), ("-m", "clipman")):
                with self.subTest(args=args):
                    result = _run(*args, path_first=bin_dir)
                    self.assertNotEqual(result.returncode, 0,
                                        result.stderr[-500:])
                    self.assertIn(b"Clipman could not start", result.stderr)


def _fake_app_module(run_status=0, exit_status=0, runs=None):
    """A stand-in for clipman.app whose ClipmanApp only records its runs:
    ``runs`` gets the app's show_on_start flag for each one."""
    class FakeApp:
        def __init__(self):
            self.exit_status = exit_status
            self.show_on_start = False

        def run(self, _argv):
            if runs is not None:
                runs.append(self.show_on_start)
            return run_status

    return SimpleNamespace(ClipmanApp=FakeApp)


class TestExitStatus(unittest.TestCase):
    """The daemon's exit status reaches the process exit status."""

    def _start_daemon(self, run_status, exit_status):
        fake = _fake_app_module(run_status, exit_status)
        with patch.dict(sys.modules, {"clipman.app": fake}):
            return cli._start_daemon()

    def test_failed_start_up_is_returned(self):
        self.assertEqual(self._start_daemon(0, 1), 1)

    def test_run_status_wins(self):
        self.assertEqual(self._start_daemon(2, 0), 2)

    def test_clean_exit_is_zero(self):
        self.assertEqual(self._start_daemon(0, 0), 0)

    def test_launchers_exit_with_it(self):
        for launcher in ("clipman.py", "clipman/__main__.py"):
            with self.subTest(launcher=launcher):
                source = (ROOT / launcher).read_text(encoding="utf-8")
                self.assertIn("sys.exit(main())", source)


class TestToggle(unittest.TestCase):
    """`clipman toggle` shows the popup even when no daemon runs yet."""

    def test_no_daemon_starts_one_that_shows_the_popup(self):
        """CORE-13: the first toggle started the daemon but showed
        nothing, so the shortcut had to be pressed again."""
        import dbus

        runs = []
        error = dbus.exceptions.DBusException("no daemon")
        with patch("dbus.SessionBus", side_effect=error), \
             patch.dict(sys.modules, {"clipman.app": _fake_app_module(runs=runs)}), \
             contextlib.redirect_stdout(io.StringIO()):
            status = cli._toggle()
        self.assertEqual(status, 0)
        self.assertEqual(runs, [True])

    def test_plain_start_keeps_the_popup_hidden(self):
        runs = []
        with patch.dict(sys.modules, {"clipman.app": _fake_app_module(runs=runs)}):
            cli._start_daemon()
        self.assertEqual(runs, [False])


class TestDependencyCheck(unittest.TestCase):
    """The entry point names what is missing and how to install it
    (audit finding CORE-12)."""

    # The program each package manager is found by.
    PROGRAMS = {"apt": "apt-get", "dnf": "dnf", "pacman": "pacman"}

    def _check(self, missing=(), manager="apt", isolated=False):
        """Run the check with ``missing`` pieces ("gi", "dbus",
        "wl-clipboard") taken away. Return what it wrote to stderr when
        it exited, or None when it passed."""
        present = self.PROGRAMS.get(manager)

        def which(program):
            if program == "wl-paste":
                return None if "wl-clipboard" in missing else "/usr/bin/wl-paste"
            return f"/usr/bin/{program}" if program == present else None

        # None in sys.modules makes an import raise ImportError.
        blocked = {name: None for name in ("gi", "dbus") if name in missing}
        stderr = io.StringIO()
        with patch.dict(sys.modules, blocked), \
             patch("clipman.cli.shutil.which", side_effect=which), \
             patch("clipman.cli._isolated_venv", return_value=isolated), \
             contextlib.redirect_stderr(stderr):
            try:
                cli._check_dependencies()
            except SystemExit as exc:
                self.assertEqual(exc.code, 1)
                return stderr.getvalue()
        return None

    def test_passes_when_nothing_is_missing(self):
        self.assertIsNone(self._check())

    def test_names_each_missing_piece(self):
        written = self._check(missing=("gi", "dbus", "wl-clipboard"))
        self.assertIn("Error: missing system dependencies: PyGObject, "
                      "GTK 4 and libadwaita, dbus-python, wl-clipboard",
                      written)

    def test_install_command_fits_the_package_manager(self):
        """The hint was always apt, even on Fedora or Arch."""
        installs = {
            "apt": ("sudo apt install",
                    "python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-dbus"),
            "dnf": ("sudo dnf install",
                    "python3-gobject gtk4 libadwaita python3-dbus"),
            "pacman": ("sudo pacman -S",
                       "python-gobject gtk4 libadwaita python-dbus"),
        }
        for manager, (command, packages) in installs.items():
            with self.subTest(manager=manager):
                written = self._check(("gi", "dbus", "wl-clipboard"), manager)
                self.assertIn(f"  {command} {packages} wl-clipboard\n", written)

    def test_names_only_what_is_missing(self):
        written = self._check(missing=("wl-clipboard",))
        self.assertIn("  sudo apt install wl-clipboard\n", written)
        self.assertNotIn("python3-gi", written)

    def test_unknown_package_manager_gets_a_general_hint(self):
        written = self._check(missing=("dbus",), manager=None)
        self.assertIn("Install them with your package manager.", written)
        self.assertNotIn("sudo", written)

    def test_isolated_venv_gets_the_pipx_hint(self):
        """PyGObject and dbus-python come from the system, so a venv that
        cannot see it misses them even when they are installed."""
        pipx = "pipx install --system-site-packages clipman-clipboard"
        written = self._check(missing=("gi",), isolated=True)
        self.assertIn(pipx, written)
        self.assertIn("sudo apt install python3-gi", written)
        # wl-clipboard alone is not a venv problem.
        written = self._check(missing=("wl-clipboard",), isolated=True)
        self.assertNotIn(pipx, written)


class TestIsolatedVenv(unittest.TestCase):
    """Whether this Python environment can see the system's packages."""

    def _isolated(self, cfg):
        """Run the check in a fake venv whose pyvenv.cfg holds ``cfg``
        (None: no such file)."""
        with tempfile.TemporaryDirectory() as prefix:
            if cfg is not None:
                Path(prefix, "pyvenv.cfg").write_text(cfg, encoding="utf-8")
            with patch.object(sys, "prefix", prefix), \
                 patch.object(sys, "base_prefix", "/usr"):
                return cli._isolated_venv()

    def test_venv_without_system_packages(self):
        self.assertTrue(self._isolated("include-system-site-packages = false\n"))

    def test_venv_with_system_packages(self):
        self.assertFalse(self._isolated("home = /usr/bin\n"
                                        "include-system-site-packages = true\n"))

    def test_setting_left_out_means_system_packages(self):
        # Python's site module defaults it to true.
        self.assertFalse(self._isolated("home = /usr/bin\n"))
        self.assertFalse(self._isolated(None))

    def test_no_venv(self):
        with patch.object(sys, "base_prefix", sys.prefix):
            self.assertFalse(cli._isolated_venv())


class TestLibadwaitaPreflight(unittest.TestCase):
    """The start-up check refuses a libadwaita the app cannot run on.

    Preferences and the snippets editor subclass Adw.Dialog at import
    time, and Adw.AlertDialog is used too; both arrived in 1.5.
    """

    def _preflight(self, minor):
        try:
            import gi.repository
        except ImportError as exc:
            raise unittest.SkipTest("PyGObject is not installed") from exc
        fake = SimpleNamespace(MAJOR_VERSION=1, MINOR_VERSION=minor, MICRO_VERSION=0)
        with patch("gi.require_version"), \
                patch.object(gi.repository, "Adw", fake, create=True), \
                patch.dict(sys.modules, {"gi.repository.Adw": fake}):
            cli._preflight_libadwaita()

    def test_refuses_libadwaita_1_4(self):
        with self.assertRaises(SystemExit), patch("sys.stderr") as stderr:
            self._preflight(4)
        written = "".join(call.args[0] for call in stderr.write.call_args_list)
        self.assertIn(">= 1.5", written)

    def test_accepts_libadwaita_1_5(self):
        self._preflight(5)

    def test_missing_gtk_or_libadwaita_gets_a_readable_error(self):
        """CORE-12: without the typelib, require_version raised a
        ValueError, and the user saw a traceback."""
        try:
            import gi
        except ImportError as exc:
            raise unittest.SkipTest("PyGObject is not installed") from exc
        stderr = io.StringIO()
        error = ValueError("Namespace Adw not available")
        with patch.object(gi, "require_version", side_effect=error), \
             patch("clipman.cli._package_manager", return_value="dnf"), \
             contextlib.redirect_stderr(stderr), \
             self.assertRaises(SystemExit) as caught:
            cli._preflight_libadwaita()
        self.assertEqual(caught.exception.code, 1)
        written = stderr.getvalue()
        self.assertIn("missing system dependencies: GTK 4 and libadwaita",
                      written)
        self.assertIn("  sudo dnf install gtk4 libadwaita\n", written)


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
