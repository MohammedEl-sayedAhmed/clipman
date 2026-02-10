import dbus
import dbus.service

BUS_NAME = "com.clipman.Daemon"
OBJ_PATH = "/com/clipman/Daemon"
IFACE = "com.clipman.Daemon"


class ClipmanDBusService(dbus.service.Object):
    def __init__(self, window, app, monitor=None):
        bus = dbus.SessionBus()
        bus_name = dbus.service.BusName(BUS_NAME, bus)
        super().__init__(bus_name, OBJ_PATH)
        self.window = window
        self.app = app
        self.monitor = monitor

    @dbus.service.method(IFACE, in_signature="", out_signature="")
    def Toggle(self):
        self.window.toggle()

    @dbus.service.method(IFACE, in_signature="", out_signature="")
    def Show(self):
        self.window.refresh()
        self.window.show_all()
        self.window.search_entry.grab_focus()
        self.window.present()

    @dbus.service.method(IFACE, in_signature="", out_signature="")
    def Hide(self):
        self.window.hide()

    @dbus.service.method(IFACE, in_signature="", out_signature="")
    def Quit(self):
        self.app.quit()

    @dbus.service.method(IFACE, in_signature="ss", out_signature="")
    def NewEntry(self, content_type, content):
        """Called by the GNOME Shell extension when clipboard changes."""
        if self.monitor is None:
            return
        if content_type == "text" and content:
            self.monitor.handle_new_text(content)
        elif content_type == "image":
            self.monitor.handle_new_image()
