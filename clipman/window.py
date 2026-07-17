"""GTK 4 + libadwaita popup window — Phase 1 of the GTK 3 -> 4 port.

Phase 1 scope: boots, shows the popup, lists clips, searches, pastes. The
preferences window, snippets editor, full edge states, and refreshed tests
land in follow-up PRs. The three public methods used by dbus_service +
the integration callers (``toggle``, ``refresh``, ``refresh_update_banner``)
are preserved so the rest of the daemon keeps resolving against this
module without changes.
"""

import logging
import os
import re
import subprocess
import time
from datetime import date, datetime, timedelta
from string import Template

import gi

# Direct submodule imports — avoid ``from clipman import …`` which
# CodeQL flags as a cyclic import (window <-> clipman package).
from gettext import gettext as _

import clipman.updates as updates
from clipman._version import __version__

logger = logging.getLogger(__name__)

# Module-level GTK4 binding. Wrapped because some CI sandboxes ship a
# placeholder ``gi`` shim that lacks ``require_version`` (or has the
# typelibs unavailable). Re-raise as RuntimeError so importers can
# guard with a single except clause instead of catching three classes.
try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Gdk", "4.0")
    from gi.repository import (
        Adw,
        Gdk,
        GdkPixbuf,
        Gio,
        GLib,
        GObject,
        Gtk,
        Pango,
    )
except (AttributeError, ValueError, ImportError) as e:
    raise RuntimeError(
        "GTK 4 + libadwaita not available: %s" % e
    ) from e

DEFAULT_FONT_SIZE = 12
DEFAULT_THEME = "dark"
DEFAULT_SENSITIVE_TIMEOUT = 30

# Catppuccin palette overrides for libadwaita @-tokens. Mirrors
# docs/design/tokens.css so the live app matches the marketing mockup
# regardless of the user's system Adwaita accent. Values are the
# canonical Catppuccin Mocha (dark) and Latte (light) palettes.
_CATPPUCCIN_MOCHA = {
    "window_bg_color":     "#1e1e2e",
    "view_bg_color":       "#1e1e2e",
    "headerbar_bg_color":  "#181825",
    "card_bg_color":       "#313244",
    "dialog_bg_color":     "#1e1e2e",
    "popover_bg_color":    "#313244",
    "window_fg_color":     "#cdd6f4",
    "view_fg_color":       "#cdd6f4",
    "headerbar_fg_color":  "#cdd6f4",
    "card_fg_color":       "#cdd6f4",
    "dialog_fg_color":     "#cdd6f4",
    "popover_fg_color":    "#cdd6f4",
    "accent_color":        "#cba6f7",
    "accent_bg_color":     "#cba6f7",
    "accent_fg_color":     "#1e1e2e",
    "destructive_color":   "#f38ba8",
    "destructive_bg_color":"#f38ba8",
    "destructive_fg_color":"#1e1e2e",
    "success_color":       "#a6e3a1",
    "success_bg_color":    "#a6e3a1",
    "success_fg_color":    "#1e1e2e",
    "warning_color":       "#f9e2af",
    "warning_bg_color":    "#f9e2af",
    "warning_fg_color":    "#1e1e2e",
    "error_color":         "#f38ba8",
    "error_bg_color":      "#f38ba8",
    "error_fg_color":      "#1e1e2e",
}
_CATPPUCCIN_LATTE = {
    "window_bg_color":     "#eff1f5",
    "view_bg_color":       "#eff1f5",
    "headerbar_bg_color":  "#e6e9ef",
    "card_bg_color":       "#ccd0da",
    "dialog_bg_color":     "#eff1f5",
    "popover_bg_color":    "#ccd0da",
    "window_fg_color":     "#4c4f69",
    "view_fg_color":       "#4c4f69",
    "headerbar_fg_color":  "#4c4f69",
    "card_fg_color":       "#4c4f69",
    "dialog_fg_color":     "#4c4f69",
    "popover_fg_color":    "#4c4f69",
    "accent_color":        "#8839ef",
    "accent_bg_color":     "#8839ef",
    "accent_fg_color":     "#eff1f5",
    "destructive_color":   "#d20f39",
    "destructive_bg_color":"#d20f39",
    "destructive_fg_color":"#eff1f5",
    "success_color":       "#40a02b",
    "success_bg_color":    "#40a02b",
    "success_fg_color":    "#eff1f5",
    "warning_color":       "#df8e1d",
    "warning_bg_color":    "#df8e1d",
    "warning_fg_color":    "#eff1f5",
    "error_color":         "#d20f39",
    "error_bg_color":      "#d20f39",
    "error_fg_color":      "#eff1f5",
}
DEFAULT_FONT_COLOR = "default"

# Fallback CSS token used when the user picked the "default" preset.
# Keeps the .clip-row .title colour aligned with libadwaita's card fg.
_DEFAULT_FONT_COLOR_TOKEN = "@card_fg_color"

# Incremental list fill (see ClipmanWindow.refresh): paint this many rows
# immediately, then stream the remaining history in idle batches of this
# size so a large history never freezes the popup on open / filter switch.
_FILL_FIRST = 30
_FILL_BATCH = 60

# Per-row visual type -> symbolic icon + coloured tile (mockup parity,
# docs/design/main-window.html). Text entries are further classified into
# link / code so the tile colour is a quick scannable type hint.
ROW_TYPE_ICONS = {
    "text": "text-x-generic-symbolic",
    "link": "insert-link-symbolic",
    "code": "utilities-terminal-symbolic",
    "image": "image-x-generic-symbolic",
    "snip": "emblem-documents-symbolic",
}
_TILE_TYPE_CLASSES = ("type-text", "type-link", "type-code",
                      "type-image", "type-snip")

# Tile colours, keyed to the @define-color tokens emitted by
# _type_color_block(); values mirror docs/design/tokens.css (Catppuccin
# Mocha for dark, the mockup's high-contrast set for light).
_TYPE_COLORS_DARK = {
    "type_text": "#89b4fa",
    "type_link": "#74c7ec",
    "type_code": "#94e2d5",
    "type_image": "#cba6f7",
    "type_snip": "#f9e2af",
}
_TYPE_COLORS_LIGHT = {
    "type_text": "#2563eb",
    "type_link": "#0891b2",
    "type_code": "#0d9488",
    "type_image": "#9333ea",
    "type_snip": "#b45309",
}

_URL_RE = re.compile(r"^(https?://|www\.)\S+$", re.IGNORECASE)
# Conservative code detection: only strong, code-specific signals so plain
# notes ("cd cabinet", "from the shop") don't get mislabeled as code.
_CODE_HINT_RE = re.compile(
    r"^\s*(def |class |function |import |#!/|\$ )"   # code-y line starts
    r"|[{};]\s*$"                                     # line ends in ; { }
    r"|=>|</[a-zA-Z]",                               # arrows, closing tags
    re.MULTILINE,
)


def _classify_text(text):
    """Classify a text entry into 'link', 'code', or 'text' for its tile."""
    stripped = (text or "").strip()
    if not stripped:
        return "text"
    if "\n" not in stripped and _URL_RE.match(stripped):
        return "link"
    if _CODE_HINT_RE.search(stripped):
        return "code"
    return "text"


class ClipItem(GObject.Object):
    """A GObject wrapper around one history entry or snippet dict so it can
    live in a ``Gio.ListStore`` and feed ``Gtk.ListView``.

    The virtualized list only builds widgets for the ~dozen visible rows, so
    switching filters / opening the popup no longer rebuilds hundreds of
    ``Adw.ActionRow``s up front. ``data`` is the raw row dict; ``kind`` is
    ``"entry"`` or ``"snippet"``.
    """

    __gtype_name__ = "ClipmanClipItem"

    def __init__(self, data, kind):
        super().__init__()
        self.data = data
        self.kind = kind


class ClipmanWindow(Adw.ApplicationWindow):
    """Phase 1 libadwaita popup.

    Constructor takes keyword args only — ``application``, ``db``,
    ``monitor`` — to mirror the kwargs-only call site in ``app.py``.
    """

    def __init__(self, application, db, monitor):
        super().__init__(application=application)
        self.db = db
        self.monitor = monitor
        self._search_query = ""
        self._search_debounce_id = 0
        self._active_filter = "all"
        self._css_provider = None
        self._current_edge_banner = None
        # Reference to the currently-open in-app dialog (preferences /
        # snippets / edge alert). dismiss-on-focus-loss checks whether it
        # is still mapped rather than a boolean latch, because hiding the
        # popup does NOT emit a dialog's "closed" signal.
        self._child_dialog = None
        # Pending _move_to_cursor timeout id, so a show->hide within 50ms
        # can cancel it (a stale timer would re-activate a closed popup).
        self._cursor_move_id = 0
        # Incremental list fill: refresh() shows the first screenful
        # immediately, then appends the rest on idle so the popup paints
        # fast and stays responsive instead of freezing to build every row.
        self._fill_id = 0
        self._fill_rest = []
        # Decoded image thumbnails, keyed by their content-addressed path
        # (hash.png, immutable). Without this every refresh re-decoded every
        # image thumbnail — brutal for an image-heavy history.
        self._thumb_cache = {}

        self.set_title("Clipman")
        self.set_default_size(380, self._clamped_default_height())
        # Win+V is a fixed overlay panel, not a resizable app window.
        self.set_resizable(False)
        self.add_css_class("clipman-window")

        # Load persisted settings (only the subset Phase 1 actually uses;
        # opacity / font color / paste mode are handled by Phase 2's
        # preferences window).
        saved_font = self.db.get_setting("font_size", str(DEFAULT_FONT_SIZE))
        try:
            self._font_size = max(8, min(20, int(float(saved_font))))
        except (TypeError, ValueError):
            self._font_size = DEFAULT_FONT_SIZE

        saved_theme = self.db.get_setting("theme", DEFAULT_THEME)
        self._theme = (
            saved_theme
            if saved_theme in ("auto", "dark", "light")
            else DEFAULT_THEME
        )

        # When off, don't force the Catppuccin @-token overrides so the app
        # follows the user's system GNOME/Adwaita theme + accent. Default on.
        self._use_catppuccin = (
            self.db.get_setting("use_catppuccin", "true") != "false"
        )
        self._show_count_badges = (
            self.db.get_setting("show_count_badges", "true") != "false"
        )

        self._font_color = self.db.get_setting(
            "font_color", DEFAULT_FONT_COLOR
        ) or DEFAULT_FONT_COLOR

        saved_sensitive = self.db.get_setting(
            "sensitive_timeout", str(DEFAULT_SENSITIVE_TIMEOUT)
        )
        try:
            self._sensitive_timeout = max(10, min(300, int(float(saved_sensitive))))
        except (TypeError, ValueError):
            self._sensitive_timeout = DEFAULT_SENSITIVE_TIMEOUT

        self._apply_theme()
        self._apply_css()
        self._build_ui()

        # Re-evaluate update banner on startup so cached info isn't lost.
        self.refresh_update_banner()

        # Escape closes the popup.
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        # Win+V parity: dismiss when the popup loses focus (user clicks
        # another window / elsewhere). GTK 3 had a focus-out->hide handler
        # that was dropped in the GTK 4 port; restore it via is-active.
        self.connect("notify::is-active", self._on_active_changed)

        # On Wayland the compositor delivers ``close-request`` when the
        # user clicks outside the popup or hits the compositor close
        # gesture. We want the popup to hide rather than destroy so the
        # daemon can re-show it on the next D-Bus Toggle without
        # reconstructing the entire widget tree.
        self.connect("close-request", self._on_close_request)

        # Sensitive-entry purge loop — kept identical to the GTK 3 version.
        GLib.timeout_add_seconds(10, self._cleanup_sensitive)

    # ------------------------------------------------------------------
    # Theme + CSS
    # ------------------------------------------------------------------

    def _apply_theme(self):
        scheme = {
            "auto": Adw.ColorScheme.DEFAULT,
            "dark": Adw.ColorScheme.FORCE_DARK,
            "light": Adw.ColorScheme.FORCE_LIGHT,
        }.get(self._theme, Adw.ColorScheme.FORCE_DARK)
        Adw.StyleManager.get_default().set_color_scheme(scheme)

    def _resolve_font_color(self):
        """Translate the ``font_color`` setting to a CSS colour value.

        Accepts a raw ``#rrggbb`` (the generic colour picker) or a legacy
        preset id (``FONT_COLOR_PRESETS``, imported lazily since
        ``preferences`` pulls in Adw at module scope and we want
        ``window.py`` importable for headless tests). Falls back to the
        theme default.
        """
        val = self._font_color or "default"
        if isinstance(val, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", val):
            return val

        from clipman.preferences import FONT_COLOR_PRESETS

        for preset_id, hex_value, _tooltip in FONT_COLOR_PRESETS:
            if preset_id == val and hex_value:
                return hex_value
        return _DEFAULT_FONT_COLOR_TOKEN

    def _catppuccin_palette_block(self):
        """Return a CSS block that overrides libadwaita's @-tokens with
        the Catppuccin palette appropriate for the active theme.

        For ``self._theme == 'auto'``, we ask ``Adw.StyleManager.get_dark()``
        which reads the system preference; default to Mocha (dark)
        otherwise — matches the marketing mockup default.
        """
        if self._theme == "light":
            palette = _CATPPUCCIN_LATTE
        elif self._theme == "dark":
            palette = _CATPPUCCIN_MOCHA
        else:  # auto — follow system, default dark
            try:
                is_dark = Adw.StyleManager.get_default().get_dark()
            except Exception:
                is_dark = True
            palette = _CATPPUCCIN_MOCHA if is_dark else _CATPPUCCIN_LATTE
        return "\n".join(
            f"@define-color {name} {hex_value};"
            for name, hex_value in palette.items()
        )

    def _type_color_block(self):
        """@define-color tokens for the per-type row tiles.

        Emitted independently of the Catppuccin toggle so the coloured
        tiles always resolve (falling back to system theme just means the
        surrounding chrome isn't Catppuccin — the tile hues still apply).
        """
        if self._theme == "light":
            colors = _TYPE_COLORS_LIGHT
        elif self._theme == "dark":
            colors = _TYPE_COLORS_DARK
        else:  # auto — follow system, default dark
            try:
                is_dark = Adw.StyleManager.get_default().get_dark()
            except Exception:
                is_dark = True
            colors = _TYPE_COLORS_DARK if is_dark else _TYPE_COLORS_LIGHT
        return "\n".join(
            f"@define-color {name} {value};"
            for name, value in colors.items()
        )

    def _apply_css(self):
        """Inject ``style.css`` with Python ``string.Template`` substitutions.

        The template exposes ``${font_size}`` and ``${font_color}`` so
        font size and the .clip-row title colour both hot-reload from
        the preferences window without touching the .css file on disk.

        We also prepend a libadwaita ``@define-color`` palette block so
        the entire app picks up Catppuccin colours regardless of the
        user's system Adwaita accent. Without this the popup inherits
        e.g. Ubuntu's orange/Yaru palette and stops matching the
        marketing mockup.
        """
        css_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "style.css"
        )
        with open(css_path, "r", encoding="utf-8") as f:
            template_body = Template(f.read()).safe_substitute(
                font_size=str(self._font_size),
                font_color=self._resolve_font_color(),
            )
        # Only force the Catppuccin palette when enabled; otherwise emit
        # just the template so libadwaita keeps the system theme/accent.
        palette = (
            self._catppuccin_palette_block() + "\n"
            if self._use_catppuccin
            else ""
        )
        # Type-tile colours are always defined (independent of the
        # Catppuccin toggle) so row tiles never reference an undefined @color.
        css_string = self._type_color_block() + "\n" + palette + template_body

        display = Gdk.Display.get_default()
        if self._css_provider is not None:
            Gtk.StyleContext.remove_provider_for_display(
                display, self._css_provider
            )
        self._css_provider = Gtk.CssProvider()
        # ``load_from_data`` is binding-typed as ``bytes`` on older PyGObject
        # — passing a Python ``str`` raises ``TypeError`` before the popup
        # finishes building. Adw 4.12+ ships ``load_from_string`` which
        # accepts ``str`` directly; fall back to the bytes form everywhere
        # else.
        if hasattr(self._css_provider, "load_from_string"):
            self._css_provider.load_from_string(css_string)
        else:
            self._css_provider.load_from_data(
                css_string.encode("utf-8"), -1
            )
        Gtk.StyleContext.add_provider_for_display(
            display,
            self._css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Idiomatic libadwaita layout: an Adw.ToolbarView owns the header
        # (top bar), the footer hints (bottom bar), and the scrolling
        # body (content) — mirroring snippets_dialog.py. The header is
        # attached via add_top_bar rather than set_titlebar; an
        # Adw.ApplicationWindow uses set_content and has no titlebar slot.
        toolbarview = Adw.ToolbarView()
        self.set_content(toolbarview)

        # The scrolling body is a plain vertical box parented into the
        # ToolbarView content; every existing child keeps its order and
        # wiring so search / filter / edge-state logic is untouched.
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # -- Header bar (incognito start, prefs end) -----------------------
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Clipman", subtitle=""))
        # The popup is its own GtkApplicationWindow but doubles as a
        # transient overlay — title-bar controls (close / minimise /
        # maximise) clash with the close-on-Escape interaction model.
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)

        self._incognito_btn = Gtk.ToggleButton()
        self._incognito_btn.set_icon_name("view-conceal-symbolic")
        self._incognito_btn.set_tooltip_text(_("Incognito mode"))
        self._incognito_btn.add_css_class("flat")
        self._incognito_btn.connect("toggled", self._on_incognito_toggled)
        header.pack_start(self._incognito_btn)

        prefs_btn = Gtk.Button.new_from_icon_name("emblem-system-symbolic")
        prefs_btn.set_tooltip_text(_("Preferences"))
        prefs_btn.add_css_class("flat")
        prefs_btn.connect("clicked", self._on_prefs_clicked)
        header.pack_end(prefs_btn)

        # "New snippet" appears only while the Snippets filter is active;
        # hidden in the All / Pinned views so the headerbar stays light.
        self._new_snippet_btn = Gtk.Button.new_from_icon_name(
            "list-add-symbolic"
        )
        self._new_snippet_btn.set_tooltip_text(_("Manage snippets"))
        self._new_snippet_btn.add_css_class("flat")
        self._new_snippet_btn.set_visible(False)
        self._new_snippet_btn.connect("clicked", self._on_snippets_clicked)
        header.pack_end(self._new_snippet_btn)

        toolbarview.add_top_bar(header)

        # -- Update banner (libadwaita native) -----------------------------
        self._update_banner = Adw.Banner()
        self._update_banner.set_button_label(_("Release notes"))
        self._update_banner.set_revealed(False)
        self._update_banner.connect(
            "button-clicked", self._on_update_banner_clicked
        )
        root.append(self._update_banner)

        # -- Edge-state banner slot ---------------------------------------
        # Banner-kind edge states (incognito-on, paused, sensitive-shown,
        # sensitive-cleared, network-error, history-too-large) mount
        # here rather than into ``_empty_slot`` so the list stays
        # visible underneath them.
        self._edge_banner_slot = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=0
        )
        root.append(self._edge_banner_slot)

        # -- Search entry --------------------------------------------------
        search_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=0
        )
        search_box.set_margin_top(8)
        search_box.set_margin_bottom(4)
        search_box.set_margin_start(8)
        search_box.set_margin_end(8)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Search..."))
        self.search_entry.set_hexpand(True)
        self.search_entry.add_css_class("clipman-search")
        self.search_entry.connect("search-changed", self._on_search_changed)
        search_box.append(self.search_entry)
        root.append(search_box)

        # -- Filter pill row ----------------------------------------------
        self._filter_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6
        )
        self._filter_box.set_margin_top(2)
        self._filter_box.set_margin_bottom(6)
        self._filter_box.set_margin_start(8)
        self._filter_box.set_margin_end(8)
        self._filter_box.set_halign(Gtk.Align.CENTER)

        self._filter_buttons = {}
        self._filter_count_labels = {}
        first = None
        for fid, label in [
            ("all", _("All")),
            ("text", _("Text")),
            ("images", _("Images")),
            ("snippets", _("Snippets")),
        ]:
            btn = Gtk.ToggleButton()
            btn.add_css_class("filter-tab")
            content = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL, spacing=6
            )
            content.append(Gtk.Label(label=label))
            count_lbl = Gtk.Label(label="")
            count_lbl.add_css_class("filter-count")
            content.append(count_lbl)
            btn.set_child(content)
            if fid == "all":
                btn.set_active(True)
                btn.add_css_class("filter-tab-active")
            if first is None:
                first = btn
            else:
                btn.set_group(first)
            btn.connect("toggled", self._on_filter_toggled, fid)
            self._filter_box.append(btn)
            self._filter_buttons[fid] = btn
            self._filter_count_labels[fid] = count_lbl
        root.append(self._filter_box)

        # -- Scrollable list + empty status page --------------------------
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        # Virtualized list: Gio.ListStore feeds a Gtk.ListView through a
        # recycling factory, so only the visible rows (~a dozen) are ever
        # built — opening the popup and switching filters no longer rebuilds
        # every row. A Gtk.SortListModel groups entries into dated sections
        # (★ Pinned / Today / Yesterday / Earlier), rendered as list
        # headers. SingleSelection keeps a keyboard cursor for arrow-nav and
        # the P / Delete / Enter shortcuts.
        self._store = Gio.ListStore(item_type=ClipItem)
        self._sort_sorter = Gtk.CustomSorter.new(self._sort_cmp)
        self._section_sorter = Gtk.CustomSorter.new(self._section_cmp)
        self._sortmodel = Gtk.SortListModel(
            model=self._store, sorter=self._sort_sorter
        )
        self._sortmodel.set_section_sorter(self._section_sorter)
        self._selection = Gtk.SingleSelection(model=self._sortmodel)
        self._selection.set_autoselect(False)
        self._selection.set_can_unselect(True)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._row_setup)
        factory.connect("bind", self._row_bind)
        header_factory = Gtk.SignalListItemFactory()
        header_factory.connect("setup", self._header_setup)
        header_factory.connect("bind", self._header_bind)
        self.listview = Gtk.ListView(model=self._selection, factory=factory)
        self.listview.set_header_factory(header_factory)
        self.listview.set_single_click_activate(True)
        self.listview.add_css_class("clipman-list")
        self.listview.connect("activate", self._on_list_activate)
        scrolled.set_child(self.listview)

        # Empty / no-results state — Adw.StatusPage swaps in for the list.
        # The actual visual is produced by ``render_edge_state(state_id)``
        # in ``refresh()``; this slot is just a placeholder until then.
        self._empty_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._empty_slot.set_vexpand(True)
        self._current_edge_widget = None

        self._list_stack = Gtk.Stack()
        self._list_stack.set_vexpand(True)
        self._list_stack.add_named(scrolled, "list")
        self._list_stack.add_named(self._empty_slot, "empty")
        root.append(self._list_stack)

        # -- Footer: item count · recording status · clear all ------------
        # (docs/design mockup). Shortcuts still work (↵ paste, P pin,
        # ⌫ delete, Esc close); the footer now carries state + a bulk action.
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.add_css_class("clipman-footer")

        self._count_label = Gtk.Label(label="")
        self._count_label.add_css_class("clipman-count")
        self._count_label.set_halign(Gtk.Align.START)
        self._count_label.set_hexpand(True)
        footer.append(self._count_label)

        # Recording / incognito status pill (reflects the header toggle).
        self._recording_pill = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=4
        )
        self._recording_pill.add_css_class("recording-pill")
        self._recording_pill.set_valign(Gtk.Align.CENTER)
        self._recording_icon = Gtk.Image.new_from_icon_name(
            "media-record-symbolic"
        )
        self._recording_label = Gtk.Label(label=_("Recording"))
        self._recording_pill.append(self._recording_icon)
        self._recording_pill.append(self._recording_label)
        footer.append(self._recording_pill)

        clear_btn = Gtk.Button(label=_("Clear all"))
        clear_btn.add_css_class("flat")
        clear_btn.add_css_class("clipman-clear")
        clear_btn.set_valign(Gtk.Align.CENTER)
        clear_btn.connect("clicked", self._on_clear_all)
        footer.append(clear_btn)

        # -- Assemble the ToolbarView -------------------------------------
        # Body (search + filters + list/banner stack) becomes the
        # ToolbarView content; the footer hints become its bottom bar.
        toolbarview.set_content(root)
        toolbarview.add_bottom_bar(footer)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self):
        is_snippets = self._active_filter == "snippets"
        # Dated sections apply to clipboard history, not the flat snippet list.
        self._sortmodel.set_section_sorter(
            None if is_snippets else self._section_sorter
        )

        if is_snippets:
            entries = (
                self.db.search_snippets(self._search_query)
                if self._search_query
                else self.db.get_snippets()
            )
            items = [ClipItem(e, "snippet") for e in entries]
        else:
            if self._search_query:
                entries = self.db.search(self._search_query)
            else:
                entries = self.db.get_entries(limit=200)
            if self._active_filter == "text":
                entries = [
                    e for e in entries
                    if (e.get("content_type") or "text") == "text"
                ]
            elif self._active_filter == "images":
                entries = [
                    e for e in entries if e.get("content_type") == "image"
                ]
            items = [ClipItem(e, "entry") for e in entries]

        # Cancel any in-flight incremental fill from a previous refresh.
        self._cancel_fill()
        self._update_count(len(items))
        self._update_filter_counts()

        if not items:
            self._store.remove_all()
            if self._search_query:
                state_id = "no-results"
            elif is_snippets:
                state_id = "no-snippets-yet"
            else:
                state_id = "empty"
            self._show_edge_state(state_id)
            return

        self._list_stack.set_visible_child_name("list")
        # Show the first screenful immediately, then append the rest on idle.
        # Building a couple hundred rows in one go froze the popup for ~0.5s
        # ("switching to All is slow"); splitting the work keeps first paint
        # fast and the UI responsive while the tail streams in.
        first = items[:_FILL_FIRST]
        self._store.splice(0, self._store.get_n_items(), first)
        if len(items) > _FILL_FIRST:
            self._fill_rest = items[_FILL_FIRST:]
            self._fill_id = GLib.idle_add(self._fill_more)

    def _fill_more(self):
        """Append the next batch of queued rows (idle callback). Returns True
        to keep going, False when the queue is drained."""
        if not self._fill_rest:
            self._fill_id = 0
            return False
        chunk = self._fill_rest[:_FILL_BATCH]
        self._fill_rest = self._fill_rest[_FILL_BATCH:]
        self._store.splice(self._store.get_n_items(), 0, chunk)
        if self._fill_rest:
            return True
        self._fill_id = 0
        return False

    def _update_filter_counts(self):
        """Refresh the count badge on each switcher tab (honours the
        ``show_count_badges`` preference)."""
        if not hasattr(self, "_filter_count_labels"):
            return
        if not self._show_count_badges:
            for label in self._filter_count_labels.values():
                label.set_visible(False)
            return
        try:
            counts = {
                "all": self.db.count_entries(),
                "text": self.db.count_entries("text"),
                "images": self.db.count_entries("image"),
                "snippets": len(self.db.get_snippets()),
            }
        except Exception:
            logger.debug("filter count query failed", exc_info=True)
            return
        for fid, label in self._filter_count_labels.items():
            label.set_text(str(counts.get(fid, 0)))
            label.set_visible(True)

    def _update_count(self, n):
        """Set the footer item/snippet count for the current view."""
        if not hasattr(self, "_count_label"):
            return
        if self._active_filter == "snippets":
            label = _("{n} snippet").format(n=n) if n == 1 \
                else _("{n} snippets").format(n=n)
        else:
            label = _("{n} item").format(n=n) if n == 1 \
                else _("{n} items").format(n=n)
        self._count_label.set_text(label)

    def _on_clear_all(self, _button):
        """Clear unpinned history after confirmation (pinned entries stay)."""
        dialog = Adw.AlertDialog(
            heading=_("Clear clipboard history?"),
            body=_("This removes all unpinned entries. Pinned entries and "
                   "snippets are kept. This can't be undone."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("clear", _("Clear"))
        dialog.set_response_appearance(
            "clear", Adw.ResponseAppearance.DESTRUCTIVE
        )
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def _on_response(_dlg, response):
            if response == "clear":
                self.db.clear_unpinned()
                self.refresh()

        self._register_child(dialog)
        dialog.connect("response", _on_response)
        dialog.present(self)

    def _cancel_fill(self):
        """Drop any pending incremental-fill idle source and its backlog."""
        if self._fill_id:
            GLib.source_remove(self._fill_id)
            self._fill_id = 0
        self._fill_rest = []

    def _show_edge_state(self, state_id):
        """Swap the rendered edge-state widget into the empty slot.

        Dispatches through ``render_edge_state`` so future Banner /
        AlertDialog states get the correct widget family — window.py
        only knows about ``state_id`` and trusts the renderer.
        """
        from clipman.edge_states import render_edge_state

        widget = render_edge_state(
            state_id, parent_window=self, on_action=self._on_edge_action
        )
        spec = getattr(widget, "state_spec", None)
        kind = spec.kind if spec is not None else "statuspage"

        # AlertDialog presents itself modally; nothing to mount. Track it
        # as a child so a focus-losing action (e.g. its button opening a
        # browser) doesn't trip dismiss-on-focus-loss and hide both.
        if kind == "alertdialog":
            self._register_child(widget)
            widget.present(self)
            self._list_stack.set_visible_child_name("list")
            return

        # Banner-kind states use the dedicated banner slot above the
        # list, so they stack alongside (rather than replace) the clip
        # list. StatusPage states still take over the empty slot.
        if kind == "banner":
            self._mount_edge_banner(widget)
            return

        # Clear any previous statuspage widget from the empty slot.
        if self._current_edge_widget is not None:
            self._empty_slot.remove(self._current_edge_widget)
            self._current_edge_widget = None
        widget.set_vexpand(True)
        self._empty_slot.append(widget)
        self._current_edge_widget = widget
        self._list_stack.set_visible_child_name("empty")

    def _mount_edge_banner(self, banner):
        """Drop a rendered ``Adw.Banner`` into the dedicated edge slot.

        Replaces any banner already mounted there so two banners never
        stack (e.g. ``paused`` then ``incognito-on``).
        """
        if self._current_edge_banner is not None:
            self._edge_banner_slot.remove(self._current_edge_banner)
            self._current_edge_banner = None
        self._edge_banner_slot.append(banner)
        self._current_edge_banner = banner

    # Stable URLs surfaced by edge-state action buttons. Kept as class
    # constants so the dispatcher table can reference them by name and
    # the test suite can introspect them without instantiating GTK.
    _EXTENSIONS_URL = (
        "https://extensions.gnome.org/extension/9407/clipman/"
    )
    _INSTALL_GUIDE_URL = (
        "https://github.com/MohammedEl-sayedAhmed/clipman"
        "#readme"
    )
    _SNAP_NOTES_URL = (
        "https://github.com/MohammedEl-sayedAhmed/clipman"
        "/blob/main/docs/snap-confinement.md"
    )

    # Authoritative list of action_ids the dispatcher handles. The
    # ``_edge_action_dispatch`` property builds a dict keyed on this
    # set; ``test_window.test_on_edge_action_covers_states_contract``
    # asserts that this set is a superset of every action_id declared
    # in ``edge_states.STATES``. Adding a new edge state with a new
    # action_id therefore fails CI until a handler is wired here.
    _EDGE_ACTION_IDS = frozenset({
        "clear-search",
        "open-snippets-dialog",
        "open-extensions",
        "open-install-guide",
        "open-snap-notes",
        "resume-recording",
        "open-prefs-privacy",
        "retry-backup",
        "rechoose-backup",
        "rechoose-restore",
        "open-restore",
        "open-prefs-storage",
        "reveal-db-folder",
        "retry-update-check",
        "close-dialog",
    })

    def _on_edge_action(self, action_id):
        """Dispatch the ``action_id`` strings declared in ``edge_states.py``.

        Every id present in ``edge_states.STATES`` (via either
        ``primary_action`` or ``secondary_action``) MUST map to an entry
        in ``self._edge_action_dispatch``. The
        ``test_on_edge_action_covers_states_contract`` test enforces
        that invariant so a new edge state with an un-wired action_id
        fails CI instead of silently no-op-ing in production.

        Unknown ids still log a warning — they shouldn't ever happen in
        normal flow but the popup keeps running rather than crashing
        the daemon.
        """
        handler = self._edge_action_dispatch.get(action_id)
        if handler is None:
            logger.warning("unhandled edge-state action_id: %r", action_id)
            return
        handler()

    @property
    def _edge_action_dispatch(self):
        """Map ``action_id`` -> bound method for the edge-state dispatcher.

        Exposed as a property (rather than a constant) so subclasses /
        tests can introspect it without paying the cost of binding the
        methods at construction time. ``test_window.py`` reads this
        directly to assert dispatcher coverage of every action_id
        declared in ``edge_states.STATES``.
        """
        return {
            # No-history / search-empty states.
            "clear-search": self._action_clear_search,
            "open-snippets-dialog": self._action_open_snippets_dialog,
            # Extension / install-guide states.
            "open-extensions": self._action_open_extensions,
            "open-install-guide": self._action_open_install_guide,
            "open-snap-notes": self._action_open_snap_notes,
            # Privacy / incognito states.
            "resume-recording": self._action_resume_recording,
            "open-prefs-privacy": self._action_open_prefs_privacy,
            # Backup / restore error states.
            "retry-backup": self._action_retry_backup,
            "rechoose-backup": self._action_rechoose_backup,
            "rechoose-restore": self._action_rechoose_restore,
            "open-restore": self._action_open_restore,
            # Storage / DB / network states.
            "open-prefs-storage": self._action_open_prefs_storage,
            "reveal-db-folder": self._action_reveal_db_folder,
            "retry-update-check": self._action_retry_update_check,
            # AlertDialog close (response id when user dismisses).
            "close-dialog": self._action_close_dialog,
        }

    # -- Individual action handlers ------------------------------------
    # Each handler is intentionally tiny so the dispatcher table reads
    # like a manifest. The handlers fall into four families:
    #   1. inline state changes (clear-search, resume-recording)
    #   2. open-url shells (Extensions site, install guide, snap notes)
    #   3. open-prefs delegations (privacy / storage panes)
    #   4. retry hooks for background operations (update check, backup)

    def _action_clear_search(self):
        self.search_entry.set_text("")
        self._search_query = ""
        self.refresh()

    def _action_open_snippets_dialog(self):
        self._on_snippets_clicked(None)

    def _action_open_extensions(self):
        self._open_url(self._EXTENSIONS_URL)

    def _action_open_install_guide(self):
        self._open_url(self._INSTALL_GUIDE_URL)

    def _action_open_snap_notes(self):
        self._open_url(self._SNAP_NOTES_URL)

    def _action_resume_recording(self):
        if self.monitor is not None:
            self.monitor.set_incognito(False)
        self._incognito_btn.set_active(False)
        self._dismiss_edge_banner()

    def _action_open_prefs_privacy(self):
        # Adw.PreferencesWindow auto-selects the first matching page;
        # we expose the privacy pane via search to be deep-link friendly.
        self._on_prefs_clicked(None)

    def _action_open_prefs_storage(self):
        self._on_prefs_clicked(None)

    def _action_retry_backup(self):
        # The retry flow is owned by the preferences window — bring
        # the user back to Storage where the Export action lives so a
        # second click re-issues the backup.
        self._on_prefs_clicked(None)

    def _action_rechoose_backup(self):
        # Same shape as retry-backup: hand off to preferences where the
        # FileChooser is wired. Splitting them keeps the dispatcher
        # table self-documenting even though the destination matches.
        self._on_prefs_clicked(None)

    def _action_rechoose_restore(self):
        self._on_prefs_clicked(None)

    def _action_open_restore(self):
        # db-locked state CTA: take the user to the Restore action so
        # they can recover from the most recent backup.
        self._on_prefs_clicked(None)

    def _action_reveal_db_folder(self):
        # xdg-open a directory hands off to the user's file manager.
        from clipman.database import DATA_DIR

        self._open_url(str(DATA_DIR))

    def _action_retry_update_check(self):
        self.refresh_update_banner()

    def _action_close_dialog(self):
        # AlertDialog handles its own dismissal — no extra work needed.
        # The handler exists so the dispatcher table stays exhaustive.
        pass

    def _dismiss_edge_banner(self, state_id=None):
        """Remove the mounted edge banner.

        When ``state_id`` is given, only dismiss if the current banner is
        that state — so turning incognito off doesn't wipe an unrelated
        banner (e.g. ``paused``).
        """
        banner = self._current_edge_banner
        if banner is None:
            return
        if state_id is not None:
            spec = getattr(banner, "state_spec", None)
            if spec is not None and spec.id != state_id:
                return
        self._edge_banner_slot.remove(banner)
        self._current_edge_banner = None

    def _open_url(self, url):
        try:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            logger.debug("xdg-open failed for %s", url, exc_info=True)

    def _thumbnail_texture(self, image_path, size=48):
        """Decode a stored image to a small, HiDPI-crisp ``Gdk.Texture``.

        Decodes-and-scales the PNG at load time via
        ``GdkPixbuf.new_from_file_at_scale`` (not a full-res decode then
        shrink). The decode target is oversized by the widget scale factor
        (HiDPI sharpness) and by 2x (COVER-crop headroom). Returns a
        ``Gdk.Texture``, or ``None`` when the path is unsafe, missing, or
        undecodable.
        """
        from clipman.database import _safe_image_path

        if not image_path or not _safe_image_path(image_path):
            return None

        # Content-addressed path -> immutable image, so cache the decoded
        # texture and never decode the same thumbnail twice.
        cache_key = (image_path, size)
        cached = self._thumb_cache.get(cache_key)
        if cached is not None:
            return cached

        # Oversample: logical px * device scale * COVER-crop headroom.
        scale = max(1, self.get_scale_factor())
        box = size * scale * 2
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                image_path, box, box, True
            )
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        except Exception:
            # Corrupt file or unsupported format — fall back to the type
            # icon rather than crashing.
            logger.debug("thumbnail failed for %r", image_path, exc_info=True)
            return None

        # Bound the cache so a long session can't grow it without limit
        # (history itself is capped at MAX_ENTRIES). Simple FIFO eviction.
        if len(self._thumb_cache) >= 256:
            self._thumb_cache.pop(next(iter(self._thumb_cache)), None)
        self._thumb_cache[cache_key] = texture
        return texture

    # ------------------------------------------------------------------
    # ListView factory: build each visible row once, rebind on recycle
    # ------------------------------------------------------------------

    def _row_setup(self, _factory, list_item):
        """Build one reusable row widget. The factory recycles these across
        scroll positions, so nothing here is per-item — ``_row_bind`` fills
        in the data. Buttons read the row's *current* item, so they connect
        once here and stay valid across rebinds.

        The row is a plain ``Gtk.Box`` rather than ``Adw.ActionRow``:
        ActionRow is ~5x more expensive to realize, and building a couple
        hundred of them was the whole "popup feels heavy / switching to All
        is slow" problem. This composite is cheap and gives the same
        icon · title/subtitle · pin/delete layout.
        """
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.add_css_class("clip-row")

        # Colour-coded type tile: a rounded square whose tint + icon convey
        # the clip type at a glance (docs/design mockup). Images swap the
        # tile for a thumbnail (below).
        icon = Gtk.Image()
        icon.set_halign(Gtk.Align.CENTER)
        icon.set_valign(Gtk.Align.CENTER)
        tile = Gtk.Box()
        tile.add_css_class("clip-tile")
        tile.set_halign(Gtk.Align.CENTER)
        tile.set_valign(Gtk.Align.CENTER)
        tile.append(icon)
        row.append(tile)

        thumb = Gtk.Picture()
        thumb.set_can_shrink(True)
        thumb.set_content_fit(Gtk.ContentFit.COVER)
        thumb.set_size_request(48, 48)
        thumb.set_valign(Gtk.Align.CENTER)
        thumb.add_css_class("clip-thumb")
        thumb.set_visible(False)
        row.append(thumb)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        text_box.set_valign(Gtk.Align.CENTER)
        text_box.set_hexpand(True)
        title = Gtk.Label(xalign=0)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.add_css_class("title")
        subtitle = Gtk.Label(xalign=0)
        subtitle.set_ellipsize(Pango.EllipsizeMode.END)
        subtitle.add_css_class("subtitle")
        text_box.append(title)
        text_box.append(subtitle)
        row.append(text_box)

        # Actions sit in a box that fades in on row hover (always shown for
        # pinned rows) — docs/design mockup. See .clip-actions in style.css.
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        actions.add_css_class("clip-actions")
        actions.set_valign(Gtk.Align.CENTER)

        pin_btn = Gtk.Button()
        pin_btn.add_css_class("flat")
        pin_btn.set_valign(Gtk.Align.CENTER)
        pin_btn.connect("clicked", self._lv_pin_clicked, row)
        actions.append(pin_btn)

        del_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        del_btn.add_css_class("flat")
        del_btn.set_valign(Gtk.Align.CENTER)
        del_btn.set_tooltip_text(_("Delete"))
        del_btn.connect("clicked", self._lv_delete_clicked, row)
        actions.append(del_btn)
        row.append(actions)

        row._clip_icon = icon
        row._clip_tile = tile
        row._clip_thumb = thumb
        row._clip_title = title
        row._clip_subtitle = subtitle
        row._clip_pin = pin_btn
        row._clip_del = del_btn
        row._clip_actions = actions
        row._clip_item = None
        list_item.set_child(row)

    def _row_bind(self, _factory, list_item):
        row = list_item.get_child()
        item = list_item.get_item()
        row._clip_item = item
        if item.kind == "snippet":
            self._bind_snippet_row(row, item.data)
        else:
            self._bind_entry_row(row, item.data)

    # ------------------------------------------------------------------
    # Section grouping: ★ Pinned / Today / Yesterday / Earlier
    # ------------------------------------------------------------------

    def _compute_bucket(self, item):
        """Return (order, label) for the item's dated section."""
        if item.kind != "entry":
            return (0, "")
        entry = item.data
        if entry.get("pinned"):
            return (0, _("★ Pinned"))
        try:
            d = datetime.fromtimestamp(entry.get("accessed_at") or 0).date()
        except (OSError, OverflowError, ValueError):
            return (4, _("Older"))
        today = date.today()
        if d >= today:
            return (1, _("Today"))
        if d == today - timedelta(days=1):
            return (2, _("Yesterday"))
        if d > today - timedelta(days=7):
            return (3, _("Earlier this week"))
        return (4, _("Older"))

    def _bucket(self, item):
        """Cached section (order, label) for ``item`` — recomputed per
        refresh since ClipItems are rebuilt each time."""
        b = getattr(item, "_bucket", None)
        if b is None:
            b = self._compute_bucket(item)
            item._bucket = b
        return b

    @staticmethod
    def _sort_ts(item):
        if item.kind == "entry":
            return item.data.get("accessed_at") or 0
        return 0

    def _sort_cmp(self, a, b, _u):
        oa, ob = self._bucket(a)[0], self._bucket(b)[0]
        if oa != ob:
            return -1 if oa < ob else 1
        ta, tb = self._sort_ts(a), self._sort_ts(b)  # newest first in-section
        if ta != tb:
            return -1 if ta > tb else 1
        return 0

    def _section_cmp(self, a, b, _u):
        oa, ob = self._bucket(a)[0], self._bucket(b)[0]
        return -1 if oa < ob else (1 if oa > ob else 0)

    def _header_setup(self, _factory, header):
        label = Gtk.Label(xalign=0)
        label.add_css_class("clip-section-header")
        header.set_child(label)

    def _header_bind(self, _factory, header):
        item = header.get_item()
        header.get_child().set_text(self._bucket(item)[1] if item else "")

    def _bind_entry_row(self, row, entry):
        ctype = entry.get("content_type") or "text"
        text = entry.get("content_text") or ""
        first_line = text.split("\n", 1)[0].strip() if text else ""
        if ctype == "image":
            title = "[Image]"
        else:
            title = first_line[:120] or _("(empty)")
        # Gtk.Label.set_text renders literally, so no markup-escaping needed.
        row._clip_title.set_text(title)
        # Lead with the relative time (the type icon already conveys type),
        # plus a char count for text entries.
        ts = self._format_time(entry["accessed_at"])
        if ctype == "text" and text:
            n = len(text)
            subtitle = f"{ts} · {n:,} char{'s' if n != 1 else ''}"
        else:
            subtitle = ts
        row._clip_subtitle.set_text(subtitle)

        # Image rows show a thumbnail; everything else shows a coloured tile.
        texture = (
            self._thumbnail_texture(entry.get("image_path"))
            if ctype == "image" else None
        )
        if texture is not None:
            row._clip_thumb.set_paintable(texture)
            row._clip_thumb.set_visible(True)
            row._clip_tile.set_visible(False)
        else:
            row._clip_thumb.set_paintable(None)
            row._clip_thumb.set_visible(False)
            rtype = "image" if ctype == "image" else _classify_text(text)
            self._set_tile(row, rtype)

        pinned = entry.get("pinned")
        row._clip_pin.set_icon_name(
            "starred-symbolic" if pinned else "non-starred-symbolic"
        )
        row._clip_pin.set_tooltip_text(_("Unpin") if pinned else _("Pin"))
        row._clip_actions.set_visible(True)
        # Pinned rows keep their actions visible; others fade in on hover.
        if pinned:
            row.add_css_class("pinned")
        else:
            row.remove_css_class("pinned")

    def _bind_snippet_row(self, row, snippet):
        row._clip_title.set_text(snippet["name"])
        preview = (snippet.get("content_text") or "").split("\n", 1)[0]
        row._clip_subtitle.set_text(preview[:120])
        row._clip_thumb.set_paintable(None)
        row._clip_thumb.set_visible(False)
        self._set_tile(row, "snip")
        # Snippets are managed in the Snippets dialog — no inline pin/delete.
        row._clip_actions.set_visible(False)
        row.remove_css_class("pinned")

    def _set_tile(self, row, rtype):
        """Show the coloured type tile for ``rtype`` (text/link/code/image/
        snip): swap its type CSS class and icon."""
        tile = row._clip_tile
        for cls in _TILE_TYPE_CLASSES:
            tile.remove_css_class(cls)
        tile.add_css_class(f"type-{rtype}")
        row._clip_icon.set_from_icon_name(
            ROW_TYPE_ICONS.get(rtype, "text-x-generic-symbolic")
        )
        tile.set_visible(True)

    def _lv_pin_clicked(self, button, row):
        item = row._clip_item
        if item is not None and item.kind == "entry":
            entry_id = item.data.get("id")
            if entry_id:
                self._on_pin_clicked(button, entry_id)

    def _lv_delete_clicked(self, button, row):
        item = row._clip_item
        if item is not None and item.kind == "entry":
            entry_id = item.data.get("id")
            if entry_id:
                self._on_delete_clicked(button, entry_id)

    # ------------------------------------------------------------------
    # Update banner
    # ------------------------------------------------------------------

    def refresh_update_banner(self):
        """Public — ``app.py`` re-evaluates after a background check."""
        show, latest = updates.should_show_banner(self.db)
        if show:
            self._update_banner.set_title(
                _("Update available: v{new} (you have v{cur})").format(
                    new=latest, cur=__version__
                )
            )
            self._update_banner.set_revealed(True)
        else:
            self._update_banner.set_revealed(False)

    def _on_update_banner_clicked(self, _banner):
        latest = updates.latest_known(self.db) or __version__
        self._open_url(
            f"https://github.com/MohammedEl-sayedAhmed/clipman/"
            f"releases/tag/v{latest}"
        )

    # ------------------------------------------------------------------
    # Paste path — GTK 4 clipboard API with wl-copy + wtype/ydotool fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _is_wayland():
        return bool(os.environ.get("WAYLAND_DISPLAY"))

    def _wl_copy(self, data, mime=None):
        """Set the clipboard via wl-copy and return True on success.

        wl-copy owns the selection from a temporary surface it focuses
        itself, so it works from a background process — unlike GTK's
        Gdk.Clipboard, whose core wl_data_device.set_selection needs a
        serial from input focus the daemon doesn't have. It forks a helper
        that keeps serving the selection until it's replaced.
        """
        cmd = ["wl-copy"]
        if mime:
            cmd += ["--type", mime]
        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            proc.communicate(input=data)
            return proc.returncode == 0
        except OSError:
            logger.debug("wl-copy unavailable", exc_info=True)
            return False

    def _copy_to_clipboard(self, text):
        if self.monitor:
            self.monitor.set_self_copy(True)
        # On Wayland the daemon is a background process, so Gdk.Clipboard.set()
        # silently fails to claim the selection (no input-focus serial). Prefer
        # wl-copy, which is built to set the clipboard from the background; fall
        # back to GTK on X11 (no focus requirement) or if wl-copy is missing.
        if self._is_wayland() and self._wl_copy(text.encode("utf-8")):
            return
        try:
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set(text)
        except Exception:
            logger.debug("GTK clipboard.set failed", exc_info=True)
            self._wl_copy(text.encode("utf-8"))

    def _copy_image_to_clipboard(self, image_path):
        """Push an image file at ``image_path`` onto the system clipboard.

        ``image_path`` must have already passed ``database._safe_image_path``
        — we re-check defensively here so a poisoned DB row can't reach
        ``Gdk.Texture.new_from_filename`` with a path outside ``IMAGES_DIR``.
        Returns ``True`` on success so callers know whether to simulate
        a paste.
        """
        from clipman.database import _safe_image_path

        if not image_path or not _safe_image_path(image_path):
            logger.debug("refusing image with unsafe path: %r", image_path)
            return False
        if self.monitor:
            self.monitor.set_self_copy(True)
        # Wayland: prefer wl-copy (works from the background daemon); GTK's
        # set_texture() has the same input-focus limitation as text.
        if self._is_wayland():
            try:
                with open(image_path, "rb") as fh:
                    if self._wl_copy(fh.read(), mime="image/png"):
                        return True
            except OSError:
                logger.debug("reading image for wl-copy failed", exc_info=True)
        try:
            texture = Gdk.Texture.new_from_filename(image_path)
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set_texture(texture)
            return True
        except Exception:
            logger.debug("Gdk.Texture clipboard set failed", exc_info=True)
            return False

    # Per-mode command tables. ``wtype`` and ``ydotool`` use different
    # key spellings; we keep both so a user without one binary still gets
    # paste via the other.
    _PASTE_COMMANDS = {
        "ctrl-v": [
            ["wtype", "-M", "ctrl", "v"],
            ["ydotool", "key", "ctrl+v"],
        ],
        "ctrl-shift-v": [
            ["wtype", "-M", "ctrl", "-M", "shift", "v"],
            ["ydotool", "key", "ctrl+shift+v"],
        ],
        "shift-insert": [
            ["wtype", "-M", "shift", "-k", "Insert"],
            ["ydotool", "key", "shift+Insert"],
        ],
    }

    def _simulate_paste(self):
        """Synthesise the user's configured paste keystroke.

        Dispatch order: read ``paste_mode`` from the DB; ``auto`` and
        ``ctrl-v`` both fire Ctrl+V (auto is the historical default and
        the most compatible). The other two modes use their respective
        key sequence tables. If neither wtype nor ydotool is installed
        we surface ``paste-target-missing`` via the edge state so the
        user knows to copy manually.
        """
        mode = self.db.get_setting("paste_mode", "auto") or "auto"
        commands = self._PASTE_COMMANDS.get(
            mode, self._PASTE_COMMANDS["ctrl-v"]
        )
        any_binary_available = False
        for cmd in commands:
            try:
                subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
                # First command that runs (even with a non-zero exit)
                # is enough — the keystroke was synthesised.
                return False
            except FileNotFoundError:
                continue
            except subprocess.SubprocessError:
                # The binary exists but failed to drive the
                # keystroke — still counts as "available", just don't
                # short-circuit so we try the next backend.
                any_binary_available = True
                continue
        if not any_binary_available:
            # Neither wtype nor ydotool is installed. Show the popup
            # again (focused) with the dedicated edge state so the user
            # has a clear next step.
            self._present_focused()
            self._show_edge_state("paste-target-missing")
        return False

    def _paste_entry(self, entry):
        ctype = entry.get("content_type") or "text"
        if ctype == "image":
            image_path = entry.get("image_path")
            if not self._copy_image_to_clipboard(image_path):
                # Couldn't load the image — leave the popup open so the
                # user notices the failure rather than silently swallowing.
                return
        else:
            text = entry.get("content_text") or ""
            if not text:
                return
            self._copy_to_clipboard(text)
        if entry.get("id"):
            self.db.update_accessed(entry["id"])
        self.set_visible(False)
        self._dispatch_paste()

    def _paste_snippet(self, snippet):
        text = snippet.get("content_text") or ""
        if not text:
            return
        text = self._expand_snippet_tokens(text)
        self._copy_to_clipboard(text)
        self.set_visible(False)
        self._dispatch_paste()

    def _dispatch_paste(self):
        """Restore focus to the user's window, then synthesise the paste.

        On GNOME Wayland a naive paste fails twice over: the popup stole
        input focus (the Shell activated it so its buttons/keys work), and
        wtype can't inject at all — Mutter exposes no virtual-keyboard
        protocol, so ``wtype`` exits with "compositor does not support the
        virtual keyboard protocol". We therefore drive both steps through the
        Shell extension: ``RestorePreviousFocus`` hands focus back to the
        window the user came from, then ``SimulatePaste`` synthesises the
        keystroke with a Clutter virtual device (which runs inside the
        compositor and does work). Fall back to wtype/ydotool only when the
        extension is absent — other compositors, where wtype works and the
        popup never stole focus.
        """
        mode = self.db.get_setting("paste_mode", "auto") or "auto"
        if self._paste_via_shell(mode):
            return
        GLib.timeout_add(80, self._simulate_paste)

    def _paste_via_shell(self, mode):
        """Best-effort paste via the GNOME Shell extension: restore focus,
        then inject the keystroke through Clutter. Returns True once the
        requests are dispatched, False if the extension isn't reachable (so
        the caller can fall back to wtype/ydotool)."""
        iface = self._shell_extension_iface()
        if iface is None:
            return False
        try:
            iface.RestorePreviousFocus()
        except Exception as exc:
            logger.debug("Shell focus-restore failed: %s", exc, exc_info=True)
            return False

        # Give the compositor a frame to move focus onto the restored window
        # before the keys land, then inject via the Shell (not wtype).
        def _fire_keystroke():
            try:
                iface.SimulatePaste(mode)
            except Exception as exc:
                logger.debug(
                    "Shell SimulatePaste failed: %s", exc, exc_info=True
                )
            return False

        # ~120ms: comfortably longer than a compositor focus cycle so the
        # keys land on the restored window, still imperceptible to the user.
        GLib.timeout_add(120, _fire_keystroke)
        return True

    def _shell_extension_iface(self):
        """Return the GNOME Shell extension's D-Bus interface, or None if it
        isn't available (non-GNOME session, extension disabled, no bus)."""
        try:
            import dbus
            bus = dbus.SessionBus()
            proxy = bus.get_object(
                "org.gnome.Shell.Extensions.clipman",
                "/org/gnome/Shell/Extensions/clipman",
            )
            return dbus.Interface(
                proxy, "org.gnome.Shell.Extensions.clipman"
            )
        except Exception as exc:
            logger.debug("Shell extension unavailable: %s", exc, exc_info=True)
            return None

    def _expand_snippet_tokens(self, text):
        """Substitute ``${date}``, ``${time}``, ``${clipboard}`` tokens.

        ``${clipboard}`` resolves to the most-recent text entry from the
        clipboard history — useful for snippets that wrap whatever the
        user just copied (e.g. ``> ${clipboard}`` for quoting).
        """
        recent = ""
        try:
            entries = self.db.get_entries(limit=1)
            if entries:
                recent = entries[0].get("content_text") or ""
        except Exception:
            logger.debug("get_entries failed for ${clipboard} expansion",
                         exc_info=True)
        return Template(text).safe_substitute(
            date=time.strftime("%Y-%m-%d"),
            time=time.strftime("%H:%M"),
            clipboard=recent,
        )

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_search_changed(self, entry):
        # Update the query synchronously so the newest keystroke wins, but
        # coalesce the (expensive) refresh: every character otherwise runs a
        # ``LIKE '%q%'`` scan and rebuilds up to ~200 ListBox rows, which is a
        # real source of input lag while typing. Debounce so only the last
        # keystroke in a burst actually rebuilds the list.
        self._search_query = entry.get_text().strip()
        self._cancel_search_debounce()
        self._search_debounce_id = GLib.timeout_add(
            150, self._run_search_refresh
        )

    def _run_search_refresh(self):
        # One-shot debounce callback: clear the id first (the source has
        # fired, so it must not be removed again) then rebuild the list.
        self._search_debounce_id = 0
        self.refresh()
        return False

    def _cancel_search_debounce(self):
        # Remove a still-pending debounce source. Guard against a zero/None id
        # (nothing scheduled, or the source already fired and cleared itself).
        if self._search_debounce_id:
            GLib.source_remove(self._search_debounce_id)
            self._search_debounce_id = 0

    def _on_close_request(self, _window):
        # Hide (rather than destroy) so the daemon can re-show the popup on
        # the next D-Bus Toggle. _hide() tears down transient state.
        self._hide()
        return True

    def _on_filter_toggled(self, button, filter_id):
        if not button.get_active():
            return
        if filter_id == self._active_filter:
            return
        for fid, btn in self._filter_buttons.items():
            btn.remove_css_class("filter-tab-active")
            if fid == filter_id:
                btn.add_css_class("filter-tab-active")
        self._active_filter = filter_id
        self._new_snippet_btn.set_visible(filter_id == "snippets")
        self.refresh()

    def _on_snippets_clicked(self, _button):
        from clipman.snippets_dialog import SnippetsDialog

        dialog = SnippetsDialog(self.db)
        self._register_child(dialog, on_closed=lambda _d: self.refresh())
        dialog.present(self)

    def _on_list_activate(self, _listview, position):
        # Position indexes the sorted/section model the ListView shows.
        item = self._selection.get_item(position)
        if item is None:
            return
        if item.kind == "snippet":
            self._paste_snippet(item.data)
        elif item.kind == "entry":
            self._paste_entry(item.data)

    def _on_pin_clicked(self, _button, entry_id):
        self.db.toggle_pin(entry_id)
        self.refresh()

    def _on_delete_clicked(self, _button, entry_id):
        self.db.delete_entry(entry_id)
        self.refresh()

    def _update_recording_pill(self, incognito):
        """Reflect incognito state in the footer status pill."""
        if not hasattr(self, "_recording_pill"):
            return
        if incognito:
            self._recording_icon.set_from_icon_name("view-conceal-symbolic")
            self._recording_label.set_text(_("Paused"))
            self._recording_pill.add_css_class("paused")
        else:
            self._recording_icon.set_from_icon_name("media-record-symbolic")
            self._recording_label.set_text(_("Recording"))
            self._recording_pill.remove_css_class("paused")

    def _on_incognito_toggled(self, button):
        active = button.get_active()
        self._update_recording_pill(active)
        if self.monitor is None:
            return
        self.monitor.set_incognito(active)
        button.set_tooltip_text(
            _("Incognito mode: ON — clipboard not recorded")
            if active
            else _("Incognito mode: OFF")
        )
        # Surface (or clear) the privacy banner so the state is visible and
        # the "Resume recording" action is reachable. Without this the
        # incognito-on banner and its resume action were dead code.
        if active:
            self._show_edge_state("incognito-on")
        else:
            self._dismiss_edge_banner("incognito-on")

    def set_incognito(self, active):
        """Public entry point to set incognito state (used at launch).

        Drives the header toggle button so the monitor, tooltip and
        privacy banner all stay in sync through the one handler.
        """
        self._incognito_btn.set_active(bool(active))

    def _on_prefs_clicked(self, _button):
        from clipman.preferences import ClipmanPreferences

        prefs = ClipmanPreferences(
            self.db, self, on_setting_changed=self._on_setting_changed
        )
        # In-surface dialog anchored to the popup so it can't open behind
        # it on Wayland; tracked so dismiss-on-focus-loss is guarded.
        self._register_child(prefs)
        prefs.present(self)

    def _on_setting_changed(self, key, value):
        """Hot-reload settings the popup cares about.

        The preferences window calls this from each row's notify
        handler. Anything not listed here is persisted but applied on
        next launch (e.g. ``incognito_on_launch``).
        """
        if key == "theme":
            self._theme = (
                value if value in ("auto", "dark", "light") else DEFAULT_THEME
            )
            self._apply_theme()
            self._apply_css()  # palette block depends on the theme
        elif key == "use_catppuccin":
            self._use_catppuccin = str(value).lower() not in ("false", "0", "")
            self._apply_css()
        elif key == "show_count_badges":
            self._show_count_badges = str(value).lower() not in (
                "false", "0", ""
            )
            self._update_filter_counts()
        elif key == "font_size":
            try:
                self._font_size = max(8, min(20, int(value)))
            except (TypeError, ValueError):
                self._font_size = DEFAULT_FONT_SIZE
            self._apply_css()
        elif key == "font_color":
            self._font_color = value or DEFAULT_FONT_COLOR
            self._apply_css()
        elif key == "opacity":
            try:
                self.set_opacity(max(0.3, min(1.0, float(value))))
            except (TypeError, ValueError):
                # Non-numeric value persisted by an older daemon — log
                # and keep the current opacity rather than crashing.
                logger.debug(
                    "opacity setting not coercible: %r", value, exc_info=True
                )
        elif key == "sensitive_timeout":
            try:
                self._sensitive_timeout = max(10, min(300, int(value)))
            except (TypeError, ValueError):
                self._sensitive_timeout = DEFAULT_SENSITIVE_TIMEOUT
        elif key in ("backup_succeeded", "restore_succeeded",
                     "sensitive_purged"):
            if self.get_visible():
                self.refresh()
        elif key == "backup_failed":
            self._show_edge_state("backup-failed")
        elif key == "restore_failed":
            self._show_edge_state("restore-failed")

    def _on_key_pressed(self, _controller, keyval, _keycode, _state):
        """Wire the shortcuts advertised in the footer hints.

        The footer promises ``↵ Paste · ⌫ Delete · P Pin · Esc Close``.
        Escape/Enter work regardless of focus; Delete and P are gated on
        the search entry NOT having focus so they stay usable as literal
        text editing while the user is typing a query.

        Returns ``True`` when the key was handled (stops propagation),
        ``False`` otherwise so gated/unhandled keys still reach the
        search entry.
        """
        if keyval == Gdk.KEY_Escape:
            self._hide()
            return True

        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_ISO_Enter):
            self._activate_selected()
            return True

        search_focused = self.search_entry.has_focus()

        # Down arrow from the search entry drops focus into the list so
        # the user can start arrow-navigating rows. Up/Down within the
        # list itself is native to Gtk.ListView.
        if keyval == Gdk.KEY_Down and search_focused:
            if self._selection.get_n_items() > 0:
                if self._selection.get_selected() == Gtk.INVALID_LIST_POSITION:
                    self._selection.set_selected(0)
                self.listview.grab_focus()
                return True
            return False

        # Delete and P are literal text editing while typing a query —
        # only treat them as shortcuts when the search entry is unfocused.
        if search_focused:
            return False

        if keyval == Gdk.KEY_Delete:
            return self._delete_selected()

        if keyval in (Gdk.KEY_p, Gdk.KEY_P):
            return self._pin_selected()

        return False

    # ------------------------------------------------------------------
    # Keyboard / click shared action helpers
    # ------------------------------------------------------------------

    def _selected_item(self):
        """Return the selected ``ClipItem``, or the first item if none is
        selected. Returns ``None`` when the list is empty.
        """
        if self._selection.get_n_items() == 0:
            return None
        pos = self._selection.get_selected()
        if pos == Gtk.INVALID_LIST_POSITION:
            return self._selection.get_item(0)
        return self._selection.get_item(pos)

    def _activate_selected(self):
        """Paste the selected item (or the first item if none selected).

        Shared by the Enter shortcut. Returns ``True`` when an item was
        acted on, ``False`` when the list is empty.
        """
        item = self._selected_item()
        if item is None:
            return False
        if item.kind == "snippet":
            self._paste_snippet(item.data)
        elif item.kind == "entry":
            self._paste_entry(item.data)
        else:
            return False
        return True

    def _delete_selected(self):
        """Delete the selected entry (mirrors its trash button).

        Snippets have no inline delete here, so non-entry items are
        ignored. Returns ``True`` when an entry was deleted.
        """
        item = self._selected_item()
        if item is None or item.kind != "entry":
            return False
        entry_id = item.data.get("id")
        if not entry_id:
            return False
        self.db.delete_entry(entry_id)
        self.refresh()
        return True

    def _pin_selected(self):
        """Toggle pin on the selected entry (mirrors its star button).

        Snippets have no pin, so non-entry items are ignored. Returns
        ``True`` when an entry's pin state was toggled.
        """
        item = self._selected_item()
        if item is None or item.kind != "entry":
            return False
        entry_id = item.data.get("id")
        if not entry_id:
            return False
        self.db.toggle_pin(entry_id)
        self.refresh()
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_time(self, timestamp):
        diff = time.time() - timestamp
        if diff < 60:
            return _("just now")
        if diff < 3600:
            mins = int(diff / 60)
            return _("{n}m ago").format(n=mins)
        if diff < 86400:
            hours = int(diff / 3600)
            return _("{n}h ago").format(n=hours)
        days = int(diff / 86400)
        return _("{n}d ago").format(n=days)

    def _clamped_default_height(self):
        """Pick a sensible default popup height for the current monitor.

        Uses the primary monitor's geometry and caps at 60% of its
        height, with 540 as the upper bound. Falls back to 540 if the
        monitor metadata isn't queryable (offscreen / headless CI).
        """
        default = 540
        try:
            display = Gdk.Display.get_default()
            if display is None:
                return default
            monitors = display.get_monitors()
            monitor = monitors.get_item(0) if monitors is not None else None
            if monitor is None:
                return default
            geom = monitor.get_geometry()
            return min(default, int(0.6 * geom.height))
        except Exception:
            logger.debug(
                "monitor geometry unavailable; using default popup height",
                exc_info=True,
            )
            return default

    def _cleanup_sensitive(self):
        deleted = self.db.delete_expired_sensitive(self._sensitive_timeout)
        if deleted > 0 and self.get_visible():
            self.refresh()
        return True

    def _move_to_cursor(self):
        """Ask the GNOME Shell extension to reposition us near the cursor.

        Best-effort — if the extension isn't installed the window stays
        wherever the compositor placed it, which is acceptable for Phase 1.
        """
        self._cursor_move_id = 0
        # A stale timer must never re-position/re-activate a hidden popup
        # (the extension now also focuses the window on move).
        if not self.get_visible():
            return False
        try:
            import dbus
            bus = dbus.SessionBus()
            proxy = bus.get_object(
                "org.gnome.Shell.Extensions.clipman",
                "/org/gnome/Shell/Extensions/clipman",
            )
            iface = dbus.Interface(
                proxy, "org.gnome.Shell.Extensions.clipman"
            )
            iface.MoveWindowToCursor("Clipman")
        except Exception as exc:
            # The python-dbus module or the GNOME Shell extension may
            # be absent — both are expected on non-GNOME desktops, and
            # dbus raises a wide variety of error types when the bus
            # name isn't owned. Trace the failure for support requests
            # but leave the window where the compositor placed it.
            logger.debug(
                "Shell extension move-to-cursor unavailable: %s",
                exc,
                exc_info=True,
            )
        return False

    # ------------------------------------------------------------------
    # Toggle (public — dbus_service.Toggle() routes here)
    # ------------------------------------------------------------------

    def _child_is_open(self):
        d = self._child_dialog
        return d is not None and d.get_mapped()

    def _register_child(self, dialog, on_closed=None):
        """Track an in-app dialog so dismiss-on-focus-loss doesn't hide the
        popup from under it, and so hiding the popup can force-close it."""
        self._child_dialog = dialog

        def _closed(d):
            if self._child_dialog is d:
                self._child_dialog = None
            if on_closed is not None:
                on_closed(d)
            # A focus-loss suppressed while the dialog was up is now
            # actionable — re-evaluate so the popup can dismiss.
            self._on_active_changed()

        dialog.connect("closed", _closed)

    def _present_focused(self):
        """Show + focus the popup and (re)arm cursor positioning.

        Centralises the Wayland show path so toggle(), dbus Show() and the
        paste-target re-show all grab focus the same way.
        """
        self.set_visible(True)
        self.present()
        # grab_focus no-ops on a not-yet-focused Wayland toplevel; defer.
        GLib.idle_add(self.search_entry.grab_focus)
        if self._cursor_move_id:
            GLib.source_remove(self._cursor_move_id)
        self._cursor_move_id = GLib.timeout_add(50, self._move_to_cursor)

    def _hide(self):
        """Hide the popup and tear down transient state (cursor timer, search
        debounce, any open child dialog) so nothing resurfaces or latches."""
        if self._cursor_move_id:
            GLib.source_remove(self._cursor_move_id)
            self._cursor_move_id = 0
        self._cancel_search_debounce()
        self._cancel_fill()
        if self._child_dialog is not None:
            try:
                self._child_dialog.force_close()
            except Exception:
                logger.debug("force_close child dialog failed", exc_info=True)
            self._child_dialog = None
        self.set_visible(False)

    def _on_active_changed(self, *_args):
        """Hide the popup when it loses focus (Win+V click-outside dismiss).

        Skipped while an in-app dialog is still mapped so opening
        preferences / snippets doesn't hide the popup from under them.
        """
        if (
            not self.get_property("is-active")
            and self.get_visible()
            and not self._child_is_open()
        ):
            self._hide()

    def toggle(self):
        if self.get_visible():
            self._hide()
            return
        self.refresh()
        self._present_focused()
