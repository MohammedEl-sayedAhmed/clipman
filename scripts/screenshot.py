#!/usr/bin/env python3
"""Headless screenshot harness for Clipman's GTK4 UI.

Renders the real ClipmanWindow (or preferences/snippets) to a PNG using
GTK's own renderer — no external screenshot tool required. Intended to be
run under Xvfb:

    xvfb-run -a python3 scripts/screenshot.py --out /tmp/main.png

It seeds a temp database with representative history so the popup looks
realistic, then captures the widget tree to a texture and saves it.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402


def _seed(db):
    db.add_entry("text", "https://github.com/MohammedEl-sayedAhmed/clipman")
    db.add_entry("text", "The quick brown fox jumps over the lazy dog.")
    db.add_entry(
        "text",
        "def hello():\n    print('a longer multi-line snippet of code')\n    return 42",
    )
    db.add_entry("text", "short note")
    db.add_entry("text", "another clipboard entry with some length to it")
    try:
        db.add_snippet("Signature", "Best regards,\nMohammed")
    except Exception:
        pass


def _capture(window, out_path, attempts_left, app):
    w = window.get_width()
    h = window.get_height()
    if (w == 0 or h == 0) and attempts_left > 0:
        GLib.timeout_add(120, _capture, window, out_path, attempts_left - 1, app)
        return False
    try:
        paintable = Gtk.WidgetPaintable.new(window)
        iw = paintable.get_intrinsic_width() or w or 420
        ih = paintable.get_intrinsic_height() or h or 600
        snapshot = Gtk.Snapshot.new()
        paintable.snapshot(snapshot, iw, ih)
        node = snapshot.to_node()
        if node is None:
            print("CAPTURE_FAIL: empty render node", file=sys.stderr)
            app.quit()
            return False
        renderer = window.get_native().get_renderer()
        texture = renderer.render_texture(node, None)
        texture.save_to_png(out_path)
        print(f"CAPTURE_OK {out_path} {texture.get_width()}x{texture.get_height()}")
    except Exception as e:  # noqa: BLE001
        print(f"CAPTURE_EXC {type(e).__name__}: {e}", file=sys.stderr)
    app.quit()
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/clipman-shot.png")
    ap.add_argument("--view", default="main", choices=["main", "preferences", "snippets"])
    ap.add_argument("--empty", action="store_true", help="don't seed history")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="clipman-shot-")
    data_dir = Path(tmp) / "clipman"
    patches = [
        patch("clipman.database.DATA_DIR", data_dir),
        patch("clipman.database.IMAGES_DIR", data_dir / "images"),
        patch("clipman.database.DB_PATH", data_dir / "clipman.db"),
    ]
    for p in patches:
        p.start()

    from clipman import database
    from clipman.window import ClipmanWindow

    db = database.ClipboardDB()
    if not args.empty:
        _seed(db)

    app = Adw.Application(application_id="com.clipman.Shot",
                         flags=Gio.ApplicationFlags.NON_UNIQUE)

    def on_activate(app):
        app.hold()
        window = ClipmanWindow(application=app, db=db, monitor=None)
        if args.view == "main":
            window.refresh()
            target = window
        elif args.view == "preferences":
            from clipman.preferences import ClipmanPreferences
            target = ClipmanPreferences(parent=window, db=db)
        else:
            from clipman.snippets_dialog import SnippetsDialog
            target = SnippetsDialog(parent=window, db=db)
        target.set_default_size(440, 620)
        target.present()
        GLib.timeout_add(500, _capture, target, args.out, 20, app)

    app.connect("activate", on_activate)
    app.run([])


if __name__ == "__main__":
    main()
