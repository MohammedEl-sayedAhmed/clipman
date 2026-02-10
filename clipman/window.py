import datetime
import subprocess
import time
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango


WINDOW_OPACITY = 0.95


class ClipmanWindow(Gtk.Window):
    def __init__(self, db, monitor):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.db = db
        self.monitor = monitor
        self._search_query = ""
        self._active_filter = "all"
        self._ignore_focus_out = False

        self.set_title("Clipman")
        self.set_default_size(440, 560)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_decorated(True)
        self.set_resizable(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_skip_taskbar_hint(True)
        self.set_opacity(WINDOW_OPACITY)

        self._apply_css()
        self._build_ui()

        self.connect("key-press-event", self._on_key_press)
        self.connect("delete-event", self._on_delete)
        self.connect("focus-out-event", self._on_focus_out)

    # ── CSS ──────────────────────────────────────────────────────────

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
        .count-label {
            color: #666666;
            font-size: 11px;
        }

        /* Filter tabs */
        .filter-bar {
            background-color: #2d2d2d;
            padding: 2px 8px;
        }
        .filter-tab {
            background: none;
            background-image: none;
            border: none;
            color: #888888;
            font-size: 12px;
            padding: 4px 12px;
            min-height: 28px;
            border-bottom: 2px solid transparent;
        }
        .filter-tab:hover {
            color: #e0e0e0;
        }
        .filter-tab-active {
            background: none;
            background-image: none;
            border: none;
            color: #3584e4;
            font-size: 12px;
            font-weight: bold;
            padding: 4px 12px;
            min-height: 28px;
            border-bottom: 2px solid #3584e4;
        }

        /* Rows */
        .clip-row {
            background-color: #353535;
            border-radius: 8px;
            padding: 10px 12px;
            margin: 2px 6px;
        }
        .clip-row:hover {
            background-color: #404040;
        }
        row:selected .clip-row {
            background-color: #2a3a4a;
            border-left: 3px solid #3584e4;
        }
        .clip-text {
            color: #e0e0e0;
            font-size: 13px;
        }
        .clip-time {
            color: #888888;
            font-size: 11px;
        }
        .clip-chars {
            color: #666666;
            font-size: 10px;
        }
        .clip-type-badge {
            color: #3584e4;
            font-size: 10px;
            font-weight: bold;
        }

        /* Section headers */
        .section-header {
            color: #888888;
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
            padding: 8px 12px 4px 12px;
        }

        /* Buttons */
        .pin-button, .delete-button, .edit-button {
            background: none;
            border: none;
            padding: 4px;
            min-height: 24px;
            min-width: 24px;
        }
        .pin-button:hover, .delete-button:hover, .edit-button:hover {
            background: #4a4a4a;
            background-image: none;
            border-radius: 4px;
        }
        .pinned {
            color: #f5c211;
        }
        .unpinned {
            color: #888888;
        }
        .clear-button {
            font-size: 12px;
            padding: 6px 12px;
        }
        .add-snippet-button {
            font-size: 12px;
            padding: 6px 12px;
        }
        .empty-label {
            color: #888888;
            font-size: 16px;
        }

        /* Snippet name */
        .snippet-name {
            color: #e0e0e0;
            font-size: 13px;
            font-weight: bold;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    # ── Build UI ─────────────────────────────────────────────────────

    def _build_ui(self):
        self.get_style_context().add_class("clipman-window")

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(main_box)

        # Header: search + count + action button
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

        self.count_label = Gtk.Label(label="")
        self.count_label.get_style_context().add_class("count-label")
        header_box.pack_start(self.count_label, False, False, 0)

        self.clear_btn = Gtk.Button(label="Clear All")
        self.clear_btn.get_style_context().add_class("clear-button")
        self.clear_btn.get_style_context().add_class("destructive-action")
        self.clear_btn.set_tooltip_text("Clear all unpinned entries")
        self.clear_btn.connect("clicked", self._on_clear_all)
        header_box.pack_end(self.clear_btn, False, False, 0)

        self.add_snippet_btn = Gtk.Button(label="+ Add")
        self.add_snippet_btn.get_style_context().add_class("add-snippet-button")
        self.add_snippet_btn.get_style_context().add_class("suggested-action")
        self.add_snippet_btn.set_tooltip_text("Add a new snippet")
        self.add_snippet_btn.connect("clicked", self._on_add_snippet_clicked)
        self.add_snippet_btn.set_no_show_all(True)
        header_box.pack_end(self.add_snippet_btn, False, False, 0)

        main_box.pack_start(header_box, False, False, 0)

        # Filter tabs
        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        filter_box.get_style_context().add_class("filter-bar")
        self._filter_buttons = {}
        for fid, label in [("all", "All"), ("text", "Text"),
                           ("image", "Images"), ("snippets", "Snippets")]:
            btn = Gtk.Button(label=label)
            btn.get_style_context().add_class(
                "filter-tab-active" if fid == "all" else "filter-tab"
            )
            btn.connect("clicked", self._on_filter_clicked, fid)
            filter_box.pack_start(btn, False, False, 0)
            self._filter_buttons[fid] = btn
        main_box.pack_start(filter_box, False, False, 0)

        # Scrollable list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.BROWSE)
        self.listbox.set_activate_on_single_click(True)
        self.listbox.connect("row-activated", self._on_row_activated)
        scrolled.add(self.listbox)

        main_box.pack_start(scrolled, True, True, 0)

        # Empty state
        self.empty_label = Gtk.Label(
            label="No clipboard entries yet.\nCopy something to get started!"
        )
        self.empty_label.get_style_context().add_class("empty-label")
        self.empty_label.set_justify(Gtk.Justification.CENTER)
        self.empty_label.set_valign(Gtk.Align.CENTER)
        self.empty_label.set_vexpand(True)
        main_box.pack_start(self.empty_label, True, True, 0)

    # ── Refresh ──────────────────────────────────────────────────────

    def refresh(self):
        for child in self.listbox.get_children():
            self.listbox.remove(child)

        # Toggle header buttons
        is_snippets = self._active_filter == "snippets"
        self.clear_btn.set_visible(not is_snippets)
        self.add_snippet_btn.set_visible(is_snippets)

        if is_snippets:
            self._refresh_snippets()
        else:
            self._refresh_entries()

        self.listbox.show_all()

    def _refresh_entries(self):
        content_type = (
            None if self._active_filter == "all" else self._active_filter
        )

        if self._search_query:
            if content_type == "image":
                entries = []
            else:
                entries = self.db.search(self._search_query)
        else:
            entries = self.db.get_entries(limit=50, content_type=content_type)

        # Update count
        if self._search_query:
            self.count_label.set_text(f"{len(entries)} results")
        else:
            total = self.db.count_entries(content_type)
            self.count_label.set_text(f"{total} items")

        if not entries:
            self.empty_label.set_text(
                "No results found." if self._search_query
                else "No clipboard entries yet.\nCopy something to get started!"
            )
            self.empty_label.show()
            self.listbox.get_parent().hide()
            return

        self.empty_label.hide()
        self.listbox.get_parent().show()

        # Split pinned / unpinned
        pinned = [e for e in entries if e["pinned"]]
        unpinned = [e for e in entries if not e["pinned"]]

        # Pinned section
        if pinned:
            self.listbox.add(self._create_section_header("PINNED"))
            for entry in pinned:
                self.listbox.add(self._create_row(entry))

        # Date-grouped unpinned
        if unpinned:
            today = datetime.date.today()
            today_start = datetime.datetime.combine(
                today, datetime.time.min
            ).timestamp()
            yesterday_start = today_start - 86400

            current_group = None
            for entry in unpinned:
                ts = entry["accessed_at"]
                if ts >= today_start:
                    group = "TODAY"
                elif ts >= yesterday_start:
                    group = "YESTERDAY"
                else:
                    group = "OLDER"

                if group != current_group:
                    current_group = group
                    self.listbox.add(self._create_section_header(group))

                self.listbox.add(self._create_row(entry))

    def _refresh_snippets(self):
        if self._search_query:
            snippets = self.db.search_snippets(self._search_query)
        else:
            snippets = self.db.get_snippets()

        self.count_label.set_text(f"{len(snippets)} snippets")

        if not snippets:
            self.empty_label.set_text(
                "No snippets yet.\nClick '+ Add' to create one."
            )
            self.empty_label.show()
            self.listbox.get_parent().hide()
            return

        self.empty_label.hide()
        self.listbox.get_parent().show()

        for snippet in snippets:
            self.listbox.add(self._create_snippet_row(snippet))

    # ── Row builders ─────────────────────────────────────────────────

    def _create_section_header(self, text):
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.set_activatable(False)
        label = Gtk.Label(label=text)
        label.get_style_context().add_class("section-header")
        label.set_halign(Gtk.Align.START)
        row.add(label)
        return row

    def _create_row(self, entry):
        row = Gtk.ListBoxRow()
        row.entry_data = entry
        row.get_style_context().add_class("clip-row")

        outer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer_box.set_margin_top(2)
        outer_box.set_margin_bottom(2)

        # Content area (clickable)
        content_event = Gtk.EventBox()
        content_event.set_hexpand(True)
        content_event.connect("button-press-event", self._on_entry_click, entry)
        content_event.set_tooltip_text("Click to paste")

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        # Type badge + time + char count
        meta_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        type_label = Gtk.Label(label=entry["content_type"].upper())
        type_label.get_style_context().add_class("clip-type-badge")
        type_label.set_halign(Gtk.Align.START)
        meta_box.pack_start(type_label, False, False, 0)

        time_label = Gtk.Label(label=self._format_time(entry["accessed_at"]))
        time_label.get_style_context().add_class("clip-time")
        time_label.set_halign(Gtk.Align.START)
        meta_box.pack_start(time_label, False, False, 0)

        if entry["content_type"] == "text" and entry["content_text"]:
            chars = len(entry["content_text"])
            chars_label = Gtk.Label(
                label=f"{chars:,} chars" if chars >= 1000 else f"{chars} chars"
            )
            chars_label.get_style_context().add_class("clip-chars")
            chars_label.set_halign(Gtk.Align.START)
            meta_box.pack_start(chars_label, False, False, 0)

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
                image.set_has_tooltip(True)
                image.connect(
                    "query-tooltip", self._on_image_tooltip, entry["image_path"]
                )
                content_box.pack_start(image, False, False, 0)
            except (GLib.Error, OSError):
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
        pin_btn.get_style_context().add_class(
            "pinned" if entry["pinned"] else "unpinned"
        )
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

    def _create_snippet_row(self, snippet):
        row = Gtk.ListBoxRow()
        row.snippet_data = snippet
        row.get_style_context().add_class("clip-row")

        outer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer_box.set_margin_top(2)
        outer_box.set_margin_bottom(2)

        # Content area (clickable)
        content_event = Gtk.EventBox()
        content_event.set_hexpand(True)
        content_event.connect(
            "button-press-event", self._on_snippet_click, snippet
        )
        content_event.set_tooltip_text("Click to paste")

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        name_label = Gtk.Label(label=snippet["name"])
        name_label.get_style_context().add_class("snippet-name")
        name_label.set_halign(Gtk.Align.START)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        content_box.pack_start(name_label, False, False, 0)

        preview = snippet["content_text"][:120].replace("\n", " ")
        if len(snippet["content_text"]) > 120:
            preview += "..."
        preview_label = Gtk.Label(label=preview)
        preview_label.get_style_context().add_class("clip-text")
        preview_label.set_halign(Gtk.Align.START)
        preview_label.set_line_wrap(True)
        preview_label.set_max_width_chars(45)
        preview_label.set_ellipsize(Pango.EllipsizeMode.END)
        preview_label.set_lines(2)
        content_box.pack_start(preview_label, False, False, 0)

        content_event.add(content_box)
        outer_box.pack_start(content_event, True, True, 0)

        # Action buttons: edit + delete
        btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        btn_box.set_valign(Gtk.Align.CENTER)

        edit_btn = Gtk.Button(label="\u270E")
        edit_btn.get_style_context().add_class("edit-button")
        edit_btn.get_style_context().add_class("unpinned")
        edit_btn.set_tooltip_text("Edit")
        edit_btn.connect("clicked", self._on_snippet_edit_click, snippet)
        btn_box.pack_start(edit_btn, False, False, 0)

        del_btn = Gtk.Button(label="\u2715")
        del_btn.get_style_context().add_class("delete-button")
        del_btn.set_tooltip_text("Delete")
        del_btn.connect("clicked", self._on_snippet_delete_click, snippet["id"])
        btn_box.pack_start(del_btn, False, False, 0)

        outer_box.pack_end(btn_box, False, False, 0)

        row.add(outer_box)
        return row

    # ── Image tooltip ────────────────────────────────────────────────

    def _on_image_tooltip(self, widget, x, y, keyboard_mode, tooltip,
                          image_path):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                image_path, 200, 200, True
            )
            tooltip.set_icon(pixbuf)
            return True
        except (GLib.Error, OSError):
            return False

    # ── Helpers ──────────────────────────────────────────────────────

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

    # ── Paste / Copy ─────────────────────────────────────────────────

    def _paste_entry(self, entry):
        """Copy entry to clipboard, hide the window, and auto-paste."""
        if self.monitor:
            self.monitor.set_self_copy(True)

        if entry["content_type"] == "text" and entry["content_text"]:
            proc = subprocess.Popen(
                ["wl-copy"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            proc.communicate(input=entry["content_text"].encode("utf-8"))
        elif entry["content_type"] == "image" and entry["image_path"]:
            with open(entry["image_path"], "rb") as img_file:
                proc = subprocess.Popen(
                    ["wl-copy", "--type", "image/png"],
                    stdin=img_file,
                    stderr=subprocess.DEVNULL
                )
                proc.wait(timeout=5)

        self.db.update_accessed(entry["id"])
        self.hide()
        GLib.timeout_add(150, self._simulate_paste)

    def _paste_snippet(self, snippet):
        """Copy snippet text to clipboard, hide, and auto-paste."""
        if self.monitor:
            self.monitor.set_self_copy(True)

        proc = subprocess.Popen(
            ["wl-copy"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        proc.communicate(input=snippet["content_text"].encode("utf-8"))

        self.hide()
        GLib.timeout_add(150, self._simulate_paste)

    def _copy_only(self, data):
        """Copy to clipboard without auto-pasting (Shift+Enter)."""
        if self.monitor:
            self.monitor.set_self_copy(True)

        text = data.get("content_text")
        image_path = data.get("image_path")

        if text:
            proc = subprocess.Popen(
                ["wl-copy"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            proc.communicate(input=text.encode("utf-8"))
        elif image_path:
            with open(image_path, "rb") as img_file:
                proc = subprocess.Popen(
                    ["wl-copy", "--type", "image/png"],
                    stdin=img_file,
                    stderr=subprocess.DEVNULL
                )
                proc.wait(timeout=5)

        if data.get("id") and not data.get("name"):
            self.db.update_accessed(data["id"])
        self.hide()

    def _simulate_paste(self):
        """Ask the GNOME Shell extension to simulate Ctrl+V."""
        try:
            import dbus
            bus = dbus.SessionBus()
            proxy = bus.get_object(
                "com.clipman.Extension", "/com/clipman/Extension"
            )
            iface = dbus.Interface(proxy, "com.clipman.Extension")
            iface.SimulatePaste()
        except Exception:
            pass
        return False  # Don't repeat

    # ── Event handlers ───────────────────────────────────────────────

    def _on_entry_click(self, widget, event, entry):
        self._paste_entry(entry)

    def _on_snippet_click(self, widget, event, snippet):
        self._paste_snippet(snippet)

    def _on_row_activated(self, listbox, row):
        if row and hasattr(row, "entry_data"):
            self._paste_entry(row.entry_data)
        elif row and hasattr(row, "snippet_data"):
            self._paste_snippet(row.snippet_data)

    def _on_focus_out(self, widget, event):
        if self._ignore_focus_out:
            return False
        self.hide()
        return False

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

    def _on_filter_clicked(self, button, filter_id):
        if filter_id == self._active_filter:
            return
        for fid, btn in self._filter_buttons.items():
            ctx = btn.get_style_context()
            ctx.remove_class("filter-tab-active")
            ctx.remove_class("filter-tab")
            ctx.add_class(
                "filter-tab-active" if fid == filter_id else "filter-tab"
            )
        self._active_filter = filter_id
        self.refresh()

    # ── Snippet dialogs ──────────────────────────────────────────────

    def _on_add_snippet_clicked(self, button):
        self._show_snippet_dialog()

    def _on_snippet_edit_click(self, button, snippet):
        self._show_snippet_dialog(snippet)

    def _on_snippet_delete_click(self, button, snippet_id):
        self.db.delete_snippet(snippet_id)
        self.refresh()

    def _show_snippet_dialog(self, snippet=None):
        self._ignore_focus_out = True
        editing = snippet is not None

        dialog = Gtk.Dialog(
            title="Edit Snippet" if editing else "Add Snippet",
            parent=self,
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Save", Gtk.ResponseType.OK)
        dialog.set_default_size(360, 280)

        area = dialog.get_content_area()
        area.set_spacing(8)
        area.set_margin_start(12)
        area.set_margin_end(12)
        area.set_margin_top(12)

        name_label = Gtk.Label(label="Name:")
        name_label.set_halign(Gtk.Align.START)
        area.pack_start(name_label, False, False, 0)

        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("e.g., Email signature")
        if editing:
            name_entry.set_text(snippet["name"])
        area.pack_start(name_entry, False, False, 0)

        content_label = Gtk.Label(label="Content:")
        content_label.set_halign(Gtk.Align.START)
        area.pack_start(content_label, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_size_request(-1, 150)
        text_view = Gtk.TextView()
        text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        if editing:
            text_view.get_buffer().set_text(snippet["content_text"])
        scrolled.add(text_view)
        area.pack_start(scrolled, True, True, 0)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            name = name_entry.get_text().strip()
            buf = text_view.get_buffer()
            content = buf.get_text(
                buf.get_start_iter(), buf.get_end_iter(), False
            )
            if name and content:
                if editing:
                    self.db.update_snippet(snippet["id"], name, content)
                else:
                    self.db.add_snippet(name, content)

        dialog.destroy()
        self._ignore_focus_out = False
        self.refresh()

    # ── Key handling ─────────────────────────────────────────────────

    def _on_key_press(self, widget, event):
        # Escape — close
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True

        # Shift+Enter — copy without paste
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if event.state & Gdk.ModifierType.SHIFT_MASK:
                row = self.listbox.get_selected_row()
                if row and hasattr(row, "entry_data"):
                    self._copy_only(row.entry_data)
                    return True
                elif row and hasattr(row, "snippet_data"):
                    self._copy_only(row.snippet_data)
                    return True

        # Down arrow from search — move to first selectable entry
        if event.keyval == Gdk.KEY_Down and self.search_entry.has_focus():
            idx = 0
            row = self.listbox.get_row_at_index(idx)
            while row and not row.get_selectable():
                idx += 1
                row = self.listbox.get_row_at_index(idx)
            if row:
                self.listbox.select_row(row)
                row.grab_focus()
                return True

        # Only when a listbox row is focused (not search entry)
        if not self.search_entry.has_focus():
            # Delete — remove selected entry/snippet
            if event.keyval == Gdk.KEY_Delete:
                row = self.listbox.get_selected_row()
                if row and hasattr(row, "entry_data"):
                    self.db.delete_entry(row.entry_data["id"])
                    self.refresh()
                    return True
                elif row and hasattr(row, "snippet_data"):
                    self.db.delete_snippet(row.snippet_data["id"])
                    self.refresh()
                    return True

            # P — toggle pin on selected entry
            if event.keyval in (Gdk.KEY_p, Gdk.KEY_P):
                row = self.listbox.get_selected_row()
                if row and hasattr(row, "entry_data"):
                    self.db.toggle_pin(row.entry_data["id"])
                    self.refresh()
                    return True

        return False

    def _on_delete(self, widget, event):
        self.hide()
        return True

    # ── Toggle ───────────────────────────────────────────────────────

    def toggle(self):
        if self.get_visible():
            self.hide()
        else:
            self.show_all()
            self.refresh()
            self.search_entry.grab_focus()
            self.present()
