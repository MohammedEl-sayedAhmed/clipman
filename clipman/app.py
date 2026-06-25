import os
import signal
import dbus
import gi
import dbus.mainloop.glib

# GTK 4 + libadwaita 1.4+. Adw must be initialised BEFORE any GTK widget
# is constructed (Adw.init() runs Gtk.init() under the hood and primes
# the libadwaita style provider).
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib  # noqa: E402

from clipman import updates
from clipman.database import ClipboardDB
from clipman.clipboard_monitor import ClipboardMonitor
from clipman.window import ClipmanWindow
from clipman.dbus_service import ClipmanDBusService


class ClipmanApp(Adw.Application):
    def __init__(self):
        # DBus glib mainloop integration must be installed before the
        # GTK main loop starts so D-Bus signals dispatch on the same
        # loop libadwaita uses.
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
        self.window = ClipmanWindow(application=self, db=self.db, monitor=self.monitor)
        # Adw.Application tracks windows via add_window; the popup window
        # toggle/visibility is managed by ClipmanWindow itself.
        self.add_window(self.window)

        # Keep the app running even when the popup is hidden — the
        # daemon needs to stay alive to receive D-Bus toggle calls and
        # to keep the clipboard monitor running.
        self.hold()

        self.dbus_service = ClipmanDBusService(self.window, self, self.monitor)

        # Start wl-paste --watch fallback if GNOME Shell extension absent.
        # Skip in snap: wl-paste cannot monitor the clipboard from within
        # strict confinement; snap users rely on the GNOME Shell extension.
        if not self._extension_on_bus() and not os.environ.get("SNAP"):
            self.monitor.start()

        # Schedule the first update check 30s after startup (so we
        # don't slow login) and a daily recurring tick after that.
        GLib.timeout_add_seconds(30, self._update_check_tick)
        GLib.timeout_add_seconds(updates.CHECK_INTERVAL_SECONDS,
                                 self._update_check_tick)

        # Handle SIGINT/SIGTERM gracefully
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._shutdown)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._shutdown)

    def _update_check_tick(self):
        if self.db is None:
            return False
        if updates.should_check_now(self.db):
            updates.check_async(self.db, callback=self._on_update_result)
        return True

    def _on_update_result(self, is_newer, latest, url):
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
