#!/usr/bin/env python3
import sys
import os
import shutil

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_MISSING = []

try:
    import importlib
    importlib.import_module("gi")
except ImportError:
    _MISSING.append("python3-gi gir1.2-gtk-3.0")

try:
    import dbus
except ImportError:
    _MISSING.append("python3-dbus")

if shutil.which("wl-paste") is None:
    _MISSING.append("wl-clipboard")

if _MISSING:
    print("Error: missing system dependencies: " + ", ".join(_MISSING))
    print("Install them with:")
    print(f"  sudo apt install {' '.join(_MISSING)}")
    sys.exit(1)

# Must be called before ANY dbus operations so that the GLib main loop
# is used for all connections, including cached ones created by the
# toggle client.  Without this, _start_daemon() inherits a connection
# with the wrong mainloop and D-Bus method calls never get dispatched.
import dbus.mainloop.glib
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "toggle":
        # Send toggle signal to running daemon via D-Bus
        import dbus
        try:
            bus = dbus.SessionBus()
            proxy = bus.get_object("com.clipman.Daemon", "/com/clipman/Daemon")
            iface = dbus.Interface(proxy, "com.clipman.Daemon")
            iface.Toggle()
        except dbus.exceptions.DBusException:
            print("Clipman daemon is not running. Starting it now...")
            _start_daemon()
        return

    _start_daemon()


def _start_daemon():
    from clipman.app import ClipmanApp
    app = ClipmanApp()
    app.run([])


if __name__ == "__main__":
    main()
