import os
import signal
import dbus
import gi
import dbus.mainloop.glib

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from clipman import updates
from clipman.database import ClipboardDB
from clipman.clipboard_monitor import ClipboardMonitor
from clipman.window import ClipmanWindow
from clipman.dbus_service import ClipmanDBusService


class ClipmanApp(Gtk.Application):
    def __init__(self):
        # Must be called before GTK main loop starts
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
        self.window = ClipmanWindow(self.db, self.monitor)
        self.add_window(self.window)

        # Keep the app running even when the window is hidden
        self.hold()

        self.dbus_service = ClipmanDBusService(self.window, self, self.monitor)

        # Start wl-paste --watch fallback if GNOME Shell extension absent.
        # Skip in snap: wl-paste cannot monitor the clipboard from within
        # strict confinement; snap users rely on the GNOME Shell extension.
        if not self._extension_on_bus() and not os.environ.get("SNAP"):
            self.monitor.start()

        # Schedule the first update check 30s after startup (so we
        # don't slow login) and a daily recurring tick after that.
        # ``updates.should_check_now`` enforces opt-out + 24h rate limit.
        GLib.timeout_add_seconds(30, self._update_check_tick)
        GLib.timeout_add_seconds(updates.CHECK_INTERVAL_SECONDS,
                                 self._update_check_tick)

        # Handle SIGINT/SIGTERM gracefully
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._shutdown)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._shutdown)

    def _update_check_tick(self):
        """Fire an async update check if rate-limit + opt-in allow it.

        Returning ``True`` keeps the recurring 24h timeout alive.
        The initial 30s-after-startup tick is a one-shot that returns
        ``False``; both end up here, the GLib bookkeeping is handled
        per-timeout below.
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
