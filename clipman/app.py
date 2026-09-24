import logging
import os
import shutil
import signal
import sqlite3
from gettext import gettext as _
import dbus
import dbus.exceptions
import gi
import dbus.mainloop.glib

# Module-level GTK4 binding. Wrapped because some CI sandboxes ship a
# placeholder ``gi`` shim that lacks ``require_version`` (or has the
# typelibs unavailable). Re-raise as RuntimeError so importers can
# guard with a single except clause.
try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, GLib
except (AttributeError, ValueError, ImportError) as e:
    raise RuntimeError(
        "GTK 4 + libadwaita not available: %s" % e
    ) from e

import clipman.updates as updates
from clipman.database import ClipboardDB
from clipman.clipboard_monitor import ClipboardMonitor
from clipman.window import ClipmanWindow
from clipman.dbus_service import ClipmanDBusService
import clipman.shell_bridge as shell_bridge

logger = logging.getLogger(__name__)

# What the journal says when nothing records copies. The popup shows the
# edge state with the same id.
_PROBLEM_LOGS = {
    "first-run": (
        "The Clipman GNOME Shell extension is not running, so copies are "
        "not recorded. After installing it, log out and back in. If it is "
        "still off, run: gnome-extensions enable clipman@clipman.com"
    ),
    "extension-missing": (
        "The Clipman GNOME Shell extension is not running, so copies are "
        "not recorded. The snap cannot install it: get it from "
        "https://extensions.gnome.org/extension/9407/ and log out and back in."
    ),
    "watcher-crashed": (
        "wl-paste --watch failed too many times, so copies are not "
        "recorded. Restart Clipman to try again."
    ),
    "clipboard-blocked": (
        "wl-paste is not installed (package wl-clipboard), so copies are "
        "not recorded."
    ),
}


class ClipmanApp(Adw.Application):
    def __init__(self):
        # Must be called before the GTK main loop starts so that any
        # subsequent dbus.SessionBus() use integrates with GLib.
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        super().__init__(application_id="com.clipman.Clipman")
        self.db = None
        self.monitor = None
        self.window = None
        self.dbus_service = None
        # Why nothing records copies (an edge state id), or None.
        self._recording_problem = None
        self._watcher_dead = False
        # The process exit status (cli.py returns it). Non-zero when
        # start-up failed, so systemd's Restart=on-failure tries again.
        self.exit_status = 0
        self._db_error_window = None

    def do_activate(self):
        if self.window:
            self.window.toggle()
            return
        try:
            self._start()
        except Exception:
            # GLib prints an exception raised here and carries on, so the
            # daemon would exit 0 with nothing on screen.
            logger.exception("Clipman could not start")
            self._fail()

    def _fail(self):
        """Quit with a non-zero exit status: start-up failed."""
        self.exit_status = 1
        self.quit()

    def _start(self):
        try:
            self.db = ClipboardDB()
        except (sqlite3.DatabaseError, OSError):
            # Locked, unreadable or corrupt ("file is not a database" is a
            # DatabaseError, and OperationalError is one kind of it): show
            # the guided error state (mockup db-corrupt), not a traceback.
            logger.exception("clipboard database could not be opened")
            self._present_db_error()
            return
        self.monitor = ClipboardMonitor(self.db, on_new_entry=self._on_new_entry)
        # Surface repeated wl-paste crashes in the popup instead of dying
        # silently (mockup watcher-crashed).
        self.monitor.on_watcher_dead = self._on_watcher_dead
        # Phase 1 of the GTK 4 + libadwaita port: keyword args only, the
        # window constructor expects (application, db, monitor) now.
        self.window = ClipmanWindow(
            application=self, db=self.db, monitor=self.monitor
        )

        # Apply the persisted start-in-incognito preference. Driven through
        # the window so the header toggle, tooltip and privacy banner all
        # reflect it — previously this setting was saved but never read, so
        # "start in incognito" silently did nothing and clips were recorded.
        if (self.db.get_setting("incognito_on_launch", "false") or "").strip(
        ).lower() == "true":
            self.window.set_incognito(True)

        # Register the service before hold(): a second daemon, or a bus
        # we cannot reach, must log and quit instead of lingering.
        try:
            self.dbus_service = ClipmanDBusService(
                self.window, self, self.monitor
            )
        except dbus.exceptions.NameExistsException:
            logger.warning(
                "Another Clipman daemon is already running on the "
                "session bus; exiting."
            )
            self.quit()
            return
        except dbus.exceptions.DBusException:
            logger.exception("Cannot register on the session bus; exiting.")
            self._fail()
            return

        # Incognito also pauses the extension (no clip crosses the bus).
        # Connected only now: the extension accepts calls from the owner of
        # our bus name, so a push made before registration (incognito on
        # launch, above) was refused and logged as a denied call. Push the
        # state now, and again after any extension restart.
        self.monitor.on_incognito_changed = shell_bridge.set_paused
        shell_bridge.set_paused(self.monitor.incognito)
        try:
            dbus.SessionBus().watch_name_owner(
                shell_bridge.EXT_BUS_NAME, self._on_extension_owner_changed
            )
        except dbus.DBusException:
            logger.debug("cannot watch the extension name", exc_info=True)

        # Keep the app running even when the window is hidden — the daemon
        # owns the lifetime of the clipboard monitor + D-Bus service.
        # Only held *after* dbus_service registration succeeds so a
        # NameExistsException doesn't leave us in a held-forever state.
        self.hold()

        # The database opens now (restored from a backup, or repaired), so
        # the error window has done its job.
        if self._db_error_window is not None:
            self._db_error_window.destroy()
            self._db_error_window = None

        # Without the extension, record with wl-paste --watch where it can
        # work. Either way, tell the popup if nothing records copies.
        extension_on_bus = self._extension_on_bus()
        if not extension_on_bus and self._watcher_can_record():
            self.monitor.start()
        self._update_recording_problem(extension_on_bus)

        # Schedule the first update check 30s after startup (so we
        # don't slow login) and a daily recurring tick after that.
        # ``updates.should_check_now`` enforces opt-out + 24h rate limit.
        # The 30s tick is one-shot — only the 24h tick recurs, otherwise
        # we'd burn an extra timer every login.
        GLib.timeout_add_seconds(30, self._update_check_tick_once)
        GLib.timeout_add_seconds(updates.CHECK_INTERVAL_SECONDS,
                                 self._update_check_tick)

        # Handle SIGINT/SIGTERM gracefully
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._shutdown)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._shutdown)

    def _on_extension_owner_changed(self, owner):
        if owner and self.monitor is not None:
            shell_bridge.set_paused(self.monitor.incognito)
        self._update_recording_problem(bool(owner))

    def _on_watcher_dead(self):
        self._watcher_dead = True
        self._update_recording_problem(self._extension_on_bus())

    def _watcher_can_record(self):
        """Whether the wl-paste --watch fallback can record here.

        It needs the data-control protocol, which GNOME does not have, so
        on GNOME it would exit at once and only the extension records. In
        the snap, wl-paste cannot watch the host clipboard at all.
        """
        return not os.environ.get("SNAP") and not self._gnome_shell_on_bus()

    def _recording_problem_for(self, extension_on_bus):
        """Return the edge state that says why copies are not recorded.

        None means something records them: the extension, or the
        wl-paste watcher outside GNOME.
        """
        if extension_on_bus:
            return None
        if os.environ.get("SNAP"):
            return "extension-missing"
        if self._gnome_shell_on_bus():
            return "first-run"
        if self._watcher_dead:
            return "watcher-crashed"
        if shutil.which("wl-paste") is None:
            return "clipboard-blocked"
        return None

    def _update_recording_problem(self, extension_on_bus):
        """Work out the recording problem, log a new one, tell the popup."""
        problem = self._recording_problem_for(extension_on_bus)
        if problem != self._recording_problem and problem is not None:
            logger.warning(_PROBLEM_LOGS[problem])
        self._recording_problem = problem
        if self.window is not None:
            self.window.set_recording_problem(problem)

    def _present_db_error(self):
        """Minimal window with the db-locked statuspage (no DB available).

        Closing it ends the process with status 0: the user has seen the
        problem, so systemd need not start it again. Activating again
        (Super+V) brings the same window back.
        """
        from clipman.edge_states import render_edge_state

        if self._db_error_window is not None:
            self._db_error_window.present()
            return
        win = Adw.ApplicationWindow(application=self)
        win.set_title("Clipman")
        win.set_default_size(420, 480)
        win.set_content(
            render_edge_state("db-locked", on_action=self._on_db_error_action)
        )
        self._db_error_window = win
        win.present()

    def _on_db_error_action(self, action_id):
        from clipman.database import DATA_DIR

        if action_id == "reveal-db-folder":
            import subprocess
            try:
                subprocess.Popen(
                    ["xdg-open", str(DATA_DIR)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                logger.debug("xdg-open failed", exc_info=True)
        elif action_id in ("open-restore", "rechoose-restore"):
            self._pick_backup()

    def _pick_backup(self):
        """Ask for the backup to restore. The safety copies that
        Preferences writes before each restore are in the data folder."""
        from gi.repository import Gio, Gtk

        from clipman.database import DATA_DIR

        dialog = Gtk.FileDialog()
        dialog.set_title(_("Restore from backup"))
        dialog.set_initial_folder(Gio.File.new_for_path(str(DATA_DIR)))
        dialog.open(self._db_error_window, None, self._on_backup_picked)

    def _on_backup_picked(self, dialog, result):
        """Put the picked backup in place of the unreadable database, then
        start as usual and show the restored history."""
        from clipman.database import restore_backup_file

        try:
            picked = dialog.open_finish(result)
        except GLib.Error:
            return  # dismissed
        path = picked.get_path() if picked is not None else None
        try:
            if path is None:
                raise ValueError("not a local file")
            restore_backup_file(path)
        except (ValueError, OSError) as exc:
            logger.warning("Could not restore %s: %s", path, exc)
            self._show_restore_failed()
            return
        logger.info("Restored the history from %s", path)
        self.do_activate()
        if self.window is not None:
            self.window.toggle()

    def _show_restore_failed(self):
        from clipman.edge_states import render_edge_state

        alert = render_edge_state(
            "restore-failed", on_action=self._on_db_error_action
        )
        alert.present(self._db_error_window)

    def _update_check_tick_once(self):
        """One-shot initial tick — runs ``_update_check_tick`` then dies.

        ``GLib.timeout_add_seconds`` keeps the timer alive while the
        callback returns ``True``. The recurring 24h timer wants that
        behaviour; the initial 30s timer doesn't (otherwise we'd have
        two pollers stacked forever).
        """
        self._update_check_tick()
        return False

    def _update_check_tick(self):
        """Fire an async update check if rate-limit + opt-in allow it.

        Returning ``True`` keeps the recurring 24h timeout alive.
        ``should_check_now`` re-applies the 24h rate limit so even if
        the timer fires for any reason, no extra HTTP request goes out.
        """
        if self.db is None:
            return False
        if updates.should_check_now(self.db):
            updates.check_async(self.db, callback=self._on_update_result)
        return True

    def _on_update_result(self, is_newer, latest, url):
        """Callback marshalled to the GTK main loop by ``updates``.

        If the window already exists, refresh its banner state. The
        method is always defined on ClipmanWindow, so no defensive
        guard beyond the None check is needed.
        """
        if is_newer and self.window is not None:
            self.window.refresh_update_banner()
        return False  # idle_add: run once

    def _on_new_entry(self):
        if self.window and self.window.get_visible():
            self.window.refresh()

    def _extension_on_bus(self):
        """Check if the GNOME Shell clipboard extension is running."""
        try:
            bus = dbus.SessionBus()
            return bus.name_has_owner("org.gnome.Shell.Extensions.clipman")
        except dbus.DBusException:
            return False

    def _gnome_shell_on_bus(self):
        """Check if GNOME Shell runs this session (it owns org.gnome.Shell)."""
        try:
            return dbus.SessionBus().name_has_owner("org.gnome.Shell")
        except dbus.DBusException:
            return False

    def _shutdown(self):
        if self.monitor:
            self.monitor.stop()
        if self.db:
            self.db.close()
        self.quit()
        return False
