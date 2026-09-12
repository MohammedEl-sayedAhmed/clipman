import os
import subprocess
import sys
import unittest


class TestDBusMainLoopInit(unittest.TestCase):
    """Verify that DBusGMainLoop is set before any D-Bus connections.

    Regression test for a bug where the 'toggle' path created a
    dbus.SessionBus() connection before DBusGMainLoop was set as
    the default mainloop.  When the toggle fell back to starting
    the daemon, the cached connection used the wrong (non-GLib)
    mainloop, making the D-Bus service unresponsive.
    """

    def test_glib_mainloop_set_at_module_level(self):
        """clipman.py must call DBusGMainLoop(set_as_default=True) at
        module level, before main() is ever called."""
        # Read the source and verify the setup happens before def main()
        with open("clipman.py") as f:
            source = f.read()

        # Find positions
        setup_pos = source.find("DBusGMainLoop(set_as_default=True)")
        main_pos = source.find("def main():")

        self.assertNotEqual(setup_pos, -1,
                            "DBusGMainLoop(set_as_default=True) not found in clipman.py")
        self.assertNotEqual(main_pos, -1,
                            "def main() not found in clipman.py")
        self.assertLess(setup_pos, main_pos,
                        "DBusGMainLoop must be called before def main() "
                        "to prevent the toggle path from creating a "
                        "D-Bus connection with the wrong mainloop")

    def test_toggle_without_daemon_does_not_hang(self):
        """'clipman.py toggle' must exit promptly when no daemon runs."""
        # No display and a dead bus: the toggle falls through to the daemon
        # start, which must fail fast instead of running the main loop.
        env = {k: v for k, v in os.environ.items()
               if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
        env["GDK_BACKEND"] = "x11"
        env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/nonexistent/clipman-test"
        result = subprocess.run(
            [sys.executable, "clipman.py", "toggle"],
            capture_output=True, timeout=10, cwd=".", env=env,
        )
        output = result.stdout + result.stderr
        expected = (b"not running", b"missing system dependencies")
        self.assertTrue(any(m in output for m in expected), output[-500:])

    def test_dbus_import_order(self):
        """dbus.mainloop.glib must be imported before dbus in clipman.py."""
        with open("clipman.py") as f:
            source = f.read()

        glib_import_pos = source.find("import dbus.mainloop.glib")
        # The toggle path does 'import dbus' inside main()
        main_pos = source.find("def main():")

        self.assertNotEqual(glib_import_pos, -1,
                            "import dbus.mainloop.glib not found")
        self.assertLess(glib_import_pos, main_pos,
                        "dbus.mainloop.glib must be imported at module level, "
                        "before main() where 'import dbus' happens")


class TestDependencyCheck(unittest.TestCase):
    """Verify that clipman.py checks for system dependencies at startup."""

    def test_dep_check_exists_before_main(self):
        """Dependency check must run before main() is called."""
        with open("clipman.py") as f:
            source = f.read()
        check_pos = source.find("_MISSING")
        main_pos = source.find("def main():")
        self.assertNotEqual(check_pos, -1,
                            "Dependency check (_MISSING) not found in clipman.py")
        self.assertLess(check_pos, main_pos,
                        "Dependency check must happen before def main()")

    def test_dep_check_covers_gi(self):
        """clipman.py must check for gi (python3-gi)."""
        with open("clipman.py") as f:
            source = f.read()
        self.assertIn("gi", source)
        self.assertIn("python3-gi", source)

    def test_dep_check_covers_dbus(self):
        """clipman.py must check for dbus (python3-dbus)."""
        with open("clipman.py") as f:
            source = f.read()
        self.assertIn("import dbus", source)
        self.assertIn("python3-dbus", source)

    def test_dep_check_covers_wl_clipboard(self):
        """clipman.py must check for wl-paste (wl-clipboard)."""
        with open("clipman.py") as f:
            source = f.read()
        self.assertIn("wl-paste", source)
        self.assertIn("wl-clipboard", source)
