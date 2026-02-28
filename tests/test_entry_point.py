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
        """'clipman.py toggle' must exit promptly when no daemon runs.

        Before the fix, the toggle path would create a SessionBus
        connection without the GLib mainloop, then start the daemon
        on a poisoned connection that never dispatched method calls.
        """
        result = subprocess.run(
            [sys.executable, "clipman.py", "toggle"],
            capture_output=True, timeout=10, cwd=".",
        )
        # It should print "not running" and attempt to start (which will
        # fail in the test env due to no display), but must not hang.
        self.assertIsNotNone(result.returncode, "Process should have exited")

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
