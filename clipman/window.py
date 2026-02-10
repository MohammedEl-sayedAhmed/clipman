import datetime
import subprocess
import time
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango


DEFAULT_OPACITY = 1.0
DEFAULT_FONT_SIZE = 12
DEFAULT_MAX_HISTORY = 500


class ClipmanWindow(Gtk.Window):
    def __init__(self, db, monitor):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.db = db
        self.monitor = monitor
        self._search_query = ""
        self._active_filter = "all"
        self._ignore_focus_out = False
        self._css_provider = None

        self.set_title("Clipman")
        self.set_default_size(380, 500)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_decorated(True)
        self.set_resizable(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_skip_taskbar_hint(True)

        # Load persisted settings
        saved_opacity = self.db.get_setting("opacity", str(DEFAULT_OPACITY))
        self._opacity = max(0.3, min(1.0, float(saved_opacity)))
        self.set_opacity(self._opacity)

        saved_font = self.db.get_setting("font_size", str(DEFAULT_FONT_SIZE))
        self._font_size = max(8, min(20, int(float(saved_font))))

        saved_max = self.db.get_setting("max_entries", str(DEFAULT_MAX_HISTORY))
        self._max_history = max(50, min(5000, int(float(saved_max))))

        self._apply_css()
        self._build_ui()

        self.connect("key-press-event", self._on_key_press)
        self.connect("delete-event", self._on_delete)
        self.connect("focus-out-event", self._on_focus_out)

    def _apply_css(self):
        fs = self._font_size
        css = f"""
        /* Base window */
        .clipman-window {{
            background-color: #181825;
            border-radius: 12px;
        }}

        /* Title bar (CSD headerbar) */
        .clipman-window headerbar {{
            background-color: #181825;
            background-image: none;
            color: #cdd6f4;
            border-bottom: 1px solid #313244;
            min-height: 28px;
            padding: 2px 6px;
        }}
        .clipman-window headerbar .title {{
            color: #cdd6f4;
            font-size: 12px;
            font-weight: bold;
        }}
        .clipman-window headerbar button {{
            background-color: transparent;
            background-image: none;
            color: #6c7086;
            border: none;
            min-height: 20px;
            min-width: 20px;
            padding: 2px;
        }}
        .clipman-window headerbar button:hover {{
            background-color: #313244;
            background-image: none;
            color: #cdd6f4;
            border-radius: 4px;
        }}

        /* Search bar */
        .clipman-header {{
            background-color: #1e1e2e;
            padding: 6px 8px;
        }}
        .clipman-search {{
            background-color: #313244;
            color: #cdd6f4;
            border: 1px solid #45475a;
            border-radius: 8px;
            padding: 4px 8px;
            font-size: {fs}px;
            min-height: 0;
        }}
        .clipman-search:focus {{
            border-color: #89b4fa;
        }}

        /* Gear button */
        .gear-button {{
            background-color: transparent;
            background-image: none;
            border: none;
            border-radius: 6px;
            color: #6c7086;
            padding: 2px 4px;
            min-height: 20px;
            min-width: 20px;
            font-size: 13px;
        }}
        .gear-button:hover {{
            background-color: #313244;
            background-image: none;
            color: #cdd6f4;
        }}

        /* Filter tabs */
        .filter-bar {{
            background-color: #1e1e2e;
            padding: 2px 8px 4px 8px;
        }}
        .filter-tab {{
            background-color: transparent;
            background-image: none;
            border: none;
            border-radius: 12px;
            color: #585b70;
            font-size: 11px;
            padding: 1px 10px;
            min-height: 20px;
            margin: 0 1px;
        }}
        .filter-tab:hover {{
            color: #a6adc8;
            background-color: #313244;
            background-image: none;
        }}
        .filter-tab-active {{
            background-color: #313244;
            background-image: none;
            border: none;
            border-radius: 12px;
            color: #89b4fa;
            font-size: 11px;
            font-weight: bold;
            padding: 1px 10px;
            min-height: 20px;
            margin: 0 1px;
        }}

        /* Settings panel */
        .settings-panel {{
            background-color: #1e1e2e;
            padding: 8px 12px;
            border-top: 1px solid #313244;
            border-bottom: 1px solid #313244;
        }}
        .settings-title {{
            color: #89b4fa;
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 1px;
        }}
        .settings-label {{
            color: #a6adc8;
            font-size: 11px;
            min-width: 80px;
        }}
        .settings-value {{
            color: #585b70;
            font-size: 10px;
            min-width: 32px;
        }}
        .settings-panel scale trough {{
            background-color: #45475a;
            min-height: 4px;
            border-radius: 2px;
        }}
        .settings-panel scale highlight {{
            background-color: #89b4fa;
            min-height: 4px;
            border-radius: 2px;
        }}
        .settings-panel scale slider {{
            background-color: #cdd6f4;
            min-height: 12px;
            min-width: 12px;
            border-radius: 6px;
        }}

        /* Section headers */
        .section-header {{
            color: #585b70;
            font-size: 9px;
            font-weight: bold;
            letter-spacing: 1px;
            padding: 6px 12px 2px 12px;
        }}

        /* Clipboard entry rows */
        .clip-row {{
            background-color: #1e1e2e;
            border-radius: 6px;
            padding: 5px 10px;
            margin: 1px 4px;
        }}
        .clip-row:hover {{
            background-color: #252536;
        }}
        row:selected .clip-row {{
            background-color: #1e3a5f;
            border-left: 2px solid #89b4fa;
        }}
        .clip-text {{
            color: #cdd6f4;
            font-size: {fs}px;
        }}
        .clip-time {{
            color: #585b70;
            font-size: 9px;
        }}
        .clip-chars {{
            color: #45475a;
            font-size: 9px;
        }}
        .clip-type-badge {{
            color: #89b4fa;
            font-size: 8px;
            font-weight: bold;
        }}

        /* Row action buttons */
        .pin-button, .delete-button, .edit-button {{
            background: none;
            background-image: none;
            border: none;
            padding: 0;
            min-height: 16px;
            min-width: 16px;
            font-size: 11px;
        }}
        .pin-button:hover, .delete-button:hover, .edit-button:hover {{
            background-color: rgba(255, 255, 255, 0.06);
            background-image: none;
            border-radius: 4px;
        }}
        .pinned {{
            color: #f9e2af;
        }}
        .unpinned {{
            color: #45475a;
        }}
        .delete-button {{
            color: #45475a;
        }}
        .delete-button:hover {{
            color: #f38ba8;
        }}

        /* Snippet name */
        .snippet-name {{
            color: #cdd6f4;
            font-size: {fs}px;
            font-weight: bold;
        }}

        /* Empty state */
        .empty-label {{
            color: #585b70;
            font-size: 13px;
        }}

        /* Bottom status bar */
        .status-bar {{
            background-color: #1e1e2e;
            padding: 4px 10px;
            border-top: 1px solid #313244;
        }}
        .status-count {{
            color: #585b70;
            font-size: 10px;
        }}
        .action-button {{
            background-color: transparent;
            background-image: none;
            border: 1px solid #45475a;
            border-radius: 6px;
            color: #a6adc8;
            font-size: 10px;
            padding: 1px 8px;
            min-height: 18px;
        }}
        .action-button:hover {{
            background-color: #313244;
            background-image: none;
            color: #cdd6f4;
        }}
        .action-button-danger {{
            background-color: transparent;
            background-image: none;
            border: 1px solid #45475a;
            border-radius: 6px;
            color: #f38ba8;
            font-size: 10px;
            padding: 1px 8px;
            min-height: 18px;
        }}
        .action-button-danger:hover {{
            background-color: rgba(243, 139, 168, 0.1);
            background-image: none;
            border-color: #f38ba8;
            color: #f38ba8;
        }}

        /* Snippet dialog */
        .snippet-dialog {{
            background-color: #1e1e2e;
        }}
        .snippet-dialog-content {{
            background-color: #1e1e2e;
        }}
        .snippet-dialog-label {{
            color: #a6adc8;
            font-size: 12px;
            font-weight: bold;
        }}
        .snippet-dialog-entry {{
            background-color: #313244;
            color: #cdd6f4;
            border: 1px solid #45475a;
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 12px;
        }}
        .snippet-dialog-entry:focus {{
            border-color: #89b4fa;
        }}
        .snippet-dialog-textview {{
            background-color: #313244;
            color: #cdd6f4;
            font-size: 12px;
            border-radius: 6px;
        }}
        .snippet-dialog-textview text {{
            background-color: #313244;
            color: #cdd6f4;
        }}
        .snippet-dialog .dialog-action-area button {{
            background-color: #313244;
            background-image: none;
            color: #a6adc8;
            border: 1px solid #45475a;
            border-radius: 6px;
            padding: 4px 14px;
            font-size: 12px;
        }}
        .snippet-dialog .dialog-action-area button:hover {{
            background-color: #45475a;
            background-image: none;
            color: #cdd6f4;
        }}
        .snippet-dialog .dialog-action-area button:last-child {{
            background-color: #89b4fa;
            background-image: none;
            color: #1e1e2e;
            border: none;
            font-weight: bold;
        }}
        .snippet-dialog .dialog-action-area button:last-child:hover {{
            background-color: #b4d0fb;
            background-image: none;
        }}
        .snippet-dialog headerbar {{
            background-color: #181825;
            background-image: none;
            color: #cdd6f4;
            border-bottom: 1px solid #313244;
        }}
        .snippet-dialog headerbar .title {{
            color: #cdd6f4;
        }}
        """
        screen = Gdk.Screen.get_default()
        if self._css_provider:
            Gtk.StyleContext.remove_provider_for_screen(screen, self._css_provider)
        self._css_provider = Gtk.CssProvider()
        self._css_provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            screen, self._css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    # -- Build UI ----------------------------------------------------------

    def _build_ui(self):
        self.get_style_context().add_class("clipman-window")

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(main_box)

        # -- Header: search + gear -----------------------------------------
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header.get_style_context().add_class("clipman-header")

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search...")
        self.search_entry.get_style_context().add_class("clipman-search")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self._on_search_changed)
        header.pack_start(self.search_entry, True, True, 0)

        gear_btn = Gtk.Button(label="\u2699")
        gear_btn.get_style_context().add_class("gear-button")
        gear_btn.set_tooltip_text("Settings")
        gear_btn.connect("clicked", self._on_gear_clicked)
        header.pack_end(gear_btn, False, False, 0)

        main_box.pack_start(header, False, False, 0)

        # -- Filter tabs ----------------------------------------------------
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

        # -- Settings panel (hidden by default) -----------------------------
        self.settings_panel = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=4
        )
        self.settings_panel.get_style_context().add_class("settings-panel")
        self.settings_panel.set_no_show_all(True)

        # Title
        title_label = Gtk.Label(label="SETTINGS")
        title_label.get_style_context().add_class("settings-title")
        title_label.set_halign(Gtk.Align.START)
        self.settings_panel.pack_start(title_label, False, False, 0)

        # Opacity row
        self._opacity_value_label = Gtk.Label(
            label=f"{int(self._opacity * 100)}%"
        )
        self._build_setting_row(
            self.settings_panel, "Opacity",
            0.3, 1.0, 0.05, self._opacity,
            self._on_opacity_changed, self._opacity_value_label
        )

        # Font size row
        self._font_value_label = Gtk.Label(label=f"{self._font_size}px")
        self._build_setting_row(
            self.settings_panel, "Font size",
            8, 20, 1, self._font_size,
            self._on_font_size_changed, self._font_value_label
        )

        # Max history row
        self._max_value_label = Gtk.Label(label=str(self._max_history))
        self._build_setting_row(
            self.settings_panel, "Max history",
            50, 5000, 50, self._max_history,
            self._on_max_history_changed, self._max_value_label
        )

        main_box.pack_start(self.settings_panel, False, False, 0)

        # -- Scrollable list ------------------------------------------------
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.BROWSE)
        self.listbox.set_activate_on_single_click(True)
        self.listbox.connect("row-activated", self._on_row_activated)
        scrolled.add(self.listbox)

        main_box.pack_start(scrolled, True, True, 0)

        # -- Empty state label ----------------------------------------------
        self.empty_label = Gtk.Label(
            label="No clipboard entries yet.\nCopy something to get started!"
        )
        self.empty_label.get_style_context().add_class("empty-label")
        self.empty_label.set_justify(Gtk.Justification.CENTER)
        self.empty_label.set_valign(Gtk.Align.CENTER)
        self.empty_label.set_vexpand(True)
        main_box.pack_start(self.empty_label, True, True, 0)

        # -- Bottom status bar ----------------------------------------------
        self.status_bar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6
        )
        self.status_bar.get_style_context().add_class("status-bar")

        self.count_label = Gtk.Label(label="")
        self.count_label.get_style_context().add_class("status-count")
        self.count_label.set_halign(Gtk.Align.START)
        self.status_bar.pack_start(self.count_label, True, True, 0)

        self.clear_btn = Gtk.Button(label="Clear All")
        self.clear_btn.get_style_context().add_class("action-button-danger")
        self.clear_btn.set_tooltip_text("Clear all unpinned entries")
        self.clear_btn.connect("clicked", self._on_clear_all)
        self.status_bar.pack_end(self.clear_btn, False, False, 0)

        self.add_snippet_btn = Gtk.Button(label="+ Add")
        self.add_snippet_btn.get_style_context().add_class("action-button")
        self.add_snippet_btn.set_tooltip_text("Add a new snippet")
        self.add_snippet_btn.connect("clicked", self._on_add_snippet_clicked)
        self.add_snippet_btn.set_no_show_all(True)
        self.status_bar.pack_end(self.add_snippet_btn, False, False, 0)

        main_box.pack_end(self.status_bar, False, False, 0)

    def _build_setting_row(self, parent, label_text, min_val, max_val, step,
                           current, callback, value_label):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        label = Gtk.Label(label=label_text)
        label.get_style_context().add_class("settings-label")
        label.set_halign(Gtk.Align.START)
        row.pack_start(label, False, False, 0)

        scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, min_val, max_val, step
        )
        scale.set_value(current)
        scale.set_draw_value(False)
        scale.set_hexpand(True)
        scale.connect("value-changed", callback)
        row.pack_start(scale, True, True, 0)

        value_label.get_style_context().add_class("settings-value")
        value_label.set_halign(Gtk.Align.END)
        row.pack_end(value_label, False, False, 0)

        parent.pack_start(row, False, False, 0)

    # -- Refresh -----------------------------------------------------------

    def refresh(self):
        for child in self.listbox.get_children():
            self.listbox.remove(child)

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

        pinned = [e for e in entries if e["pinned"]]
        unpinned = [e for e in entries if not e["pinned"]]

        if pinned:
            self.listbox.add(self._create_section_header("PINNED"))
            for entry in pinned:
                self.listbox.add(self._create_row(entry))

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

    # -- Row builders ------------------------------------------------------

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

        outer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        content_event = Gtk.EventBox()
        content_event.set_hexpand(True)
        content_event.connect("button-press-event", self._on_entry_click, entry)
        content_event.set_tooltip_text("Click to paste")

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)

        meta_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
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
                    entry["image_path"], 48, 48, True
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

        outer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        content_event = Gtk.EventBox()
        content_event.set_hexpand(True)
        content_event.connect(
            "button-press-event", self._on_snippet_click, snippet
        )
        content_event.set_tooltip_text("Click to paste")

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)

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

    # -- Image tooltip -----------------------------------------------------

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

    # -- Helpers -----------------------------------------------------------

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

    # -- Paste / Copy ------------------------------------------------------

    def _paste_entry(self, entry):
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
        if self.monitor:
            self.monitor.set_self_copy(True)

        proc = subprocess.Popen(
            ["wl-copy"], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        proc.communicate(input=snippet["content_text"].encode("utf-8"))

        self.hide()
        GLib.timeout_add(150, self._simulate_paste)

    def _copy_only(self, data):
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
        return False

    # -- Event handlers ----------------------------------------------------

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

    # -- Settings ----------------------------------------------------------

    def _on_gear_clicked(self, button):
        if self.settings_panel.get_visible():
            self.settings_panel.hide()
        else:
            self.settings_panel.show()
            self._show_all_children(self.settings_panel)

    def _show_all_children(self, widget):
        """Recursively show all children (bypasses set_no_show_all)."""
        if hasattr(widget, "get_children"):
            for child in widget.get_children():
                child.show()
                self._show_all_children(child)

    def _on_opacity_changed(self, scale):
        self._opacity = round(scale.get_value(), 2)
        self.set_opacity(self._opacity)
        self._opacity_value_label.set_text(f"{int(self._opacity * 100)}%")
        self.db.set_setting("opacity", str(self._opacity))

    def _on_font_size_changed(self, scale):
        self._font_size = int(scale.get_value())
        self._font_value_label.set_text(f"{self._font_size}px")
        self.db.set_setting("font_size", str(self._font_size))
        self._apply_css()
        self.refresh()

    def _on_max_history_changed(self, scale):
        self._max_history = int(scale.get_value())
        self._max_value_label.set_text(str(self._max_history))
        self.db.set_setting("max_entries", str(self._max_history))

    # -- Snippet dialogs ---------------------------------------------------

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

        # Hide the main window to avoid Wayland "unmap parent of popup" warnings
        self.hide()

        dialog = Gtk.Dialog(
            title="Edit Snippet" if editing else "Add Snippet",
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.get_style_context().add_class("snippet-dialog")
        dialog.set_keep_above(True)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Save", Gtk.ResponseType.OK)
        dialog.set_default_size(360, 280)

        area = dialog.get_content_area()
        area.get_style_context().add_class("snippet-dialog-content")
        area.set_spacing(8)
        area.set_margin_start(12)
        area.set_margin_end(12)
        area.set_margin_top(12)

        name_label = Gtk.Label(label="Name")
        name_label.get_style_context().add_class("snippet-dialog-label")
        name_label.set_halign(Gtk.Align.START)
        area.pack_start(name_label, False, False, 0)

        name_entry = Gtk.Entry()
        name_entry.get_style_context().add_class("snippet-dialog-entry")
        name_entry.set_placeholder_text("e.g., Email signature")
        if editing:
            name_entry.set_text(snippet["name"])
        area.pack_start(name_entry, False, False, 0)

        content_label = Gtk.Label(label="Content")
        content_label.get_style_context().add_class("snippet-dialog-label")
        content_label.set_halign(Gtk.Align.START)
        area.pack_start(content_label, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_size_request(-1, 150)
        text_view = Gtk.TextView()
        text_view.get_style_context().add_class("snippet-dialog-textview")
        text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        text_view.set_left_margin(6)
        text_view.set_right_margin(6)
        text_view.set_top_margin(4)
        text_view.set_bottom_margin(4)
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
        self.show_all()
        self.refresh()
        self.present()

    # -- Key handling ------------------------------------------------------

    def _on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True

        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if event.state & Gdk.ModifierType.SHIFT_MASK:
                row = self.listbox.get_selected_row()
                if row and hasattr(row, "entry_data"):
                    self._copy_only(row.entry_data)
                    return True
                elif row and hasattr(row, "snippet_data"):
                    self._copy_only(row.snippet_data)
                    return True

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

        if not self.search_entry.has_focus():
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

    # -- Toggle ------------------------------------------------------------

    def toggle(self):
        if self.get_visible():
            self.hide()
        else:
            self.show_all()
            self.refresh()
            self.search_entry.grab_focus()
            self.present()
