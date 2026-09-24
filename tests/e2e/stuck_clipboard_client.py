#!/usr/bin/env python3
"""Own the clipboard but never send the data, like an app that hangs.

Usage: stuck_clipboard_client.py COUNT

Shows a small GTK 4 window, then takes the clipboard COUNT times, 250 ms
apart, with content it never writes, prints "done", and waits to be
killed. Each read the Shell starts from it stays open until the Shell
gives up on it.
"""

import sys

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

# The streams the Shell asked us to write to. Kept, so they stay open.
PENDING = []


class StuckContent(Gdk.ContentProvider):
    def do_ref_formats(self):
        return Gdk.ContentFormats.new(["text/plain;charset=utf-8"])

    def do_write_mime_type_async(self, _mime, stream, *_rest):
        # Never write, never close, never finish.
        PENDING.append(stream)


def main(count):
    Gtk.init()
    window = Gtk.Window(title="clipman-e2e-stuck")
    window.set_default_size(300, 100)
    clipboard = window.get_display().get_clipboard()
    state = {"started": False, "taken": 0}

    def take():
        clipboard.set_content(StuckContent())
        state["taken"] += 1
        if state["taken"] < count:
            return GLib.SOURCE_CONTINUE
        print(f"done: took the clipboard {count} times, "
              f"{len(PENDING)} reads asked", flush=True)
        return GLib.SOURCE_REMOVE

    def start(*_args):
        # As in clipboard_client.py: copy once the window is active.
        if not state["started"]:
            state["started"] = True
            GLib.timeout_add(250, take)
        return GLib.SOURCE_REMOVE

    window.connect("notify::is-active", lambda w, _p: w.is_active() and start())
    window.present()
    GLib.timeout_add_seconds(5, start)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main(int(sys.argv[1]))
