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
    _MISSING.append("python3-gi gir1.2-gtk-4.0 gir1.2-adw-1")

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


_MIN_ADW_MINOR = 4


def _preflight_libadwaita():
    """Refuse to boot when libadwaita is too old.

    The GTK 4 port relies on widgets introduced in libadwaita 1.4
    (Adw.AboutDialog, Adw.Banner action API, etc.). Fail with a
    readable error before ClipmanApp tries to construct them — the
    crash deep inside Gtk would otherwise just print a confusing
    'no such symbol' from C.
    """
    import gi
    gi.require_version("Adw", "1")
    from gi.repository import Adw
    minor = getattr(Adw, "MINOR_VERSION", 0)
    if minor < _MIN_ADW_MINOR:
        major = getattr(Adw, "MAJOR_VERSION", 1)
        micro = getattr(Adw, "MICRO_VERSION", 0)
        print(
            f"Error: libadwaita {major}.{minor}.{micro} is too old. "
            f"Clipman requires libadwaita >= 1.{_MIN_ADW_MINOR}.",
            file=sys.stderr,
        )
        print(
            "On Ubuntu 24.04+ / Debian trixie this ships as "
            "libadwaita-1-0; on Fedora 40+ as 'libadwaita'.",
            file=sys.stderr,
        )
        sys.exit(1)


def main():
    _preflight_libadwaita()

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
