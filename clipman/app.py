import signal
import gi
import dbus.mainloop.glib

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

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

        self.monitor.start()
        self.dbus_service = ClipmanDBusService(self.window, self, self.monitor)

        # Handle SIGINT/SIGTERM gracefully
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._shutdown)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._shutdown)

    def _on_new_entry(self):
        if self.window and self.window.get_visible():
            self.window.refresh()

    def _shutdown(self):
        if self.monitor:
            self.monitor.stop()
        if self.db:
            self.db.close()
        self.quit()
        return False
