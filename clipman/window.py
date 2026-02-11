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
DEFAULT_THEME = "dark"
DEFAULT_FONT_COLOR = ""

THEME_DARK = {
    "bg_crust": "#181825", "bg_base": "#1e1e2e", "bg_surface": "#252536",
    "bg_overlay": "#313244", "border": "#45475a",
    "text_primary": "#cdd6f4", "text_secondary": "#a6adc8",
    "text_muted": "#585b70", "text_faint": "#45475a",
    "headerbar_btn": "#6c7086",
    "accent": "#89b4fa", "accent_hover": "#b4d0fb", "accent_on": "#1e1e2e",
    "pin_color": "#f9e2af", "danger": "#f38ba8",
    "danger_bg": "rgba(243, 139, 168, 0.1)",
    "selected_bg": "#1e3a5f",
    "hover_overlay": "rgba(255, 255, 255, 0.06)",
}

THEME_LIGHT = {
    "bg_crust": "#dce0e8", "bg_base": "#eff1f5", "bg_surface": "#e6e9ef",
    "bg_overlay": "#ccd0da", "border": "#bcc0cc",
    "text_primary": "#11111b", "text_secondary": "#1e1e2e",
    "text_muted": "#4c4f69", "text_faint": "#5c5f77",
    "headerbar_btn": "#4c4f69",
    "accent": "#1e66f5", "accent_hover": "#2a6ff7", "accent_on": "#eff1f5",
    "pin_color": "#df8e1d", "danger": "#d20f39",
    "danger_bg": "rgba(210, 15, 57, 0.08)",
    "selected_bg": "#bdd6f2",
    "hover_overlay": "rgba(0, 0, 0, 0.05)",
}

THEMES = {"dark": THEME_DARK, "light": THEME_LIGHT}

FONT_COLOR_PRESETS = [
    ("Default", None),
    ("Green", "#40a02b"),
    ("Peach", "#fe640b"),
    ("Mauve", "#8839ef"),
    ("Pink", "#ea76cb"),
    ("Teal", "#179299"),
]


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

        saved_theme = self.db.get_setting("theme", DEFAULT_THEME)
        self._theme = saved_theme if saved_theme in THEMES else DEFAULT_THEME

        self._font_color = self.db.get_setting("font_color", DEFAULT_FONT_COLOR)

        self._apply_css()
        self._build_ui()

        self.connect("key-press-event", self._on_key_press)
        self.connect("delete-event", self._on_delete)
        self.connect("focus-out-event", self._on_focus_out)
        GLib.timeout_add_seconds(10, self._cleanup_sensitive)

    def _apply_css(self):
        fs = self._font_size
        t = dict(THEMES[self._theme])
        if self._font_color:
            t["text_primary"] = self._font_color
        css = f"""
        /* Base window */
        .clipman-window {{
            background-color: {t["bg_crust"]};
            border-radius: 12px;
        }}

        /* Title bar (CSD headerbar) */
        .clipman-window headerbar {{
            background-color: {t["bg_crust"]};
            background-image: none;
            color: {t["text_primary"]};
            border-bottom: 1px solid {t["bg_overlay"]};
            min-height: 28px;
            padding: 2px 6px;
        }}
        .clipman-window headerbar .title {{
            color: {t["text_primary"]};
            font-size: 12px;
            font-weight: bold;
        }}
        .clipman-window headerbar button {{
            background-color: transparent;
            background-image: none;
            color: {t["headerbar_btn"]};
            border: none;
            min-height: 20px;
            min-width: 20px;
            padding: 2px;
        }}
        .clipman-window headerbar button:hover {{
            background-color: {t["bg_overlay"]};
            background-image: none;
            color: {t["text_primary"]};
            border-radius: 4px;
        }}

        /* Search bar */
        .clipman-header {{
            background-color: {t["bg_base"]};
            padding: 6px 8px;
        }}
        .clipman-search {{
            background-color: {t["bg_overlay"]};
            color: {t["text_primary"]};
            border: 1px solid {t["border"]};
            border-radius: 8px;
            padding: 4px 8px;
            font-size: {fs}px;
            min-height: 0;
        }}
        .clipman-search:focus {{
            border-color: {t["accent"]};
        }}

        /* Gear button */
        .gear-button {{
            background-color: transparent;
            background-image: none;
            border: none;
            border-radius: 6px;
            color: {t["headerbar_btn"]};
            padding: 2px 6px;
            min-height: 24px;
            min-width: 24px;
            font-size: 17px;
        }}
        .gear-button:hover {{
            background-color: {t["bg_overlay"]};
            background-image: none;
            color: {t["text_primary"]};
        }}

        /* Filter tabs */
        .filter-bar {{
            background-color: {t["bg_base"]};
            padding: 2px 8px 4px 8px;
        }}
        .filter-tab {{
            background-color: transparent;
            background-image: none;
            border: none;
            border-radius: 12px;
            color: {t["text_secondary"]};
            font-size: 11px;
            padding: 1px 10px;
            min-height: 20px;
            margin: 0 1px;
        }}
        .filter-tab:hover {{
            color: {t["text_primary"]};
            background-color: {t["bg_overlay"]};
            background-image: none;
        }}
        .filter-tab-active {{
            background-color: {t["bg_overlay"]};
            background-image: none;
            border: none;
            border-radius: 12px;
            color: {t["accent"]};
            font-size: 11px;
            font-weight: bold;
            padding: 1px 10px;
            min-height: 20px;
            margin: 0 1px;
        }}

        /* Settings panel */
        .settings-panel {{
            background-color: {t["bg_base"]};
            padding: 8px 12px;
            border-top: 1px solid {t["bg_overlay"]};
            border-bottom: 1px solid {t["bg_overlay"]};
        }}
        .settings-title {{
            color: {t["accent"]};
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 1px;
        }}
        .settings-label {{
            color: {t["text_secondary"]};
            font-size: 11px;
            min-width: 80px;
        }}
        .settings-value {{
            color: {t["text_muted"]};
            font-size: 10px;
            min-width: 32px;
        }}
        .settings-panel scale trough {{
            background-color: {t["border"]};
            min-height: 4px;
            border-radius: 2px;
        }}
        .settings-panel scale highlight {{
            background-color: {t["accent"]};
            min-height: 4px;
            border-radius: 2px;
        }}
        .settings-panel scale slider {{
            background-color: {t["text_primary"]};
            min-height: 12px;
            min-width: 12px;
            border-radius: 6px;
        }}

        /* Theme toggle buttons */
        .theme-btn {{
            background-color: transparent;
            background-image: none;
            border: 1px solid {t["border"]};
            border-radius: 6px;
            color: {t["text_muted"]};
            font-size: 10px;
            padding: 1px 10px;
            min-height: 18px;
            margin: 0 2px;
        }}
        .theme-btn:hover {{
            color: {t["text_secondary"]};
            background-color: {t["bg_overlay"]};
            background-image: none;
        }}
        .theme-btn-active {{
            background-color: {t["accent"]};
            background-image: none;
            border: none;
            border-radius: 6px;
            color: {t["accent_on"]};
            font-size: 10px;
            font-weight: bold;
            padding: 1px 10px;
            min-height: 18px;
            margin: 0 2px;
        }}

        /* Font color swatches */
        .color-swatch {{
            min-height: 18px;
            min-width: 18px;
            border-radius: 9px;
            border: 2px solid transparent;
            padding: 0;
            margin: 0 1px;
            background-image: none;
        }}
        .color-swatch:hover {{
            border-color: {t["text_muted"]};
            background-image: none;
        }}
        .swatch-active {{
            border-color: {t["text_primary"]};
        }}
        .swatch-default {{
            background-color: transparent;
            border: 2px solid {t["text_muted"]};
            color: {t["text_muted"]};
            font-size: 9px;
            font-weight: bold;
        }}
        .swatch-green {{
            background-color: #40a02b;
        }}
        .swatch-peach {{
            background-color: #fe640b;
        }}
        .swatch-mauve {{
            background-color: #8839ef;
        }}
        .swatch-pink {{
            background-color: #ea76cb;
        }}
        .swatch-teal {{
            background-color: #179299;
        }}

        /* Section headers */
        .section-header {{
            color: {t["text_muted"]};
            font-size: 9px;
            font-weight: bold;
            letter-spacing: 1px;
            padding: 6px 12px 2px 12px;
        }}

        /* Listbox background */
        .clipman-window list {{
            background-color: {t["bg_crust"]};
        }}
        .clipman-window list row {{
            background-color: transparent;
        }}

        /* Clipboard entry rows */
        .clip-row {{
            background-color: {t["bg_base"]};
            border-radius: 6px;
            padding: 5px 10px;
            margin: 1px 4px;
        }}
        .clip-row:hover {{
            background-color: {t["bg_surface"]};
        }}
        row:selected .clip-row {{
            background-color: {t["selected_bg"]};
            border-left: 2px solid {t["accent"]};
        }}
        .clip-text {{
            color: {t["text_primary"]};
            font-size: {fs}px;
        }}
        .clip-time {{
            color: {t["text_muted"]};
            font-size: 9px;
        }}
        .clip-chars {{
            color: {t["text_faint"]};
            font-size: 9px;
        }}
        .clip-type-badge {{
            color: {t["accent"]};
            font-size: 8px;
            font-weight: bold;
        }}

        /* Row action buttons */
        .pin-button, .delete-button, .edit-button, .expand-button, .url-button {{
            background: none;
            background-image: none;
            border: none;
            padding: 0;
            min-height: 16px;
            min-width: 16px;
            font-size: 11px;
        }}
        .pin-button:hover, .delete-button:hover, .edit-button:hover,
        .expand-button:hover, .url-button:hover {{
            background-color: {t["hover_overlay"]};
            background-image: none;
            border-radius: 4px;
        }}
        .expand-button {{
            color: {t["text_muted"]};
        }}
        .url-button {{
            color: {t["accent"]};
        }}
        .pinned {{
            color: {t["pin_color"]};
        }}
        .unpinned {{
            color: {t["text_muted"]};
        }}
        .delete-button {{
            color: {t["text_muted"]};
        }}
        .delete-button:hover {{
            color: {t["danger"]};
        }}

        /* Snippet name */
        .snippet-name {{
            color: {t["text_primary"]};
            font-size: {fs}px;
            font-weight: bold;
        }}

        /* Empty state */
        .empty-label {{
            color: {t["text_muted"]};
            font-size: 13px;
        }}

        /* Bottom status bar */
        .status-bar {{
            background-color: {t["bg_base"]};
            padding: 4px 10px;
            border-top: 1px solid {t["bg_overlay"]};
        }}
        .status-count {{
            color: {t["text_muted"]};
            font-size: 10px;
        }}
        .action-button {{
            background-color: transparent;
            background-image: none;
            border: 1px solid {t["border"]};
            border-radius: 6px;
            color: {t["text_secondary"]};
            font-size: 10px;
            padding: 1px 8px;
            min-height: 18px;
        }}
        .action-button:hover {{
            background-color: {t["bg_overlay"]};
            background-image: none;
            color: {t["text_primary"]};
        }}
        .action-button-danger {{
            background-color: transparent;
            background-image: none;
            border: 1px solid {t["border"]};
            border-radius: 6px;
            color: {t["danger"]};
            font-size: 10px;
            padding: 1px 8px;
            min-height: 18px;
        }}
        .action-button-danger:hover {{
            background-color: {t["danger_bg"]};
            background-image: none;
            border-color: {t["danger"]};
            color: {t["danger"]};
        }}

        /* Incognito button */
        .incognito-btn {{
            background-color: transparent;
            background-image: none;
            border: none;
            border-radius: 6px;
            color: {t["text_muted"]};
            font-size: 14px;
            padding: 1px 4px;
            min-height: 18px;
            min-width: 18px;
        }}
        .incognito-btn:hover {{
            background-color: {t["bg_overlay"]};
            background-image: none;
        }}
        .incognito-active {{
            background-color: {t["danger_bg"]};
            background-image: none;
            border: 1px solid {t["danger"]};
            border-radius: 6px;
            color: {t["danger"]};
            font-size: 14px;
            padding: 1px 4px;
            min-height: 18px;
            min-width: 18px;
        }}
        .incognito-active:hover {{
            background-color: {t["danger"]};
            background-image: none;
            color: {t["accent_on"]};
        }}

        /* Sensitive entries */
        .sensitive-badge {{
            color: {t["danger"]};
            font-size: 9px;
        }}
        .sensitive-row {{
            opacity: 0.7;
        }}

        /* Backup/Restore buttons */
        .backup-btn {{
            background-color: transparent;
            background-image: none;
            border: 1px solid {t["border"]};
            border-radius: 6px;
            color: {t["text_secondary"]};
            font-size: 10px;
            padding: 1px 10px;
            min-height: 18px;
            margin: 0 2px;
        }}
        .backup-btn:hover {{
            background-color: {t["bg_overlay"]};
            background-image: none;
            color: {t["text_primary"]};
        }}

        /* Snippet dialog */
        .snippet-dialog {{
            background-color: {t["bg_base"]};
        }}
        .snippet-dialog-content {{
            background-color: {t["bg_base"]};
        }}
        .snippet-dialog-label {{
            color: {t["text_secondary"]};
            font-size: 12px;
            font-weight: bold;
        }}
        .snippet-dialog-entry {{
            background-color: {t["bg_overlay"]};
            color: {t["text_primary"]};
            border: 1px solid {t["border"]};
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 12px;
        }}
        .snippet-dialog-entry:focus {{
            border-color: {t["accent"]};
        }}
        .snippet-dialog-textview {{
            background-color: {t["bg_overlay"]};
            color: {t["text_primary"]};
            font-size: 12px;
            border-radius: 6px;
        }}
        .snippet-dialog-textview text {{
            background-color: {t["bg_overlay"]};
            color: {t["text_primary"]};
        }}
        .snippet-dialog .dialog-action-area button {{
            background-color: {t["bg_overlay"]};
            background-image: none;
            color: {t["text_secondary"]};
            border: 1px solid {t["border"]};
            border-radius: 6px;
            padding: 4px 14px;
            font-size: 12px;
        }}
        .snippet-dialog .dialog-action-area button:hover {{
            background-color: {t["border"]};
            background-image: none;
            color: {t["text_primary"]};
        }}
        .snippet-dialog .dialog-action-area button:last-child {{
            background-color: {t["accent"]};
            background-image: none;
            color: {t["accent_on"]};
            border: none;
            font-weight: bold;
        }}
        .snippet-dialog .dialog-action-area button:last-child:hover {{
            background-color: {t["accent_hover"]};
            background-image: none;
        }}
        .snippet-dialog headerbar {{
            background-color: {t["bg_crust"]};
            background-image: none;
            color: {t["text_primary"]};
            border-bottom: 1px solid {t["bg_overlay"]};
        }}
        .snippet-dialog headerbar .title {{
            color: {t["text_primary"]};
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

        # Theme toggle row
        theme_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        theme_label = Gtk.Label(label="Theme")
        theme_label.get_style_context().add_class("settings-label")
        theme_label.set_halign(Gtk.Align.START)
        theme_row.pack_start(theme_label, False, False, 0)
        theme_spacer = Gtk.Box()
        theme_spacer.set_hexpand(True)
        theme_row.pack_start(theme_spacer, True, True, 0)
        self._theme_buttons = {}
        for tid, tlabel in [("dark", "Dark"), ("light", "Light")]:
            btn = Gtk.Button(label=tlabel)
            cls = "theme-btn-active" if tid == self._theme else "theme-btn"
            btn.get_style_context().add_class(cls)
            btn.connect("clicked", self._on_theme_changed, tid)
            theme_row.pack_start(btn, False, False, 0)
            self._theme_buttons[tid] = btn
        self.settings_panel.pack_start(theme_row, False, False, 0)

        # Font color swatch row
        color_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        color_label = Gtk.Label(label="Font color")
        color_label.get_style_context().add_class("settings-label")
        color_label.set_halign(Gtk.Align.START)
        color_row.pack_start(color_label, False, False, 0)
        color_spacer = Gtk.Box()
        color_spacer.set_hexpand(True)
        color_row.pack_start(color_spacer, True, True, 0)
        self._color_buttons = []
        for name, hex_val in FONT_COLOR_PRESETS:
            btn = Gtk.Button(label="A" if hex_val is None else "")
            btn.set_tooltip_text(name)
            btn.get_style_context().add_class("color-swatch")
            btn.get_style_context().add_class(f"swatch-{name.lower()}")
            current = self._font_color or None
            if hex_val == current:
                btn.get_style_context().add_class("swatch-active")
            elif hex_val is None and not self._font_color:
                btn.get_style_context().add_class("swatch-active")
            btn.connect("clicked", self._on_font_color_changed, hex_val)
            color_row.pack_start(btn, False, False, 0)
            self._color_buttons.append((btn, hex_val))
        self.settings_panel.pack_start(color_row, False, False, 0)

        # Backup/Restore row
        backup_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        backup_label = Gtk.Label(label="Data")
        backup_label.get_style_context().add_class("settings-label")
        backup_label.set_halign(Gtk.Align.START)
        backup_row.pack_start(backup_label, False, False, 0)
        backup_spacer = Gtk.Box()
        backup_spacer.set_hexpand(True)
        backup_row.pack_start(backup_spacer, True, True, 0)
        backup_btn = Gtk.Button(label="Backup")
        backup_btn.get_style_context().add_class("backup-btn")
        backup_btn.set_tooltip_text("Export clipboard database")
        backup_btn.connect("clicked", self._on_backup_clicked)
        backup_row.pack_start(backup_btn, False, False, 0)
        restore_btn = Gtk.Button(label="Restore")
        restore_btn.get_style_context().add_class("backup-btn")
        restore_btn.set_tooltip_text("Import clipboard database")
        restore_btn.connect("clicked", self._on_restore_clicked)
        backup_row.pack_start(restore_btn, False, False, 0)
        self.settings_panel.pack_start(backup_row, False, False, 0)

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

        self.incognito_btn = Gtk.Button(label="\U0001f441")
        self.incognito_btn.get_style_context().add_class("incognito-btn")
        self.incognito_btn.set_tooltip_text("Incognito mode: OFF")
        self.incognito_btn.connect("clicked", self._on_incognito_toggle)
        self.status_bar.pack_start(self.incognito_btn, False, False, 0)

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
        label.set_xalign(0)
        row.add(label)
        return row

    def _create_row(self, entry):
        row = Gtk.ListBoxRow()
        row.entry_data = entry
        row.get_style_context().add_class("clip-row")
        if entry.get("sensitive"):
            row.get_style_context().add_class("sensitive-row")

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

        if entry.get("sensitive"):
            sens_label = Gtk.Label(label="\U0001f6e1")
            sens_label.get_style_context().add_class("sensitive-badge")
            sens_label.set_halign(Gtk.Align.START)
            meta_box.pack_start(sens_label, False, False, 0)

        content_box.pack_start(meta_box, False, False, 0)

        if entry["content_type"] == "text":
            text = entry["content_text"] or ""
            preview = text[:150].replace("\n", " ")
            if len(text) > 150:
                preview += "..."
            label = Gtk.Label(label=preview)
            label.get_style_context().add_class("clip-text")
            label.set_halign(Gtk.Align.START)
            label.set_xalign(0)
            label.set_line_wrap(True)
            label.set_max_width_chars(45)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_lines(2)
            row.full_text = text
            row.preview_text = preview
            row.content_label = label
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

        if entry["content_type"] == "text" and entry["content_text"]:
            edit_btn = Gtk.Button(label="\u270E")
            edit_btn.get_style_context().add_class("edit-button")
            edit_btn.get_style_context().add_class("unpinned")
            edit_btn.set_tooltip_text("Edit")
            edit_btn.connect("clicked", self._on_edit_entry_click, entry)
            btn_box.pack_start(edit_btn, False, False, 0)

            if len(entry["content_text"]) > 150:
                expand_btn = Gtk.Button(label="\u25BC")
                expand_btn.get_style_context().add_class("expand-button")
                expand_btn.set_tooltip_text("Expand")
                expand_btn.connect("clicked", self._on_expand_click, row)
                btn_box.pack_start(expand_btn, False, False, 0)

            url = self._detect_url(entry["content_text"])
            if url:
                url_btn = Gtk.Button(label="\u2197")
                url_btn.get_style_context().add_class("url-button")
                url_btn.set_tooltip_text("Open URL")
                url_btn.connect("clicked", self._on_open_url_click, url)
                btn_box.pack_start(url_btn, False, False, 0)

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
        name_label.set_xalign(0)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        content_box.pack_start(name_label, False, False, 0)

        preview = snippet["content_text"][:120].replace("\n", " ")
        if len(snippet["content_text"]) > 120:
            preview += "..."
        preview_label = Gtk.Label(label=preview)
        preview_label.get_style_context().add_class("clip-text")
        preview_label.set_halign(Gtk.Align.START)
        preview_label.set_xalign(0)
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

    def _on_theme_changed(self, button, theme_id):
        if theme_id == self._theme:
            return
        self._theme = theme_id
        self.db.set_setting("theme", theme_id)
        for tid, btn in self._theme_buttons.items():
            ctx = btn.get_style_context()
            ctx.remove_class("theme-btn-active")
            ctx.remove_class("theme-btn")
            ctx.add_class("theme-btn-active" if tid == theme_id else "theme-btn")
        self._apply_css()
        self.refresh()

    def _on_font_color_changed(self, button, hex_val):
        self._font_color = hex_val or ""
        self.db.set_setting("font_color", self._font_color)
        for btn, val in self._color_buttons:
            ctx = btn.get_style_context()
            ctx.remove_class("swatch-active")
            if val == hex_val:
                ctx.add_class("swatch-active")
        self._apply_css()
        self.refresh()

    def _cleanup_sensitive(self):
        deleted = self.db.delete_expired_sensitive()
        if deleted > 0 and self.get_visible():
            self.refresh()
        return True

    def _on_incognito_toggle(self, button):
        ctx = button.get_style_context()
        if self.monitor and self.monitor._incognito:
            self.monitor.set_incognito(False)
            ctx.remove_class("incognito-active")
            ctx.add_class("incognito-btn")
            button.set_tooltip_text("Incognito mode: OFF")
        else:
            if self.monitor:
                self.monitor.set_incognito(True)
            ctx.remove_class("incognito-btn")
            ctx.add_class("incognito-active")
            button.set_tooltip_text("Incognito mode: ON — clipboard not recorded")

    # -- Expand / Edit / URL handlers --------------------------------------

    def _on_expand_click(self, button, row):
        if getattr(row, '_is_expanded', False):
            row.content_label.set_text(row.preview_text)
            row.content_label.set_lines(2)
            row.content_label.set_ellipsize(Pango.EllipsizeMode.END)
            button.set_label("\u25BC")
            button.set_tooltip_text("Expand")
            row._is_expanded = False
        else:
            show = row.full_text[:2000]
            if len(row.full_text) > 2000:
                show += f"\n\u2026 ({len(row.full_text):,} total chars)"
            row.content_label.set_text(show)
            row.content_label.set_lines(20)
            row.content_label.set_ellipsize(Pango.EllipsizeMode.NONE)
            button.set_label("\u25B2")
            button.set_tooltip_text("Collapse")
            row._is_expanded = True

    def _on_edit_entry_click(self, button, entry):
        self._show_edit_dialog(entry)

    def _show_edit_dialog(self, entry):
        self._ignore_focus_out = True
        self.hide()

        dialog = Gtk.Dialog(
            title="Edit Entry",
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

        label = Gtk.Label(label="Content")
        label.get_style_context().add_class("snippet-dialog-label")
        label.set_halign(Gtk.Align.START)
        area.pack_start(label, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_size_request(-1, 200)
        text_view = Gtk.TextView()
        text_view.get_style_context().add_class("snippet-dialog-textview")
        text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        text_view.set_left_margin(6)
        text_view.set_right_margin(6)
        text_view.set_top_margin(4)
        text_view.set_bottom_margin(4)
        text_view.get_buffer().set_text(entry["content_text"] or "")
        scrolled.add(text_view)
        area.pack_start(scrolled, True, True, 0)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            buf = text_view.get_buffer()
            new_text = buf.get_text(
                buf.get_start_iter(), buf.get_end_iter(), False
            )
            if new_text and new_text != entry["content_text"]:
                self.db.update_entry_text(entry["id"], new_text)

        dialog.destroy()
        self._ignore_focus_out = False
        self.show_all()
        self.refresh()
        self.present()

    @staticmethod
    def _detect_url(text):
        t = text.strip().split("\n")[0].strip()
        if t.startswith(("http://", "https://")) and " " not in t:
            return t
        if t.startswith("www.") and " " not in t:
            return "https://" + t
        return None

    def _on_open_url_click(self, button, url):
        try:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except OSError:
            pass

    # -- Backup / Restore --------------------------------------------------

    def _on_backup_clicked(self, button):
        self._ignore_focus_out = True
        dialog = Gtk.FileChooserDialog(
            title="Backup Clipboard Database",
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.set_keep_above(True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Save", Gtk.ResponseType.OK)
        dialog.set_current_name("clipman-backup.db")
        dialog.set_do_overwrite_confirmation(True)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            try:
                self.db.export_backup(path)
            except Exception:
                pass
        dialog.destroy()
        self._ignore_focus_out = False

    def _on_restore_clicked(self, button):
        self._ignore_focus_out = True
        dialog = Gtk.FileChooserDialog(
            title="Restore Clipboard Database",
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.set_keep_above(True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Open", Gtk.ResponseType.OK)

        db_filter = Gtk.FileFilter()
        db_filter.set_name("Database files")
        db_filter.add_pattern("*.db")
        dialog.add_filter(db_filter)

        all_filter = Gtk.FileFilter()
        all_filter.set_name("All files")
        all_filter.add_pattern("*")
        dialog.add_filter(all_filter)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            try:
                self.db.import_backup(path)
                self.refresh()
            except Exception:
                pass
        dialog.destroy()
        self._ignore_focus_out = False

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
