import dbus
import dbus.service
import dbus.mainloop.glib

BUS_NAME = "com.clipman.Daemon"
OBJ_PATH = "/com/clipman/Daemon"
IFACE = "com.clipman.Daemon"


class ClipmanDBusService(dbus.service.Object):
    def __init__(self, window, app):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        bus_name = dbus.service.BusName(BUS_NAME, bus)
        super().__init__(bus_name, OBJ_PATH)
        self.window = window
        self.app = app

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


def send_toggle():
    try:
        bus = dbus.SessionBus()
        proxy = bus.get_object(BUS_NAME, OBJ_PATH)
        iface = dbus.Interface(proxy, IFACE)
        iface.Toggle()
        return True
    except dbus.exceptions.DBusException:
        return False
