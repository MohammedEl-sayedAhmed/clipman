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
import subprocess
import time
from html import escape
from string import Template

import gi

# Direct submodule imports — avoid ``from clipman import …`` which
# CodeQL flags as a cyclic import (window <-> clipman package).
from gettext import gettext as _

import clipman.updates as updates
from clipman._version import __version__

logger = logging.getLogger(__name__)

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, GLib, Gtk

DEFAULT_FONT_SIZE = 12
DEFAULT_THEME = "dark"
DEFAULT_SENSITIVE_TIMEOUT = 30
DEFAULT_FONT_COLOR = "default"

# Fallback CSS token used when the user picked the "default" preset.
# Keeps the .clip-row .title colour aligned with libadwaita's card fg.
_DEFAULT_FONT_COLOR_TOKEN = "@card_fg_color"

# Hard-coded per-type accent tints — matched to docs/design/tokens.css.
# Used to colour the 3px prefix bar on each Adw.ActionRow so users can
# scan the list by type without reading the subtitle.
TYPE_CLASSES = {
    "text": "clip-type-text",
    "image": "clip-type-image",
    "link": "clip-type-link",
    "code": "clip-type-code",
    "snip": "clip-type-snip",
}


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
        self._active_filter = "all"
        self._css_provider = None
        self._current_edge_banner = None

        self.set_title("Clipman")
        self.set_default_size(380, 540)
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
        """Translate the ``font_color`` preset id to a CSS colour value.

        ``FONT_COLOR_PRESETS`` lives in ``preferences.py``; we import it
        lazily because ``preferences`` pulls in Adw at module scope and
        we want ``window.py`` importable for headless tests.
        """
        from clipman.preferences import FONT_COLOR_PRESETS

        for preset_id, hex_value, _tooltip in FONT_COLOR_PRESETS:
            if preset_id == self._font_color and hex_value:
                return hex_value
        return _DEFAULT_FONT_COLOR_TOKEN

    def _apply_css(self):
        """Inject ``style.css`` with Python ``string.Template`` substitutions.

        The template exposes ``${font_size}`` and ``${font_color}`` so
        font size and the .clip-row title colour both hot-reload from
        the preferences window without touching the .css file on disk.
        """
        css_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "style.css"
        )
        with open(css_path, "r", encoding="utf-8") as f:
            css_string = Template(f.read()).safe_substitute(
                font_size=str(self._font_size),
                font_color=self._resolve_font_color(),
            )

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
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(root)

        # -- Header bar (incognito start, prefs end) -----------------------
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="Clipman"))

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

        root.append(header)

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
        first = None
        for fid, label in [
            ("all", _("All")),
            ("pinned", _("Pinned")),
            ("snippets", _("Snippets")),
        ]:
            btn = Gtk.ToggleButton(label=label)
            btn.add_css_class("filter-tab")
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
        root.append(self._filter_box)

        # -- Scrollable list + empty status page --------------------------
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.BROWSE)
        self.listbox.set_activate_on_single_click(True)
        self.listbox.add_css_class("clipman-list")
        self.listbox.add_css_class("boxed-list")
        self.listbox.connect("row-activated", self._on_row_activated)
        scrolled.set_child(self.listbox)

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

        # -- Footer hints --------------------------------------------------
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        footer.add_css_class("clipman-footer")
        footer.set_halign(Gtk.Align.CENTER)
        footer.set_margin_top(4)
        footer.set_margin_bottom(6)
        for text in [
            "↵ " + _("Paste"),
            "⌫ " + _("Delete"),
            "P " + _("Pin"),
            "Esc " + _("Close"),
        ]:
            lbl = Gtk.Label(label=text)
            lbl.add_css_class("clipman-footer-hint")
            footer.append(lbl)
        root.append(footer)

    # ------------------------------------------------------------------
    # Compatibility shim for dbus_service.Show() — GTK 4 widgets are
    # visible by default, so ``show_all`` is just ``set_visible(True)``.
    # Kept here so the existing dbus_service.py keeps resolving against
    # the window object without modification.
    # ------------------------------------------------------------------

    def show_all(self):
        self.set_visible(True)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self):
        # GTK 4 ListBox row clearing.
        while True:
            row = self.listbox.get_row_at_index(0)
            if row is None:
                break
            self.listbox.remove(row)

        is_snippets = self._active_filter == "snippets"
        is_pinned_only = self._active_filter == "pinned"

        if is_snippets:
            entries = (
                self.db.search_snippets(self._search_query)
                if self._search_query
                else self.db.get_snippets()
            )
            rows = [self._make_snippet_row(e) for e in entries]
        else:
            if self._search_query:
                entries = self.db.search(self._search_query)
            else:
                entries = self.db.get_entries(limit=200)
            if is_pinned_only:
                entries = [e for e in entries if e["pinned"]]
            rows = [self._make_entry_row(e) for e in entries]

        if not rows:
            if self._search_query:
                state_id = "no-results"
            elif is_snippets:
                state_id = "no-snippets-yet"
            else:
                state_id = "empty"
            self._show_edge_state(state_id)
            return

        self._list_stack.set_visible_child_name("list")
        for row in rows:
            self.listbox.append(row)

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

        # AlertDialog presents itself modally; nothing to mount.
        if kind == "alertdialog":
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

    def _on_edge_action(self, action_id):
        """Dispatch the ``action_id`` strings declared in ``edge_states.py``.

        Anything unrecognised is logged at warning level so missing
        wiring is visible during development but the popup keeps
        running.
        """
        if action_id == "clear-search":
            self.search_entry.set_text("")
            self._search_query = ""
            self.refresh()
        elif action_id == "open-snippets-dialog":
            self._on_snippets_clicked(None)
        elif action_id in (
            "open-prefs-appearance",
            "open-prefs-privacy",
            "open-prefs-storage",
            "open-prefs-shortcuts",
            "open-prefs-updates",
        ):
            self._on_prefs_clicked(None)
        elif action_id == "open-extensions-page":
            self._open_url(
                "https://extensions.gnome.org/extension/9407/clipman/"
            )
        elif action_id == "retry-network":
            self.refresh_update_banner()
        elif action_id == "retry-restore":
            # Re-issue the restore flow via preferences; the actual
            # restore happens there, this just brings the user back.
            self._on_prefs_clicked(None)
        elif action_id == "resume-recording":
            if self.monitor is not None:
                self.monitor.set_incognito(False)
            self._incognito_btn.set_active(False)
            self._dismiss_edge_banner()
        elif action_id == "pause-recording":
            if self.monitor is not None:
                self.monitor.set_incognito(True)
            self._incognito_btn.set_active(True)
        elif action_id == "dismiss-banner":
            self._dismiss_edge_banner()
        elif action_id == "close-dialog":
            # AlertDialog handles its own close; no extra work needed.
            pass
        else:
            logger.warning("unhandled edge-state action_id: %r", action_id)

    def _dismiss_edge_banner(self):
        if self._current_edge_banner is not None:
            self._edge_banner_slot.remove(self._current_edge_banner)
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

    def _make_entry_row(self, entry):
        ctype = entry.get("content_type") or "text"
        text = entry.get("content_text") or ""
        first_line = text.split("\n", 1)[0].strip() if text else ""
        if ctype == "image":
            title = "[Image]"
        else:
            title = first_line[:120] or _("(empty)")

        row = Adw.ActionRow()
        row.set_title(escape(title))
        row.set_subtitle(
            f"{ctype.upper()} · {self._format_time(entry['accessed_at'])}"
        )
        row.set_activatable(True)
        row.add_css_class("clip-row")
        row.entry_data = entry
        row.row_kind = "entry"

        # 3px coloured prefix bar (per-type tint).
        bar = Gtk.Box()
        bar.add_css_class("clip-type-bar")
        bar.add_css_class(TYPE_CLASSES.get(ctype, "clip-type-text"))
        bar.set_size_request(3, -1)
        bar.set_valign(Gtk.Align.FILL)
        row.add_prefix(bar)

        # Image entries get a 32x32 thumbnail so users can scan the list
        # visually instead of relying on the literal ``[Image]`` title.
        if ctype == "image":
            image_path = entry.get("image_path")
            from clipman.database import _safe_image_path

            if image_path and _safe_image_path(image_path):
                try:
                    texture = Gdk.Texture.new_from_filename(image_path)
                    thumb = Gtk.Picture.new_for_paintable(texture)
                    thumb.set_can_shrink(True)
                    thumb.set_content_fit(Gtk.ContentFit.COVER)
                    thumb.set_size_request(32, 32)
                    thumb.set_valign(Gtk.Align.CENTER)
                    thumb.add_css_class("clip-thumb")
                    row.add_prefix(thumb)
                except Exception:
                    # Corrupt file or unsupported format — fall back to
                    # the bare ``[Image]`` label rather than crashing.
                    logger.debug(
                        "thumbnail failed for %r", image_path, exc_info=True
                    )

        pin_btn = Gtk.Button.new_from_icon_name(
            "starred-symbolic" if entry["pinned"]
            else "non-starred-symbolic"
        )
        pin_btn.add_css_class("flat")
        pin_btn.set_valign(Gtk.Align.CENTER)
        pin_btn.set_tooltip_text(
            _("Unpin") if entry["pinned"] else _("Pin")
        )
        pin_btn.connect("clicked", self._on_pin_clicked, entry["id"])
        row.add_suffix(pin_btn)

        del_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        del_btn.add_css_class("flat")
        del_btn.set_valign(Gtk.Align.CENTER)
        del_btn.set_tooltip_text(_("Delete"))
        del_btn.connect("clicked", self._on_delete_clicked, entry["id"])
        row.add_suffix(del_btn)

        return row

    def _make_snippet_row(self, snippet):
        row = Adw.ActionRow()
        row.set_title(escape(snippet["name"]))
        preview = (snippet.get("content_text") or "").split("\n", 1)[0]
        row.set_subtitle(escape(preview[:120]))
        row.set_activatable(True)
        row.add_css_class("clip-row")
        row.snippet_data = snippet
        row.row_kind = "snippet"

        bar = Gtk.Box()
        bar.add_css_class("clip-type-bar")
        bar.add_css_class(TYPE_CLASSES["snip"])
        bar.set_size_request(3, -1)
        bar.set_valign(Gtk.Align.FILL)
        row.add_prefix(bar)

        return row

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

    def _copy_to_clipboard(self, text):
        if self.monitor:
            self.monitor.set_self_copy(True)
        try:
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set(text)
        except Exception:
            # GTK clipboard API can fail under Xwayland or before the
            # display is ready; fall through to the wl-copy CLI which
            # is more reliable on Wayland sessions.
            logger.debug("GTK clipboard.set failed", exc_info=True)
            try:
                proc = subprocess.Popen(
                    ["wl-copy"],
                    stdin=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                proc.communicate(input=text.encode("utf-8"))
            except OSError:
                # wl-copy isn't installed either — the user will have
                # to copy manually. Log so we can diagnose support
                # requests but don't surface a popup error.
                logger.debug("wl-copy fallback failed", exc_info=True)

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
        try:
            texture = Gdk.Texture.new_from_filename(image_path)
            clipboard = Gdk.Display.get_default().get_clipboard()
            clipboard.set_texture(texture)
            return True
        except Exception:
            logger.debug(
                "Gdk.Texture clipboard set failed; trying wl-copy fallback",
                exc_info=True,
            )
        try:
            with open(image_path, "rb") as fh:
                proc = subprocess.Popen(
                    ["wl-copy", "--type", "image/png"],
                    stdin=fh,
                    stderr=subprocess.DEVNULL,
                )
                proc.communicate()
            return proc.returncode == 0
        except OSError:
            logger.debug("wl-copy image fallback failed", exc_info=True)
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
                any_binary_available = True
                return False
            except FileNotFoundError:
                continue
            except subprocess.SubprocessError:
                any_binary_available = True
                continue
        if not any_binary_available:
            # Neither wtype nor ydotool is installed. Show the popup
            # again with the dedicated edge state so the user has a
            # clear next step.
            self.set_visible(True)
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
        GLib.timeout_add(80, self._simulate_paste)

    def _paste_snippet(self, snippet):
        text = snippet.get("content_text") or ""
        if not text:
            return
        text = self._expand_snippet_tokens(text)
        self._copy_to_clipboard(text)
        self.set_visible(False)
        GLib.timeout_add(80, self._simulate_paste)

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
        self._search_query = entry.get_text().strip()
        self.refresh()

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
        dialog.connect("closed", lambda _d: self.refresh())
        dialog.present(self)

    def _on_row_activated(self, _listbox, row):
        if row is None:
            return
        if getattr(row, "row_kind", None) == "snippet":
            self._paste_snippet(row.snippet_data)
        elif getattr(row, "row_kind", None) == "entry":
            self._paste_entry(row.entry_data)

    def _on_pin_clicked(self, _button, entry_id):
        self.db.toggle_pin(entry_id)
        self.refresh()

    def _on_delete_clicked(self, _button, entry_id):
        self.db.delete_entry(entry_id)
        self.refresh()

    def _on_incognito_toggled(self, button):
        if self.monitor is None:
            return
        self.monitor.set_incognito(button.get_active())
        button.set_tooltip_text(
            _("Incognito mode: ON — clipboard not recorded")
            if button.get_active()
            else _("Incognito mode: OFF")
        )

    def _on_prefs_clicked(self, _button):
        from clipman.preferences import ClipmanPreferences

        prefs = ClipmanPreferences(
            self.db, self, on_setting_changed=self._on_setting_changed
        )
        prefs.present()

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

    def _on_key_pressed(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            self.set_visible(False)
            return True
        return False

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

    def toggle(self):
        if self.get_visible():
            self.set_visible(False)
            return
        self.refresh()
        self.set_visible(True)
        self.present()
        self.search_entry.grab_focus()
        GLib.timeout_add(50, self._move_to_cursor)
