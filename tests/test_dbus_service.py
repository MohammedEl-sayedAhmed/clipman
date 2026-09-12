import os
import shutil
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Runs on a private bus from dbus-run-session, so the developer's real
# session bus and daemon are never touched. A child process owns the
# daemon name through the real service class; the parent then tries the
# same and must be refused instead of queued behind the child.
WORKER = textwrap.dedent(
    """
    import subprocess
    import sys
    import textwrap
    from unittest.mock import MagicMock

    import dbus
    import dbus.mainloop.glib

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    from clipman.dbus_service import BUS_NAME, ClipmanDBusService

    HOLDER = textwrap.dedent('''
        import time
        from unittest.mock import MagicMock
        import dbus.mainloop.glib
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        from clipman.dbus_service import ClipmanDBusService
        ClipmanDBusService(MagicMock(), MagicMock())
        print("holding", flush=True)
        time.sleep(30)
    ''')
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "holding"
        assert dbus.SessionBus().name_has_owner(BUS_NAME)
        try:
            ClipmanDBusService(MagicMock(), MagicMock())
        except dbus.exceptions.NameExistsException:
            print("second-owner-refused")
            sys.exit(0)
        print("second-owner-queued")
        sys.exit(1)
    finally:
        holder.kill()
    """
)


@unittest.skipUnless(shutil.which("dbus-run-session"), "dbus-run-session missing")
class TestSingleInstance(unittest.TestCase):
    """A second daemon must be refused the bus name, not queued."""

    def test_second_owner_is_refused(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
        env["PYTHONPATH"] = str(ROOT)
        result = subprocess.run(
            ["dbus-run-session", "--", sys.executable, "-c", WORKER],
            capture_output=True, timeout=30, cwd=ROOT, env=env, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr[-800:])
        self.assertIn("second-owner-refused", result.stdout)
