"""Command-line entry point: run the daemon, or toggle a running one."""

import argparse
import importlib
import os
import shutil
import sys

from clipman._version import __version__

# Adw.Dialog and Adw.AlertDialog, which Preferences and the snippets
# editor subclass at import time, arrived in libadwaita 1.5.
_MIN_ADW_MINOR = 5


# What each missing piece is called by each package manager: the
# runtime lists in scripts/deps.sh.
_PACKAGES = {
    "apt": {
        "gi": ["python3-gi"],
        "gtk": ["gir1.2-gtk-4.0", "gir1.2-adw-1"],
        "dbus": ["python3-dbus"],
        "wl-clipboard": ["wl-clipboard"],
    },
    "dnf": {
        "gi": ["python3-gobject"],
        "gtk": ["gtk4", "libadwaita"],
        "dbus": ["python3-dbus"],
        "wl-clipboard": ["wl-clipboard"],
    },
    "pacman": {
        "gi": ["python-gobject"],
        "gtk": ["gtk4", "libadwaita"],
        "dbus": ["python-dbus"],
        "wl-clipboard": ["wl-clipboard"],
    },
}
_INSTALL = {
    "apt": ("apt-get", "sudo apt install"),
    "dnf": ("dnf", "sudo dnf install"),
    "pacman": ("pacman", "sudo pacman -S"),
}
_NAMES = {
    "gi": "PyGObject",
    "gtk": "GTK 4 and libadwaita",
    "dbus": "dbus-python",
    "wl-clipboard": "wl-clipboard",
}


def _package_manager():
    """Return "apt", "dnf" or "pacman", whichever this system has."""
    for manager, (program, _command) in _INSTALL.items():
        if shutil.which(program):
            return manager
    return None


def _isolated_venv():
    """True in a virtual environment that cannot see the system's Python
    packages. PyGObject and dbus-python come from the system, so there
    they are missing even when installed."""
    if sys.prefix == sys.base_prefix:
        return False
    try:
        with open(os.path.join(sys.prefix, "pyvenv.cfg"), encoding="utf-8") as cfg:
            for line in cfg:
                key, _sep, value = line.partition("=")
                if key.strip().lower() == "include-system-site-packages":
                    return value.strip().lower() != "true"
    except OSError:
        return False
    # Without the setting, Python's site module includes them.
    return False


def _fail_missing(missing):
    """Name what is missing and how to install it, then exit.

    ``missing`` holds keys of ``_NAMES``.
    """
    print("Error: missing system dependencies: "
          + ", ".join(_NAMES[m] for m in missing), file=sys.stderr)
    manager = _package_manager()
    if manager is None:
        print("Install them with your package manager.", file=sys.stderr)
    else:
        packages = [p for m in missing for p in _PACKAGES[manager][m]]
        print("Install them with:", file=sys.stderr)
        print(f"  {_INSTALL[manager][1]} {' '.join(packages)}", file=sys.stderr)
    if _isolated_venv() and {"gi", "dbus"} & set(missing):
        print("This Python environment cannot see the system's Python "
              "packages, so it cannot use PyGObject or dbus-python even "
              "once they are installed. Install Clipman with:",
              file=sys.stderr)
        print("  pipx install --system-site-packages clipman-clipboard",
              file=sys.stderr)
    sys.exit(1)


def _check_dependencies():
    """Exit with an install hint when a system dependency is missing."""
    missing = []
    try:
        importlib.import_module("gi")
    except ImportError:
        missing += ["gi", "gtk"]
    try:
        importlib.import_module("dbus")
    except ImportError:
        missing.append("dbus")
    if shutil.which("wl-paste") is None:
        missing.append("wl-clipboard")
    if missing:
        _fail_missing(missing)


def _preflight_libadwaita():
    """Exit with a readable error when GTK 4 or libadwaita is missing, or
    libadwaita is older than 1.5."""
    import gi
    try:
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw
    except (ValueError, ImportError):
        # PyGObject is there, but not the GTK 4 or libadwaita typelib.
        _fail_missing(["gtk"])
        return
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
    """Toggle the popup of a running daemon, or start one. Return the
    exit status."""
    import dbus
    try:
        bus = dbus.SessionBus()
        proxy = bus.get_object("com.clipman.Daemon", "/com/clipman/Daemon")
        dbus.Interface(proxy, "com.clipman.Daemon").Toggle()
    except dbus.exceptions.DBusException:
        print("Clipman daemon is not running. Starting it now...")
        # The same press of the shortcut should open the popup too.
        return _start_daemon(show=True)
    return 0


def _start_daemon(show=False):
    """Run the daemon until it quits; return its exit status. With
    ``show``, it opens the popup once it has started.

    A failed start-up ends with a non-zero status, so systemd's
    Restart=on-failure tries again.
    """
    from clipman.app import ClipmanApp
    app = ClipmanApp()
    app.show_on_start = show
    status = app.run([])
    return status or app.exit_status


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
    """Parse arguments, check the system, then run or toggle. Return the
    exit status."""
    args = _parser().parse_args(argv)
    _check_dependencies()
    # The GLib loop must be the default before any bus connection, or a
    # daemon started by the toggle client never dispatches method calls.
    import dbus.mainloop.glib
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    _preflight_libadwaita()
    if args.command == "toggle":
        return _toggle()
    return _start_daemon()
