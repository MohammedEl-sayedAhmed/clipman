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
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

# Probe GTK4 + libadwaita availability without taking a strong
# reference on ``Adw`` — the helper tests under this module never
# touch Adw directly (they mock ``ClipmanApp``'s collaborators), so a
# top-level ``from gi.repository import Adw`` would be an unused
# import (py/unused-import). Importing the package itself is enough
# to surface a missing typelib via ImportError/ValueError, and
# clipman.app's own module-level guard catches the remaining edge
# cases by re-raising as RuntimeError.
try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    # Drive the typelib lookup through clipman.app's own guard so
    # this module skips cleanly when the import-chain raises
    # RuntimeError (the module-level guard re-raises gi failures as
    # RuntimeError so callers only need a single except clause).
    from clipman.app import ClipmanApp as _ClipmanAppProbe
    _HAS_GTK = _ClipmanAppProbe is not None
except (ImportError, ValueError, AttributeError, RuntimeError):
    # ImportError: pygobject / gi missing on the runner.
    # ValueError: gi present but the GTK4 / Adw1 typelibs aren't.
    # AttributeError: a stub ``gi`` shim lacks ``require_version``.
    # RuntimeError: re-raised by ``clipman.app``'s own module-level
    # guard when the chain above fails inside the package.
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

    # -- _on_extension_owner_changed ------------------------------------

    def test_extension_reappearing_pushes_the_pause_state(self):
        app = self._make_app()
        app.monitor.incognito = True
        with patch("clipman.app.shell_bridge.set_paused") as set_paused:
            app._on_extension_owner_changed(":1.77")
        set_paused.assert_called_once_with(True)
        app.window.set_recording_problem.assert_called_once_with(None)

    def test_extension_vanishing_pushes_nothing(self):
        app = self._make_app()
        with patch("clipman.app.shell_bridge.set_paused") as set_paused, \
             patch.object(app, "_gnome_shell_on_bus", return_value=True), \
             self.assertLogs("clipman.app", "WARNING"):
            app._on_extension_owner_changed("")
        set_paused.assert_not_called()
        # The popup says at once that nothing records copies now.
        app.window.set_recording_problem.assert_called_once_with("first-run")

    # -- what records copies ---------------------------------------------

    def _session(self, app, gnome=False, snap=False, wl_paste=True):
        """Patch the facts ``_recording_problem_for`` reads."""
        patches = [
            patch.object(app, "_gnome_shell_on_bus", return_value=gnome),
            patch("clipman.app.shutil.which",
                  return_value="/usr/bin/wl-paste" if wl_paste else None),
            patch.dict(os.environ, {"SNAP": "/snap/clipman/x1"}),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        if not snap:
            # patch.dict restores the variable when the test ends.
            os.environ.pop("SNAP")

    def test_recording_problem_for_each_session(self):
        cases = [
            # (extension, gnome, snap, wl_paste, watcher_dead) -> problem
            ((True, True, False, True, False), None),
            ((True, True, True, True, False), None),
            ((False, True, False, True, False), "first-run"),
            ((False, True, True, True, False), "extension-missing"),
            # On GNOME the watcher can't record, so a dead one is not
            # the problem: the missing extension is.
            ((False, True, False, True, True), "first-run"),
            ((False, False, False, True, True), "watcher-crashed"),
            ((False, False, False, False, False), "clipboard-blocked"),
            ((False, False, False, True, False), None),
        ]
        for (extension, gnome, snap, wl_paste, dead), problem in cases:
            with self.subTest(extension=extension, gnome=gnome, snap=snap,
                              wl_paste=wl_paste, watcher_dead=dead):
                app = self._make_app()
                self._session(app, gnome=gnome, snap=snap, wl_paste=wl_paste)
                app._watcher_dead = dead
                self.assertEqual(app._recording_problem_for(extension),
                                 problem)

    def test_the_watcher_starts_only_outside_gnome_and_snap(self):
        for gnome, snap, can_record in ((True, False, False),
                                        (False, True, False),
                                        (False, False, True)):
            with self.subTest(gnome=gnome, snap=snap):
                app = self._make_app()
                self._session(app, gnome=gnome, snap=snap)
                self.assertEqual(app._watcher_can_record(), can_record)

    def test_a_new_problem_is_logged_once(self):
        """The journal says why nothing is recorded (issue #1 saw only
        "Started clipman.service"), once per new problem, and the popup
        is told every time."""
        app = self._make_app()
        self._session(app, gnome=True)
        with self.assertLogs("clipman.app", "WARNING") as logs:
            app._update_recording_problem(False)
            app._update_recording_problem(False)
        self.assertEqual(len(logs.records), 1)
        self.assertIn("gnome-extensions enable clipman@clipman.com",
                      logs.output[0])
        self.assertEqual(app.window.set_recording_problem.call_count, 2)

        with self.assertNoLogs("clipman.app", "WARNING"):
            app._update_recording_problem(True)
        app.window.set_recording_problem.assert_called_with(None)

    def test_dead_watcher_is_reported_outside_gnome(self):
        app = self._make_app()
        self._session(app)
        with patch.object(app, "_extension_on_bus", return_value=False), \
             self.assertLogs("clipman.app", "WARNING"):
            app._on_watcher_dead()
        app.window.set_recording_problem.assert_called_once_with(
            "watcher-crashed"
        )

    def test_dead_watcher_is_not_blamed_on_gnome(self):
        """A watcher started before the Shell owned its name dies on GNOME;
        the popup must not say "restart" when the extension is running."""
        app = self._make_app()
        self._session(app, gnome=True)
        with patch.object(app, "_extension_on_bus", return_value=True):
            app._on_watcher_dead()
        app.window.set_recording_problem.assert_called_once_with(None)


@unittest.skipUnless(_HAS_GTK, "GTK 4 + libadwaita not available")
class TestStartUp(unittest.TestCase):
    """What start-up does when something fails, and the database-error
    screen (audit findings CORE-4, PKG-11 and UI-18)."""

    def _make_app(self):
        from clipman.app import ClipmanApp

        app = ClipmanApp()
        self.addCleanup(app.quit)
        return app

    def _activate(self, app, **fakes):
        """Run do_activate with every collaborator faked; ``fakes`` maps a
        patch target to the keyword arguments of its mock. Return quit."""
        db = MagicMock(name="db")
        db.get_setting.return_value = "false"
        targets = {
            "clipman.app.ClipboardDB": {"return_value": db},
            "clipman.app.ClipboardMonitor": {},
            "clipman.app.ClipmanWindow": {},
            "clipman.app.ClipmanDBusService": {},
            "clipman.app.shell_bridge.set_paused": {},
            "clipman.app.dbus.SessionBus": {},
            "clipman.app.GLib.timeout_add_seconds": {},
            "clipman.app.GLib.unix_signal_add": {},
        }
        targets.update(fakes)
        for target, kwargs in targets.items():
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        with patch.object(app, "hold"), \
             patch.object(app, "quit") as quit_, \
             patch.object(app, "_extension_on_bus", return_value=True):
            app.do_activate()
        return quit_

    def test_unreadable_database_shows_the_error_screen(self):
        """"file is not a database" is a DatabaseError; only its subclass
        OperationalError was caught, so the daemon died with a traceback."""
        for exc in (sqlite3.DatabaseError("file is not a database"),
                    sqlite3.OperationalError("database is locked"),
                    PermissionError(13, "Permission denied")):
            with self.subTest(exc=exc):
                app = self._make_app()
                with patch.object(app, "_present_db_error") as present, \
                     self.assertLogs("clipman.app", "ERROR"):
                    self._activate(app, **{
                        "clipman.app.ClipboardDB": {"side_effect": exc},
                    })
                present.assert_called_once_with()
                self.assertEqual(app.exit_status, 0)

    def test_failed_start_exits_non_zero(self):
        """GLib swallowed this exception and the daemon exited 0, so
        systemd's Restart=on-failure never tried again."""
        app = self._make_app()
        error = RuntimeError("Gtk couldn't be initialized")
        with self.assertLogs("clipman.app", "ERROR") as logs:
            quit_ = self._activate(app, **{
                "clipman.app.ClipmanWindow": {"side_effect": error},
            })
        self.assertIn("Clipman could not start", logs.output[0])
        quit_.assert_called_once_with()
        self.assertEqual(app.exit_status, 1)

    def test_unreachable_bus_exits_non_zero(self):
        from clipman import app as app_module

        app = self._make_app()
        error = app_module.dbus.exceptions.DBusException("no bus")
        with self.assertLogs("clipman.app", "ERROR"):
            quit_ = self._activate(app, **{
                "clipman.app.ClipmanDBusService": {"side_effect": error},
            })
        quit_.assert_called_once_with()
        self.assertEqual(app.exit_status, 1)

    def test_second_daemon_exits_zero(self):
        """Another daemon owns the name: nothing failed, and a non-zero
        status would make systemd start this one again and again."""
        from clipman import app as app_module

        app = self._make_app()
        error = app_module.dbus.exceptions.NameExistsException(
            "com.clipman.Daemon"
        )
        with self.assertLogs("clipman.app", "WARNING"):
            quit_ = self._activate(app, **{
                "clipman.app.ClipmanDBusService": {"side_effect": error},
            })
        quit_.assert_called_once_with()
        self.assertEqual(app.exit_status, 0)

    def test_toggle_that_started_the_daemon_shows_the_popup(self):
        """CORE-13: the first `clipman toggle` started the daemon but
        showed nothing, so the shortcut had to be pressed again."""
        app = self._make_app()
        app.show_on_start = True
        self._activate(app)
        app.window.toggle.assert_called_once_with()
        self.assertFalse(app.show_on_start)

    def test_plain_start_keeps_the_popup_hidden(self):
        app = self._make_app()
        self._activate(app)
        app.window.toggle.assert_not_called()

    def test_database_that_opens_closes_the_error_window(self):
        app = self._make_app()
        error_window = MagicMock(name="error window")
        app._db_error_window = error_window
        self._activate(app)
        error_window.destroy.assert_called_once_with()
        self.assertIsNone(app._db_error_window)
        self.assertEqual(app.exit_status, 0)

    def test_second_activation_brings_back_the_same_error_window(self):
        app = self._make_app()
        error_window = MagicMock(name="error window")
        app._db_error_window = error_window
        app._present_db_error()
        error_window.present.assert_called_once_with()
        self.assertIs(app._db_error_window, error_window)

    def test_restore_button_opens_the_picker_instead_of_quitting(self):
        """UI-18: "Restore from backup" used to quit the app."""
        for action in ("open-restore", "rechoose-restore"):
            with self.subTest(action=action):
                app = self._make_app()
                with patch.object(app, "_pick_backup") as pick, \
                     patch.object(app, "quit") as quit_:
                    app._on_db_error_action(action)
                pick.assert_called_once_with()
                quit_.assert_not_called()

    def test_closing_the_restore_failed_dialog_does_nothing(self):
        app = self._make_app()
        with patch.object(app, "_pick_backup") as pick, \
             patch.object(app, "quit") as quit_:
            app._on_db_error_action("close-dialog")
        pick.assert_not_called()
        quit_.assert_not_called()

    def _picked(self, path):
        picked = MagicMock(name="file")
        picked.get_path.return_value = path
        dialog = MagicMock(name="dialog")
        dialog.open_finish.return_value = picked
        return dialog

    def test_picked_backup_is_restored_then_clipman_starts(self):
        app = self._make_app()
        app.window = MagicMock(name="window")
        with patch("clipman.database.restore_backup_file") as restore, \
             patch.object(app, "do_activate") as activate:
            app._on_backup_picked(self._picked("/backups/clipman.db"), None)
        restore.assert_called_once_with("/backups/clipman.db")
        activate.assert_called_once_with()
        # The user sees the history they just got back.
        self.assertTrue(app.show_on_start)

    def test_unusable_backup_keeps_the_error_screen(self):
        app = self._make_app()
        error = ValueError("Invalid backup: missing 'entries' table")
        with patch("clipman.database.restore_backup_file",
                   side_effect=error), \
             patch.object(app, "do_activate") as activate, \
             patch.object(app, "_show_restore_failed") as failed, \
             self.assertLogs("clipman.app", "WARNING"):
            app._on_backup_picked(self._picked("/tmp/notes.db"), None)
        failed.assert_called_once_with()
        activate.assert_not_called()

    def test_dismissed_picker_changes_nothing(self):
        from gi.repository import GLib

        app = self._make_app()
        dialog = MagicMock(name="dialog")
        dialog.open_finish.side_effect = GLib.Error("Dismissed by user")
        with patch("clipman.database.restore_backup_file") as restore, \
             patch.object(app, "do_activate") as activate:
            app._on_backup_picked(dialog, None)
        restore.assert_not_called()
        activate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
