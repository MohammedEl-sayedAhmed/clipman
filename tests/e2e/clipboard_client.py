#!/usr/bin/env python3
"""Copy text in the headless Shell, the way a user's app does.

Usage: clipboard_client.py TEXT [REPEAT]

Shows a small GTK 4 window, puts TEXT (REPEAT times over, for a big
copy) on the clipboard, and keeps serving it for a few seconds, so the
Shell extension can read it and send it on to the daemon.
"""

import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402


def main(text):
    Gtk.init()
    window = Gtk.Window(title="clipman-e2e-client")
    window.set_default_size(300, 100)
    loop = GLib.MainLoop()
    copied = []

    def copy(*_args):
        # The Shell may accept the clipboard only from the focused window,
        # so copy once the window is active (or after 5 s, and say so).
        if copied:
            return GLib.SOURCE_REMOVE
        copied.append(True)
        window.get_display().get_clipboard().set(text)
        print(f"copied, window active: {window.is_active()}", flush=True)
        GLib.timeout_add_seconds(4, loop.quit)
        return GLib.SOURCE_REMOVE

    window.connect("notify::is-active", lambda w, _p: w.is_active() and copy())
    window.present()
    GLib.timeout_add_seconds(5, copy)
    loop.run()


if __name__ == "__main__":
    main(sys.argv[1] * (int(sys.argv[2]) if len(sys.argv) > 2 else 1))
