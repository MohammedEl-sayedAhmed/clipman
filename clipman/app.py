import logging
import os
import signal
import dbus
import dbus.exceptions
import gi
import dbus.mainloop.glib

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib

import clipman.updates as updates
from clipman.database import ClipboardDB
from clipman.clipboard_monitor import ClipboardMonitor
from clipman.window import ClipmanWindow
from clipman.dbus_service import ClipmanDBusService

logger = logging.getLogger(__name__)


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

    def do_activate(self):
        if self.window:
            self.window.toggle()
            return

        self.db = ClipboardDB()
        self.monitor = ClipboardMonitor(self.db, on_new_entry=self._on_new_entry)
        # Phase 1 of the GTK 4 + libadwaita port: keyword args only, the
        # window constructor expects (application, db, monitor) now.
        self.window = ClipmanWindow(
            application=self, db=self.db, monitor=self.monitor
        )

        # Register the D-Bus service BEFORE calling hold() — if another
        # Clipman daemon is already on the bus, we want to log + quit
        # cleanly rather than have a held-but-unreachable second daemon
        # hang around. dbus-python raises NameExistsException when the
        # well-known bus name is already owned.
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

        # Keep the app running even when the window is hidden — the daemon
        # owns the lifetime of the clipboard monitor + D-Bus service.
        # Only held *after* dbus_service registration succeeds so a
        # NameExistsException doesn't leave us in a held-forever state.
        self.hold()

        # Start wl-paste --watch fallback if GNOME Shell extension absent.
        # Skip in snap: wl-paste cannot monitor the clipboard from within
        # strict confinement; snap users rely on the GNOME Shell extension.
        if not self._extension_on_bus() and not os.environ.get("SNAP"):
            self.monitor.start()

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

    def _shutdown(self):
        if self.monitor:
            self.monitor.stop()
        if self.db:
            self.db.close()
        self.quit()
        return False
