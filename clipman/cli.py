"""Command-line entry point: run the daemon, or toggle a running one."""

import argparse
import importlib
import shutil
import sys

from clipman._version import __version__

_MIN_ADW_MINOR = 4


def _check_dependencies():
    """Exit with an install hint when a system dependency is missing."""
    missing = []
    try:
        importlib.import_module("gi")
    except ImportError:
        missing.append("python3-gi gir1.2-gtk-4.0 gir1.2-adw-1")
    try:
        importlib.import_module("dbus")
    except ImportError:
        missing.append("python3-dbus")
    if shutil.which("wl-paste") is None:
        missing.append("wl-clipboard")
    if missing:
        print("Error: missing system dependencies: " + ", ".join(missing))
        print("Install them with:")
        print(f"  sudo apt install {' '.join(missing)}")
        sys.exit(1)


def _preflight_libadwaita():
    """Exit with a readable error on a libadwaita older than 1.4."""
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


def _toggle():
    """Toggle the popup of a running daemon, or start one."""
    import dbus
    try:
        bus = dbus.SessionBus()
        proxy = bus.get_object("com.clipman.Daemon", "/com/clipman/Daemon")
        dbus.Interface(proxy, "com.clipman.Daemon").Toggle()
    except dbus.exceptions.DBusException:
        print("Clipman daemon is not running. Starting it now...")
        _start_daemon()


def _start_daemon():
    from clipman.app import ClipmanApp
    ClipmanApp().run([])


def _parser():
    parser = argparse.ArgumentParser(
        prog="clipman",
        description="Clipboard history manager for GNOME on Wayland.",
    )
    parser.add_argument(
        "--version", action="version", version=f"clipman {__version__}"
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["toggle"],
        help="toggle the popup of a running daemon (default: run the daemon)",
    )
    return parser


def main(argv=None):
    """Parse arguments, check the system, then run or toggle."""
    args = _parser().parse_args(argv)
    _check_dependencies()
    # The GLib loop must be the default before any bus connection, or a
    # daemon started by the toggle client never dispatches method calls.
    import dbus.mainloop.glib
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    _preflight_libadwaita()
    if args.command == "toggle":
        _toggle()
    else:
        _start_daemon()
