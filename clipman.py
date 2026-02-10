#!/usr/bin/env python3
import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


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
