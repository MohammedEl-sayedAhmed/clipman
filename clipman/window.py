import subprocess
import time
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, Pango


class ClipmanWindow(Gtk.Window):
    def __init__(self, db, monitor):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.db = db
        self.monitor = monitor
        self._search_query = ""

        self.set_title("Clipman")
        self.set_default_size(420, 520)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_decorated(True)
        self.set_resizable(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_skip_taskbar_hint(True)

        self._apply_css()
        self._build_ui()

        self.connect("key-press-event", self._on_key_press)
        self.connect("delete-event", self._on_delete)

    def _apply_css(self):
        css = b"""
        .clipman-window {
            background-color: #2d2d2d;
            border-radius: 12px;
        }
        .clipman-header {
            background-color: #383838;
            border-radius: 12px 12px 0 0;
            padding: 8px;
        }
        .clipman-search {
            background-color: #404040;
            color: #ffffff;
            border: 1px solid #555555;
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 14px;
        }
        .clipman-search:focus {
            border-color: #3584e4;
        }
        .clip-row {
            background-color: #353535;
            border-radius: 8px;
            padding: 10px 12px;
            margin: 2px 6px;
        }
        .clip-row:hover {
            background-color: #404040;
        }
        .clip-text {
            color: #e0e0e0;
            font-size: 13px;
        }
        .clip-time {
            color: #888888;
            font-size: 11px;
        }
        .clip-type-badge {
            color: #3584e4;
            font-size: 10px;
            font-weight: bold;
        }
        .pin-button, .delete-button {
            background: none;
            border: none;
            padding: 4px;
            min-height: 24px;
            min-width: 24px;
        }
        .pin-button:hover, .delete-button:hover {
            background-color: #4a4a4a;
            border-radius: 4px;
        }
        .pinned {
            color: #f5c211;
        }
        .unpinned {
            color: #888888;
        }
        .clear-button {
            background-color: #c01c28;
            color: #ffffff;
            border: none;
            border-radius: 6px;
            padding: 6px 12px;
            font-size: 12px;
        }
        .clear-button:hover {
            background-color: #e01b24;
        }
        .empty-label {
            color: #888888;
            font-size: 16px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_ui(self):
        self.get_style_context().add_class("clipman-window")

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(main_box)

        # Header with search
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header_box.get_style_context().add_class("clipman-header")
        header_box.set_margin_start(4)
        header_box.set_margin_end(4)
        header_box.set_margin_top(4)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search clipboard history...")
        self.search_entry.get_style_context().add_class("clipman-search")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self._on_search_changed)
        header_box.pack_start(self.search_entry, True, True, 0)

        clear_btn = Gtk.Button(label="Clear All")
        clear_btn.get_style_context().add_class("clear-button")
        clear_btn.set_tooltip_text("Clear all unpinned entries")
        clear_btn.connect("clicked", self._on_clear_all)
        header_box.pack_end(clear_btn, False, False, 0)

        main_box.pack_start(header_box, False, False, 0)

        # Scrollable list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.set_activate_on_single_click(True)
        scrolled.add(self.listbox)

        main_box.pack_start(scrolled, True, True, 0)

        # Empty state
        self.empty_label = Gtk.Label(label="No clipboard entries yet.\nCopy something to get started!")
        self.empty_label.get_style_context().add_class("empty-label")
        self.empty_label.set_justify(Gtk.Justification.CENTER)
        self.empty_label.set_valign(Gtk.Align.CENTER)
        self.empty_label.set_vexpand(True)
        main_box.pack_start(self.empty_label, True, True, 0)

    def refresh(self):
        for child in self.listbox.get_children():
            self.listbox.remove(child)

        if self._search_query:
            entries = self.db.search(self._search_query)
        else:
            entries = self.db.get_entries(limit=50)

        if not entries:
            self.empty_label.show()
            self.listbox.get_parent().hide()
        else:
            self.empty_label.hide()
            self.listbox.get_parent().show()
            for entry in entries:
                row = self._create_row(entry)
                self.listbox.add(row)

        self.listbox.show_all()

    def _create_row(self, entry):
        row = Gtk.ListBoxRow()
        row.get_style_context().add_class("clip-row")

        outer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer_box.set_margin_top(2)
        outer_box.set_margin_bottom(2)

        # Content area (clickable)
        content_event = Gtk.EventBox()
        content_event.set_hexpand(True)
        content_event.connect("button-press-event", self._on_entry_click, entry)
        content_event.set_tooltip_text("Click to copy")

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        # Type badge + time
        meta_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        type_label = Gtk.Label(label=entry["content_type"].upper())
        type_label.get_style_context().add_class("clip-type-badge")
        type_label.set_halign(Gtk.Align.START)
        meta_box.pack_start(type_label, False, False, 0)

        time_label = Gtk.Label(label=self._format_time(entry["accessed_at"]))
        time_label.get_style_context().add_class("clip-time")
        time_label.set_halign(Gtk.Align.START)
        meta_box.pack_start(time_label, False, False, 0)

        content_box.pack_start(meta_box, False, False, 0)

        # Content preview
        if entry["content_type"] == "text":
            text = entry["content_text"] or ""
            preview = text[:150].replace("\n", " ")
            if len(text) > 150:
                preview += "..."
            label = Gtk.Label(label=preview)
            label.get_style_context().add_class("clip-text")
            label.set_halign(Gtk.Align.START)
            label.set_line_wrap(True)
            label.set_max_width_chars(45)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_lines(2)
            content_box.pack_start(label, False, False, 0)
        elif entry["content_type"] == "image" and entry["image_path"]:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    entry["image_path"], 64, 64, True
                )
                image = Gtk.Image.new_from_pixbuf(pixbuf)
                image.set_halign(Gtk.Align.START)
                content_box.pack_start(image, False, False, 0)
            except Exception:
                label = Gtk.Label(label="[Image]")
                label.get_style_context().add_class("clip-text")
                content_box.pack_start(label, False, False, 0)

        content_event.add(content_box)
        outer_box.pack_start(content_event, True, True, 0)

        # Action buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        btn_box.set_valign(Gtk.Align.CENTER)

        pin_btn = Gtk.Button(label="\u2605" if entry["pinned"] else "\u2606")
        pin_btn.get_style_context().add_class("pin-button")
        pin_btn.get_style_context().add_class("pinned" if entry["pinned"] else "unpinned")
        pin_btn.set_tooltip_text("Unpin" if entry["pinned"] else "Pin")
        pin_btn.connect("clicked", self._on_pin_click, entry["id"])
        btn_box.pack_start(pin_btn, False, False, 0)

        del_btn = Gtk.Button(label="\u2715")
        del_btn.get_style_context().add_class("delete-button")
        del_btn.set_tooltip_text("Delete")
        del_btn.connect("clicked", self._on_delete_click, entry["id"])
        btn_box.pack_start(del_btn, False, False, 0)

        outer_box.pack_end(btn_box, False, False, 0)

        row.add(outer_box)
        return row

    def _format_time(self, timestamp):
        diff = time.time() - timestamp
        if diff < 60:
            return "just now"
        elif diff < 3600:
            mins = int(diff / 60)
            return f"{mins}m ago"
        elif diff < 86400:
            hours = int(diff / 3600)
            return f"{hours}h ago"
        else:
            days = int(diff / 86400)
            return f"{days}d ago"

    def _on_entry_click(self, widget, event, entry):
        if self.monitor:
            self.monitor.set_self_copy(True)

        if entry["content_type"] == "text" and entry["content_text"]:
            proc = subprocess.Popen(
                ["wl-copy"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            proc.communicate(input=entry["content_text"].encode("utf-8"))
        elif entry["content_type"] == "image" and entry["image_path"]:
            subprocess.Popen(
                ["wl-copy", "--type", "image/png"],
                stdin=open(entry["image_path"], "rb"),
                stderr=subprocess.DEVNULL
            )

        self.db.conn.execute(
            "UPDATE entries SET accessed_at = ? WHERE id = ?",
            (time.time(), entry["id"])
        )
        self.db.conn.commit()
        self.hide()

    def _on_pin_click(self, button, entry_id):
        self.db.toggle_pin(entry_id)
        self.refresh()

    def _on_delete_click(self, button, entry_id):
        self.db.delete_entry(entry_id)
        self.refresh()

    def _on_clear_all(self, button):
        self.db.clear_unpinned()
        self.refresh()

    def _on_search_changed(self, entry):
        self._search_query = entry.get_text().strip()
        self.refresh()

    def _on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    def _on_delete(self, widget, event):
        self.hide()
        return True

    def toggle(self):
        if self.get_visible():
            self.hide()
        else:
            self.refresh()
            self.show_all()
            self.search_entry.grab_focus()
            self.present()
