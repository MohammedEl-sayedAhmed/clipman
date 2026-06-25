"""Clipman popup window — GTK 4 + libadwaita 1.4+.

Phase 1 of the GTK4 + libadwaita port. Surface parity with the current
GTK3 popup is intentionally limited: this file covers the clipboard
list, search, filter switcher, paste-on-activate, pin / delete row
actions, the headerbar (with incognito + close), and the update
banner. Settings, the snippets editor, the edit dialog, full per-clip
sensitive-masking UI and the 15 edge-state surfaces all move to a
separate Phase 2 PR.

The public API of this module is kept identical to the GTK3 version:
``ClipmanWindow.toggle()``, ``.refresh()``, ``.refresh_update_banner()``
are the only call sites used by ``app.py`` and ``dbus_service.py``.
"""

import datetime
import subprocess
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, GLib, Gtk, Pango  # noqa: E402

from clipman import _, __version__, keybindings, updates


DEFAULT_OPACITY = 1.0
DEFAULT_FONT_SIZE = 12
DEFAULT_MAX_HISTORY = 500
DEFAULT_THEME = "dark"
DEFAULT_FONT_COLOR = ""
DEFAULT_SENSITIVE_TIMEOUT = 30
DEFAULT_PASTE_MODE = "auto"

PASTE_MODES = [
    ("auto", "Auto-detect"),
    ("ctrl-v", "Ctrl+V"),
    ("ctrl-shift-v", "Ctrl+Shift+V"),
    ("shift-insert", "Shift+Insert"),
]


class ClipmanWindow(Adw.ApplicationWindow):
    """Floating clipboard popup. Uses Adw.ApplicationWindow as the host so
    it picks up libadwaita's style refresh + StyleManager dark/light
    handling for free."""

    def __init__(self, *, application, db, monitor):
        super().__init__(application=application)
        self.db = db
        self.monitor = monitor

        self._search_query = ""
        self._active_filter = "all"
        self._css_provider = None

        self.set_title("Clipman")
        self.set_default_size(420, 640)
        self.set_resizable(True)
        # GTK 4 dropped set_skip_taskbar_hint / set_keep_above / set_type_hint.
        # Those used to be no-ops on Wayland anyway; the compositor decides
        # taskbar + stacking. The popup behaviour matches a normal window.

        # ----- Settings load (same key names as v1) ----------------------
        self._opacity = self._clamp(
            float(self.db.get_setting("opacity", str(DEFAULT_OPACITY))),
            0.3, 1.0)
        self.set_opacity(self._opacity)

        self._font_size = int(self._clamp(
            float(self.db.get_setting("font_size", str(DEFAULT_FONT_SIZE))),
            8, 20))

        self._max_history = int(self._clamp(
            float(self.db.get_setting("max_entries", str(DEFAULT_MAX_HISTORY))),
            50, 5000))

        saved_theme = self.db.get_setting("theme", DEFAULT_THEME)
        self._theme = saved_theme if saved_theme in ("dark", "light") else DEFAULT_THEME
        self._apply_theme_to_style_manager()

        self._font_color = self.db.get_setting("font_color", DEFAULT_FONT_COLOR)

        self._sensitive_timeout = int(self._clamp(
            float(self.db.get_setting("sensitive_timeout", str(DEFAULT_SENSITIVE_TIMEOUT))),
            10, 300))

        self._toggle_shortcut = self.db.get_setting(
            "toggle_shortcut", keybindings.DEFAULT_TOGGLE_BINDING
        )
        saved_paste = self.db.get_setting("paste_mode", DEFAULT_PASTE_MODE)
        valid_modes = {m[0] for m in PASTE_MODES}
        self._paste_mode = saved_paste if saved_paste in valid_modes else DEFAULT_PASTE_MODE

        # Keep the same incognito-mode bookkeeping the monitor reads.
        self._incognito = False

        # Periodic sensitive-data cleanup (same 10s cadence as GTK3 v1).
        GLib.timeout_add_seconds(10, self._cleanup_sensitive)

        self._apply_css()
        self._build_ui()

        # Wire global keyboard shortcuts (Escape closes, etc.) via an
        # event controller — GTK 4 dropped `connect("key-press-event")`.
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        # Don't auto-show; the app's activate() calls toggle() which
        # makes the window visible. Default state is hidden.
        self.set_visible(False)

        # If a previous run cached a newer version that's still not
        # dismissed, surface the banner immediately on startup.
        self.refresh_update_banner()

    # ------------------------------------------------------------------
    # Theme / CSS
    # ------------------------------------------------------------------

    def _apply_theme_to_style_manager(self):
        """Tell libadwaita's StyleManager which color scheme to render.

        Adw.StyleManager is the canonical channel: setting
        FORCE_DARK / FORCE_LIGHT triggers the dark/light variants of
        every Adw widget and the matching system palette."""
        mgr = Adw.StyleManager.get_default()
        if self._theme == "light":
            mgr.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        else:
            mgr.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

    def _apply_css(self):
        display = Gdk.Display.get_default()
        if display is None:
            return
        if self._css_provider is not None:
            Gtk.StyleContext.remove_provider_for_display(display, self._css_provider)
        self._css_provider = Gtk.CssProvider()
        css = self._render_css()
        # GTK 4: load_from_data takes (str, int length). Pass -1 for "use
        # the full string"; GObject-introspection will compute it.
        self._css_provider.load_from_data(css, -1)
        Gtk.StyleContext.add_provider_for_display(
            display,
            self._css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _render_css(self):
        """Pull the design-token-flavored CSS template off disk and inject
        the per-run dynamic values (font size, font color)."""
        import os
        css_path = os.path.join(os.path.dirname(__file__), "style.css")
        with open(css_path, "r", encoding="utf-8") as f:
            tpl = f.read()
        font_color_rule = ""
        if self._font_color:
            font_color_rule = f"""
            .clipman-window .clip-text,
            .clipman-window .clip-snippet-name {{ color: {self._font_color}; }}
            """
        return tpl.replace("${font_size}", str(self._font_size)) + font_color_rule

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.add_css_class("clipman-window")

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # ----- HeaderBar -------------------------------------------------
        header = Adw.HeaderBar()
        header.add_css_class("flat")
        outer.append(header)

        title_label = Gtk.Label(label="Clipman")
        title_label.add_css_class("title-3")
        header.set_title_widget(title_label)

        self._incognito_btn = Gtk.ToggleButton()
        self._incognito_btn.set_icon_name("face-cool-symbolic")  # placeholder until we ship a custom icon
        self._incognito_btn.set_tooltip_text(_("Incognito mode — pause clipboard history"))
        self._incognito_btn.connect("toggled", self._on_incognito_toggle)
        header.pack_start(self._incognito_btn)

        prefs_btn = Gtk.Button.new_from_icon_name("preferences-system-symbolic")
        prefs_btn.set_tooltip_text(_("Preferences"))
        prefs_btn.connect("clicked", self._on_prefs_clicked)
        header.pack_end(prefs_btn)

        # ----- Update banner (Adw.Banner) --------------------------------
        # Lives just under the headerbar and below it but above the search.
        self._update_banner = Adw.Banner.new("")
        self._update_banner.set_button_label(_("Release notes"))
        self._update_banner.set_revealed(False)
        self._update_banner.connect("button-clicked", self._on_update_link_clicked)
        outer.append(self._update_banner)

        # ----- Search ----------------------------------------------------
        search_wrap = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        search_wrap.add_css_class("clipman-header")
        search_wrap.set_margin_start(8)
        search_wrap.set_margin_end(8)
        search_wrap.set_margin_top(6)
        search_wrap.set_margin_bottom(4)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_hexpand(True)
        self.search_entry.set_placeholder_text(_("Search clipboard…"))
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.add_css_class("clipman-search")
        search_wrap.append(self.search_entry)

        outer.append(search_wrap)

        # ----- Filter view-switcher (All / Pinned / Snippets) ------------
        filter_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        filter_row.set_margin_start(8)
        filter_row.set_margin_end(8)
        filter_row.set_margin_bottom(6)
        filter_row.add_css_class("filter-bar")

        self._filter_buttons = {}
        for fid, label in (("all", _("All")),
                           ("pinned", _("Pinned")),
                           ("snippets", _("Snippets"))):
            btn = Gtk.ToggleButton(label=label)
            btn.add_css_class("filter-tab")
            if fid == self._active_filter:
                btn.add_css_class("filter-tab-active")
                btn.set_active(True)
            btn.connect("toggled", self._on_filter_toggled, fid)
            self._filter_buttons[fid] = btn
            filter_row.append(btn)

        outer.append(filter_row)

        # ----- Clip list -------------------------------------------------
        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("clipman-list")
        self.listbox.connect("row-activated", self._on_row_activated)
        scroller.set_child(self.listbox)
        outer.append(scroller)

        # Empty state placeholder
        self._empty_state = Adw.StatusPage()
        self._empty_state.set_icon_name("edit-paste-symbolic")
        self._empty_state.set_title(_("Nothing copied yet"))
        self._empty_state.set_description(
            _("Copy text or an image — it'll show up here. Press Super+V any time to summon this window.")
        )
        self._empty_state.set_visible(False)
        outer.append(self._empty_state)

        # ----- Footer ----------------------------------------------------
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        footer.add_css_class("clipman-footer")
        footer.set_margin_start(12)
        footer.set_margin_end(12)
        footer.set_margin_top(6)
        footer.set_margin_bottom(6)

        for hint in (_("↵  Paste"), _("⌫  Delete"), _("P  Pin"), _("Esc  Close")):
            lbl = Gtk.Label(label=hint)
            lbl.add_css_class("clipman-footer-hint")
            footer.append(lbl)

        outer.append(footer)

        self.set_content(outer)

    # ------------------------------------------------------------------
    # List rendering
    # ------------------------------------------------------------------

    def refresh(self):
        """Rebuild the list from db state. Public API; called by app and dbus."""
        # Empty the listbox.
        child = self.listbox.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.listbox.remove(child)
            child = next_child

        if self._active_filter == "snippets":
            self._refresh_snippets()
        else:
            self._refresh_entries()

    def _refresh_entries(self):
        only_pinned = (self._active_filter == "pinned")
        entries = self.db.get_entries(
            limit=self._max_history,
            search=self._search_query or None,
            only_pinned=only_pinned,
        )

        if not entries:
            self._empty_state.set_title(_("Nothing copied yet") if not self._search_query
                                        else _("No matches"))
            self._empty_state.set_visible(True)
            return
        self._empty_state.set_visible(False)

        for entry in entries:
            row = self._build_clip_row(entry)
            self.listbox.append(row)

    def _refresh_snippets(self):
        snippets = self.db.get_snippets(search=self._search_query or None)
        if not snippets:
            self._empty_state.set_title(_("No snippets"))
            self._empty_state.set_description(
                _("Snippets are reusable text fragments. Add some from preferences.")
            )
            self._empty_state.set_visible(True)
            return
        self._empty_state.set_visible(False)

        for snip in snippets:
            row = self._build_snippet_row(snip)
            self.listbox.append(row)

    def _build_clip_row(self, entry):
        row = Adw.ActionRow()
        row.set_activatable(True)
        row.add_css_class("clip-row")
        row._clipman_entry = entry  # stash for activation handler
        row._clipman_kind = "entry"

        entry_type = entry.get("type", "text")
        text = entry.get("text", "") or ""

        title = self._first_line(text, max_chars=60) or _("(empty)")
        row.set_title(GLib.markup_escape_text(title))

        meta = self._row_meta(entry)
        if meta:
            row.set_subtitle(meta)

        # Type-color indicator: a thin left bar.
        type_indicator = Gtk.Box()
        type_indicator.add_css_class("clip-type-bar")
        type_indicator.add_css_class(f"clip-type-{entry_type}")
        type_indicator.set_size_request(3, -1)
        row.add_prefix(type_indicator)

        # Pin button on the right.
        pin_btn = Gtk.Button.new_from_icon_name(
            "starred-symbolic" if entry.get("pinned") else "non-starred-symbolic"
        )
        pin_btn.add_css_class("flat")
        pin_btn.set_valign(Gtk.Align.CENTER)
        pin_btn.set_tooltip_text(_("Unpin") if entry.get("pinned") else _("Pin"))
        pin_btn.connect("clicked", self._on_pin_click, entry["id"])
        row.add_suffix(pin_btn)

        del_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        del_btn.add_css_class("flat")
        del_btn.set_valign(Gtk.Align.CENTER)
        del_btn.set_tooltip_text(_("Delete"))
        del_btn.connect("clicked", self._on_delete_click, entry["id"])
        row.add_suffix(del_btn)

        return row

    def _build_snippet_row(self, snip):
        row = Adw.ActionRow()
        row.set_activatable(True)
        row.add_css_class("clip-row")
        row._clipman_entry = snip
        row._clipman_kind = "snippet"
        row.set_title(GLib.markup_escape_text(snip.get("name") or _("(unnamed)")))
        preview = self._first_line(snip.get("content", "") or "", max_chars=70)
        if preview:
            row.set_subtitle(preview)

        type_indicator = Gtk.Box()
        type_indicator.add_css_class("clip-type-bar")
        type_indicator.add_css_class("clip-type-snip")
        type_indicator.set_size_request(3, -1)
        row.add_prefix(type_indicator)
        return row

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clamp(value, lo, hi):
        return max(lo, min(hi, value))

    @staticmethod
    def _first_line(text, max_chars=80):
        if not text:
            return ""
        line = text.splitlines()[0] if text else ""
        if len(line) > max_chars:
            return line[:max_chars - 1] + "…"
        return line

    def _row_meta(self, entry):
        entry_type = entry.get("type", "text")
        ts = entry.get("timestamp")
        rel = self._format_time(ts) if ts else ""
        type_label = {
            "text":    _("Text"),
            "image":   _("Image"),
            "url":     _("URL"),
            "code":    _("Code"),
        }.get(entry_type, entry_type.title())
        # Pango markup: subtitle is plain text in Adw.ActionRow; markup
        # would need set_subtitle_use_markup(True), which we skip here to
        # avoid escaping every dynamic field.
        return f"{type_label} · {rel}" if rel else type_label

    @staticmethod
    def _format_time(timestamp):
        try:
            then = datetime.datetime.fromtimestamp(float(timestamp))
        except (TypeError, ValueError):
            return ""
        delta = datetime.datetime.now() - then
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return _("just now")
        if seconds < 3600:
            return _("{}m ago").format(seconds // 60)
        if seconds < 86400:
            return _("{}h ago").format(seconds // 3600)
        if seconds < 7 * 86400:
            return _("{}d ago").format(seconds // 86400)
        return then.strftime("%Y-%m-%d")

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_search_changed(self, entry):
        self._search_query = entry.get_text().strip()
        self.refresh()

    def _on_filter_toggled(self, button, filter_id):
        if not button.get_active():
            # Don't allow deselecting the active filter.
            button.set_active(True)
            return
        for fid, btn in self._filter_buttons.items():
            if fid != filter_id:
                btn.set_active(False)
                btn.remove_css_class("filter-tab-active")
            else:
                btn.add_css_class("filter-tab-active")
        self._active_filter = filter_id
        self.refresh()

    def _on_row_activated(self, _listbox, row):
        kind = getattr(row, "_clipman_kind", None)
        entry = getattr(row, "_clipman_entry", None)
        if entry is None:
            return
        if kind == "snippet":
            self._paste_snippet(entry)
        else:
            self._paste_entry(entry)

    def _on_pin_click(self, _button, entry_id):
        self.db.toggle_pin(entry_id)
        self.refresh()

    def _on_delete_click(self, _button, entry_id):
        self.db.delete_entry(entry_id)
        self.refresh()

    def _on_incognito_toggle(self, button):
        self._incognito = button.get_active()
        if self.monitor:
            self.monitor.set_incognito(self._incognito)

    def _on_prefs_clicked(self, _button):
        # TODO(phase 2): open Adw.PreferencesWindow. For now this is a
        # no-op so the rest of the popup is usable. The settings panel
        # in the GTK3 version covered: opacity, font size, max-history,
        # theme, font color, sensitive timeout, paste mode, toggle
        # shortcut, snippets manager, backup/restore, updates opt-in.
        pass

    def _on_update_link_clicked(self, _banner):
        latest = updates.cached_latest(self.db) or {}
        url = latest.get("url")
        if url:
            Gtk.show_uri(self, url, Gdk.CURRENT_TIME)

    def _on_key_pressed(self, _ctrl, keyval, _keycode, _state):
        # Escape closes; route to our hide path so the daemon stays
        # alive.
        from gi.repository import Gdk as _Gdk
        if keyval == _Gdk.KEY_Escape:
            self.hide_popup()
            return True
        return False

    # ------------------------------------------------------------------
    # Paste
    # ------------------------------------------------------------------

    def _paste_entry(self, entry):
        text = entry.get("text") or ""
        if not text:
            return
        self._copy_to_clipboard(text)
        self.db.bump_use(entry["id"])
        self.hide_popup()
        # Brief delay so the window-hide animation finishes before we
        # simulate the paste keystroke — otherwise the paste lands on
        # the popup instead of the previous focus.
        GLib.timeout_add(80, self._simulate_paste)

    def _paste_snippet(self, snip):
        content = snip.get("content") or ""
        if not content:
            return
        content = self._expand_snippet(content)
        self._copy_to_clipboard(content)
        self.db.bump_snippet_use(snip["id"])
        self.hide_popup()
        GLib.timeout_add(80, self._simulate_paste)

    @staticmethod
    def _expand_snippet(text):
        # Same {{date}} / {{time}} / {{clipboard}} expansions the GTK3
        # version did. Clipboard expansion is best-effort.
        now = datetime.datetime.now()
        out = text.replace("{{date}}", now.strftime("%Y-%m-%d"))
        out = out.replace("{{time}}", now.strftime("%H:%M"))
        return out

    def _copy_to_clipboard(self, text):
        try:
            clip = Gdk.Display.get_default().get_clipboard()
            clip.set(text)
        except Exception:
            # Fall back to wl-copy (works under Wayland without GTK CSD).
            try:
                proc = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
                proc.communicate(text.encode("utf-8"), timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def _simulate_paste(self):
        # Use ydotool / wtype on Wayland to inject Ctrl+V into the
        # previously focused window. The same fallback chain the GTK3
        # version used.
        for cmd in (["wtype", "-M", "ctrl", "v"],
                    ["ydotool", "key", "ctrl+v"]):
            try:
                subprocess.run(cmd, check=False, timeout=2)
                break
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return False

    # ------------------------------------------------------------------
    # Update banner
    # ------------------------------------------------------------------

    def refresh_update_banner(self):
        latest = updates.cached_latest(self.db) if self.db else None
        if not latest or not latest.get("is_newer"):
            self._update_banner.set_revealed(False)
            return
        title = _("Clipman {ver} is available").format(ver=latest.get("version", ""))
        self._update_banner.set_title(title)
        self._update_banner.set_revealed(True)

    # ------------------------------------------------------------------
    # Sensitive cleanup
    # ------------------------------------------------------------------

    def _cleanup_sensitive(self):
        try:
            self.db.purge_sensitive(self._sensitive_timeout)
            if self.get_visible():
                self.refresh()
        except Exception:
            pass
        return True

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def hide_popup(self):
        # Adw.ApplicationWindow has set_visible() / present(); use
        # set_visible(False) for hide so the application "hold" keeps
        # the daemon alive.
        self.set_visible(False)

    def toggle(self):
        """Public API — called by app + dbus_service."""
        if self.get_visible():
            self.hide_popup()
        else:
            self.refresh()
            self.set_visible(True)
            self.present()
            self.search_entry.grab_focus()
            GLib.timeout_add(50, self._move_to_cursor)

    def _move_to_cursor(self):
        try:
            import dbus
            bus = dbus.SessionBus()
            proxy = bus.get_object(
                "org.gnome.Shell.Extensions.clipman", "/org/gnome/Shell/Extensions/clipman"
            )
            iface = dbus.Interface(proxy, "org.gnome.Shell.Extensions.clipman")
            iface.MoveWindowToCursor("Clipman")
        except Exception:
            pass
        return False
