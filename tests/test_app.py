"""Lifecycle helper coverage for ``clipman.app.ClipmanApp``.

The activation flow is heavy (it touches D-Bus, GTK widgets, the
clipboard monitor, and a polling timer) so we don't exercise it
directly. Instead we construct ``ClipmanApp()`` and inject mocks for
``db`` / ``monitor`` / ``window`` so we can drive the small,
side-effect-free helpers — ``_extension_on_bus``, ``_update_check_tick``,
and ``_shutdown`` — without an X / Wayland display.

These tests skip cleanly when the GTK4 / Adw1 typelibs are missing,
mirroring the rest of the test suite.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("GDK_BACKEND", "x11")
os.environ.setdefault("GTK_A11Y", "none")

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw  # noqa: F401
    _HAS_GTK = True
except (ImportError, ValueError, AttributeError):
    _HAS_GTK = False


@unittest.skipUnless(_HAS_GTK, "GTK 4 + libadwaita not available")
class TestClipmanAppHelpers(unittest.TestCase):
    """The non-activation helpers — pure logic, no main loop required."""

    def _make_app(self):
        """Build a ClipmanApp with mocked db / monitor / window attrs.

        We deliberately avoid calling ``do_activate`` (it would spawn a
        D-Bus service and a GTK window). The helpers under test only
        read these three attributes, so MagicMocks are enough.
        """
        from clipman.app import ClipmanApp

        app = ClipmanApp()
        app.db = MagicMock(name="db")
        app.monitor = MagicMock(name="monitor")
        app.window = MagicMock(name="window")
        self.addCleanup(app.quit)
        return app

    # -- _extension_on_bus -----------------------------------------------

    def test_extension_on_bus_returns_true_when_owned(self):
        app = self._make_app()
        bus = MagicMock()
        bus.name_has_owner.return_value = True
        with patch("clipman.app.dbus.SessionBus", return_value=bus):
            self.assertTrue(app._extension_on_bus())
        bus.name_has_owner.assert_called_once_with(
            "org.gnome.Shell.Extensions.clipman"
        )

    def test_extension_on_bus_returns_false_when_not_owned(self):
        app = self._make_app()
        bus = MagicMock()
        bus.name_has_owner.return_value = False
        with patch("clipman.app.dbus.SessionBus", return_value=bus):
            self.assertFalse(app._extension_on_bus())

    def test_extension_on_bus_returns_false_on_dbus_exception(self):
        from clipman import app as app_module

        app = self._make_app()
        bus = MagicMock()
        bus.name_has_owner.side_effect = app_module.dbus.DBusException(
            "bus unavailable"
        )
        with patch("clipman.app.dbus.SessionBus", return_value=bus):
            self.assertFalse(app._extension_on_bus())

    # -- _update_check_tick ----------------------------------------------

    def test_update_check_tick_respects_should_check_now_false(self):
        """When should_check_now is False the tick must not call check_async."""
        app = self._make_app()
        with patch("clipman.app.updates.should_check_now",
                   return_value=False) as scn, \
             patch("clipman.app.updates.check_async") as ca:
            # The recurring 24h tick returns True so GLib keeps it alive;
            # we assert it returns *something* and that no fetch fired.
            result = app._update_check_tick()
        scn.assert_called_once_with(app.db)
        ca.assert_not_called()
        # The recurring tick must stay alive — the helper returns True
        # here so the daily timer keeps re-firing.
        self.assertTrue(result)

    def test_update_check_tick_fires_when_should_check_now_true(self):
        app = self._make_app()
        with patch("clipman.app.updates.should_check_now",
                   return_value=True), \
             patch("clipman.app.updates.check_async") as ca:
            app._update_check_tick()
        ca.assert_called_once()

    def test_update_check_tick_noop_when_db_unset(self):
        """The tick fires before do_activate has assigned self.db."""
        from clipman.app import ClipmanApp

        app = ClipmanApp()
        app.db = None
        self.addCleanup(app.quit)
        with patch("clipman.app.updates.check_async") as ca:
            result = app._update_check_tick()
        # No db -> shouldn't try to read the rate-limit setting.
        ca.assert_not_called()
        # And the timer must NOT be kept alive — there's nothing to do.
        self.assertFalse(result)

    # -- _shutdown -------------------------------------------------------

    def test_shutdown_stops_monitor_then_closes_db_then_quits(self):
        """Order matters: monitor.stop -> db.close -> app.quit."""
        app = self._make_app()
        call_order: list[str] = []
        app.monitor.stop.side_effect = lambda: call_order.append("monitor.stop")
        app.db.close.side_effect = lambda: call_order.append("db.close")
        with patch.object(app, "quit",
                          side_effect=lambda: call_order.append("app.quit")):
            app._shutdown()
        self.assertEqual(
            call_order,
            ["monitor.stop", "db.close", "app.quit"],
        )

    def test_shutdown_safe_when_monitor_and_db_unset(self):
        """Before do_activate the attrs are None — shutdown must not crash."""
        from clipman.app import ClipmanApp

        app = ClipmanApp()
        app.monitor = None
        app.db = None
        self.addCleanup(app.quit)
        with patch.object(app, "quit") as q:
            app._shutdown()
        q.assert_called_once()


if __name__ == "__main__":
    unittest.main()
