"""GTK 4 + libadwaita preferences window for Clipman.

Six panes mapped to ``docs/design/preferences.html``: Appearance,
Privacy, Shortcuts, Storage, Updates, About. All settings persist via
``db.set_setting`` and every change fires ``on_setting_changed(key,
value)`` so the popup can hot-reload theme / font_size / opacity
without restarting the daemon.

The window is constructed with the Adw.PreferencesGroup / Adw.SpinRow
/ Adw.SwitchRow / Adw.ComboRow / Adw.ActionRow rows that libadwaita
1.4+ ships — never raw Gtk.Box rows — so spacing, padding, and
accessibility roles all match the rest of the desktop.

on_setting_changed contract
---------------------------

The callback receives ``(key: str, value)`` for two distinct
categories of message:

1. Real settings writes — ``key`` is a row in the ``settings`` table
   and ``value`` is the new value (already coerced to the row's
   logical Python type, e.g. ``bool``, ``int``, ``float``, ``str``).
   Today's keys: ``theme``, ``font_color``, ``opacity``, ``font_size``,
   ``show_count_badges``, ``incognito_on_launch``, ``sensitive_timeout``,
   ``paste_mode``, ``max_entries``. Listeners hot-reload CSS / theme /
   paste behaviour off these.

2. Synthetic UI events — ``key`` is one of the strings in
   ``EVENT_KEYS`` and ``value`` carries an event-specific payload
   (a backup file path, an exception message, or ``True``). These are
   not persisted to the DB; they only exist so the parent window can
   show a banner / toast. Receivers should ignore unknown synthetic
   keys instead of writing them back.
"""

import logging
import os
import re
import subprocess
import time

import gi

# Direct submodule imports — avoid ``from clipman import …`` which
# CodeQL flags as a cyclic import (preferences <-> clipman package).
from gettext import gettext as _

import clipman.keybindings as keybindings
import clipman.updates as updates
from clipman._version import __version__
from clipman.database import DB_PATH

logger = logging.getLogger(__name__)

# Module-level GTK4 binding. Wrapped because some CI sandboxes ship a
# placeholder ``gi`` shim that lacks ``require_version`` (or has the
# typelibs unavailable). Re-raise as RuntimeError so importers can
# guard with a single except clause.
try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402
except (AttributeError, ValueError, ImportError) as e:
    raise RuntimeError(
        "GTK 4 + libadwaita not available: %s" % e
    ) from e

# Paste modes the popup understands. Index 0 is the best-effort
# default that works in every focused-window scenario; the others
# force a specific keystroke when an app insists on one. ``window.py``
# re-exports this list so dbus_service can validate D-Bus arg values
# without importing the preferences module (which would pull in Adw
# for headless tests).
PASTE_MODES = [
    ("auto", _("Auto-paste (best effort)")),
    ("ctrl-v", _("Simulate Ctrl+V")),
    ("ctrl-shift-v", _("Simulate Ctrl+Shift+V")),
    ("shift-insert", _("Simulate Shift+Insert")),
]

# Six accent presets (mapped to the mockup) + a sentinel "default"
# that clears the override and falls back to the theme accent.
FONT_COLOR_PRESETS = [
    ("default", None, _("Default theme color")),
    ("green", "#a6e3a1", _("Green")),
    ("peach", "#fab387", _("Peach")),
    ("mauve", "#cba6f7", _("Mauve")),
    ("pink", "#f5c2e7", _("Pink")),
    ("teal", "#94e2d5", _("Teal")),
]

THEMES = [
    ("auto", _("Follow system")),
    ("dark", _("Dark")),
    ("light", _("Light")),
]

# Synthetic events emitted through on_setting_changed alongside real
# settings writes. Listed here so listeners (window.py) can branch on
# the set without duplicating string literals, and so future events
# get added in exactly one place.
#
#   sensitive_purged      value=True             user clicked Purge now
#   backup_succeeded      value=<dest path str>  export_backup returned
#   backup_failed         value=<error str>      export_backup raised
#   restore_succeeded     value=<source path>    import_backup returned
#   restore_failed        value=<error str>      import_backup raised
EVENT_KEYS = frozenset({
    "sensitive_purged",
    "backup_succeeded",
    "backup_failed",
    "restore_succeeded",
    "restore_failed",
})


class ClipmanPreferences(Adw.Dialog):
    """Six-pane preferences dialog with a left sidebar.

    An ``Adw.Dialog`` (not a separate top-level window) so it presents
    in-surface, anchored to the popup via ``present(parent)`` — a
    top-level window opened *behind* the popup on Wayland and looked
    unresponsive. The layout matches ``docs/design/preferences.html``:
    a persistent icon+label sidebar on the left and the selected page on
    the right (Adw.PreferencesDialog's bottom view-switcher tabs read as
    cramped at this size).

    ``on_setting_changed`` is a callable that the parent window passes
    in; it's invoked with ``(key, value)`` whenever any persisted
    setting changes so the popup can re-apply CSS / theme / paste-mode
    without a restart.
    """

    def __init__(self, db, parent=None, on_setting_changed=None):
        super().__init__()
        self.db = db
        self._on_setting_changed = on_setting_changed or (lambda k, v: None)
        self._kbd_dialog = None  # held so the GC doesn't collect mid-capture
        # As an Adw.Dialog this is NOT a Gtk.Window, so it can't be the
        # parent of a Gtk.FileChooserNative. Keep the real toplevel (the
        # ClipmanWindow passed in) for the backup/restore choosers.
        self._parent_window = parent

        self.set_title(_("Preferences"))
        # Tall enough that the Appearance page fits without a scrollbar
        # (Adw.Dialog clamps to the work area on small screens anyway).
        self.set_content_width(760)
        self.set_content_height(690)

        # Pages carry their own title + icon; the sidebar reads both.
        self._stack = Gtk.Stack()
        self._stack.set_hexpand(True)
        self._stack.set_vexpand(True)

        self._sidebar = Gtk.ListBox()
        self._sidebar.add_css_class("navigation-sidebar")
        self._sidebar.set_selection_mode(Gtk.SelectionMode.BROWSE)
        self._sidebar.connect("row-selected", self._on_nav_selected)

        for pid, page in [
            ("appearance", self._build_appearance_page()),
            ("privacy", self._build_privacy_page()),
            ("shortcuts", self._build_shortcuts_page()),
            ("storage", self._build_storage_page()),
            ("updates", self._build_updates_page()),
            ("about", self._build_about_page()),
        ]:
            self._stack.add_named(page, pid)
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(6)
            box.set_margin_end(6)
            box.append(Gtk.Image.new_from_icon_name(page.get_icon_name()))
            box.append(Gtk.Label(label=page.get_title(), xalign=0))
            row.set_child(box)
            row._page_id = pid
            row._page_title = page.get_title()
            self._sidebar.append(row)

        self._title_widget = Adw.WindowTitle(
            title=_("Preferences"), subtitle=""
        )
        header = Adw.HeaderBar()
        header.set_title_widget(self._title_widget)

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(
            Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC
        )
        sidebar_scroll.set_child(self._sidebar)
        sidebar_scroll.set_size_request(180, -1)
        sidebar_scroll.add_css_class("prefs-sidebar")

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        content.append(sidebar_scroll)
        content.append(
            Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        )
        content.append(self._stack)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(content)
        self.set_child(toolbar_view)

        self._sidebar.select_row(self._sidebar.get_row_at_index(0))

    def _on_nav_selected(self, _listbox, row):
        if row is None:
            return
        self._stack.set_visible_child_name(row._page_id)
        self._title_widget.set_title(row._page_title)

    def show_page(self, page_id):
        """Select ``page_id`` in the sidebar (deep links from edge states)."""
        i = 0
        while True:
            row = self._sidebar.get_row_at_index(i)
            if row is None:
                break
            if row._page_id == page_id:
                self._sidebar.select_row(row)
                break
            i += 1

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    def _save(self, key, value):
        """Persist + notify. ``value`` is coerced to ``str`` for SQLite.

        Booleans are stored lowercase (``true``/``false``) — Python's
        ``str(True)`` is ``"True"``, which broke case-sensitive readers
        (e.g. ``incognito_on_launch == "true"`` in app.py never matched).
        """
        if isinstance(value, bool):
            value = "true" if value else "false"
        self.db.set_setting(key, str(value))
        try:
            self._on_setting_changed(key, value)
        except Exception:
            # The callback is best-effort. A broken hot-reload must
            # never break the preferences window itself.
            pass

    def _emit_event(self, key, value):
        """Fire a synthetic on_setting_changed event (no DB write).

        ``key`` must be a member of ``EVENT_KEYS`` — anything else is
        a programmer error (the caller probably meant ``_save``).
        Like ``_save``, the listener's exceptions are swallowed.
        """
        assert key in EVENT_KEYS, (
            f"unknown synthetic event {key!r}; add it to EVENT_KEYS"
        )
        try:
            self._on_setting_changed(key, value)
        except Exception:
            # CodeQL py/empty-except: a misbehaving listener must
            # never break the preferences window. Surface at debug so
            # operators can diagnose with -v without polluting INFO.
            logger.debug(
                "on_setting_changed listener raised for event %s",
                key, exc_info=True,
            )

    def _get_float(self, key, default):
        try:
            return float(self.db.get_setting(key, str(default)))
        except (TypeError, ValueError):
            return default

    def _get_int(self, key, default):
        try:
            return int(float(self.db.get_setting(key, str(default))))
        except (TypeError, ValueError):
            return default

    def _get_bool(self, key, default):
        raw = (self.db.get_setting(key, "true" if default else "false") or "")
        return raw.lower() == "true"

    # ------------------------------------------------------------------
    # Pane 1: Appearance
    # ------------------------------------------------------------------

    def _build_appearance_page(self):
        page = Adw.PreferencesPage()
        page.set_title(_("Appearance"))
        page.set_icon_name("applications-graphics-symbolic")

        # --- Theme group --------------------------------------------------
        theme_group = Adw.PreferencesGroup()
        theme_group.set_title(_("Theme"))
        theme_group.set_description(
            _("Choose how Clipman looks. The popup updates immediately.")
        )

        theme_model = Gtk.StringList.new([label for _id, label in THEMES])
        theme_row = Adw.ComboRow()
        theme_row.set_title(_("Color scheme"))
        theme_row.set_subtitle(
            _("Dark uses Catppuccin Mocha; Light uses warm stone.")
        )
        theme_row.set_model(theme_model)
        current_theme = self.db.get_setting("theme", "dark")
        theme_ids = [tid for tid, _label in THEMES]
        theme_row.set_selected(
            theme_ids.index(current_theme) if current_theme in theme_ids else 1
        )
        theme_row.connect(
            "notify::selected",
            lambda row, _pspec: self._save(
                "theme", theme_ids[row.get_selected()]
            ),
        )
        theme_group.add(theme_row)

        catppuccin_row = Adw.SwitchRow()
        catppuccin_row.set_title(_("Catppuccin theme"))
        catppuccin_row.set_subtitle(
            _("Off: follow your system GNOME theme and accent color.")
        )
        catppuccin_row.set_active(self._get_bool("use_catppuccin", True))
        catppuccin_row.connect(
            "notify::active",
            lambda row, _pspec: self._save(
                "use_catppuccin", "true" if row.get_active() else "false"
            ),
        )
        theme_group.add(catppuccin_row)
        page.add(theme_group)

        # --- Accent / font color group ------------------------------------
        accent_group = Adw.PreferencesGroup()
        accent_group.set_title(_("Accent"))
        accent_group.set_description(
            _("Accent for controls and highlights; font color for clip text.")
        )

        # Accent colour picker — drives toggles, active tabs, focus rings,
        # the recording pill. A picker (rather than the pale default) lets
        # the user choose a high-contrast accent.
        accent_color_row = Adw.ActionRow()
        accent_color_row.set_title(_("Accent color"))
        accent_color_row.set_subtitle(
            _("Toggles, active tabs and highlights. Pick any colour or reset.")
        )
        cur_accent = self.db.get_setting("accent_color", "default")
        accent_dialog = Gtk.ColorDialog()
        accent_dialog.set_with_alpha(False)
        self._accent_btn = Gtk.ColorDialogButton(dialog=accent_dialog)
        self._accent_btn.set_valign(Gtk.Align.CENTER)
        argba = Gdk.RGBA()
        argba.parse(self._accent_display_hex(cur_accent))
        self._accent_btn.set_rgba(argba)
        self._accent_btn.connect("notify::rgba", self._on_accent_rgba)
        accent_reset = Gtk.Button.new_from_icon_name("edit-undo-symbolic")
        accent_reset.set_tooltip_text(_("Reset to theme default"))
        accent_reset.add_css_class("flat")
        accent_reset.set_valign(Gtk.Align.CENTER)
        accent_reset.connect("clicked", self._on_accent_reset)
        accent_color_row.add_suffix(self._accent_btn)
        accent_color_row.add_suffix(accent_reset)
        accent_group.add(accent_color_row)

        accent_row = Adw.ActionRow()
        accent_row.set_title(_("Font color"))
        accent_row.set_subtitle(
            _("Pick any colour, or reset to the theme default.")
        )

        current_font_color = self.db.get_setting("font_color", "default")
        color_dialog = Gtk.ColorDialog()
        color_dialog.set_with_alpha(False)
        self._font_color_btn = Gtk.ColorDialogButton(dialog=color_dialog)
        self._font_color_btn.set_valign(Gtk.Align.CENTER)
        rgba = Gdk.RGBA()
        rgba.parse(self._font_color_display_hex(current_font_color))
        self._font_color_btn.set_rgba(rgba)
        self._font_color_btn.connect(
            "notify::rgba", self._on_font_color_rgba
        )

        reset_btn = Gtk.Button.new_from_icon_name("edit-undo-symbolic")
        reset_btn.set_tooltip_text(_("Reset to theme default"))
        reset_btn.add_css_class("flat")
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.connect("clicked", self._on_font_color_reset)

        accent_row.add_suffix(self._font_color_btn)
        accent_row.add_suffix(reset_btn)
        accent_group.add(accent_row)
        page.add(accent_group)

        # --- Layout group -------------------------------------------------
        layout_group = Adw.PreferencesGroup()
        layout_group.set_title(_("Layout"))

        opacity_row = Adw.SpinRow.new_with_range(0.3, 1.0, 0.05)
        opacity_row.set_title(_("Window opacity"))
        opacity_row.set_subtitle(
            _("100% is fully opaque. Lower values are see-through.")
        )
        opacity_row.set_digits(2)
        opacity_row.set_value(self._get_float("opacity", 1.0))
        # Adw.SpinRow inherits "changed" from Gtk.Editable, which only
        # fires while the user is typing into the embedded entry — it
        # does NOT fire when the stepper arrows or scroll wheel adjust
        # the value. The "notify::value" notification on the underlying
        # property is the single source of truth across keyboard,
        # mouse, and accessibility input.
        opacity_row.connect(
            "notify::value",
            lambda r, _p: self._save("opacity", r.get_value()),
        )
        layout_group.add(opacity_row)

        font_row = Adw.SpinRow.new_with_range(8, 20, 1)
        font_row.set_title(_("Font size"))
        font_row.set_subtitle(_("Affects clip content; UI chrome unchanged."))
        font_row.set_value(self._get_int("font_size", 12))
        font_row.connect(
            "notify::value",
            lambda r, _p: self._save("font_size", int(r.get_value())),
        )
        layout_group.add(font_row)

        badges_row = Adw.SwitchRow()
        badges_row.set_title(_("Show count badges on filter tabs"))
        badges_row.set_active(self._get_bool("show_count_badges", True))
        badges_row.connect(
            "notify::active",
            lambda r, _p: self._save("show_count_badges", r.get_active()),
        )
        layout_group.add(badges_row)
        page.add(layout_group)

        return page

    def _accent_display_hex(self, value):
        """Hex to show in the accent button (custom hex, or the Catppuccin
        mauve default so the button isn't blank)."""
        if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            return value
        return "#cba6f7"

    def _on_accent_rgba(self, button, _pspec):
        rgba = button.get_rgba()
        hex_value = "#{:02x}{:02x}{:02x}".format(
            round(rgba.red * 255),
            round(rgba.green * 255),
            round(rgba.blue * 255),
        )
        self._save("accent_color", hex_value)

    def _on_accent_reset(self, _button):
        self._save("accent_color", "default")

    def _font_color_display_hex(self, value):
        """Resolve a stored font_color (hex, legacy preset id, or
        'default') to a hex the colour button can display."""
        if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            return value
        for preset_id, hex_value, _tip in FONT_COLOR_PRESETS:
            if preset_id == value and hex_value:
                return hex_value
        # 'default' — show a neutral so the button isn't misleading.
        return "#9e9e9e"

    def _on_font_color_rgba(self, button, _pspec):
        rgba = button.get_rgba()
        hex_value = "#{:02x}{:02x}{:02x}".format(
            round(rgba.red * 255),
            round(rgba.green * 255),
            round(rgba.blue * 255),
        )
        self._save("font_color", hex_value)

    def _on_font_color_reset(self, _button):
        self._save("font_color", "default")

    # ------------------------------------------------------------------
    # Pane 2: Privacy
    # ------------------------------------------------------------------

    def _build_privacy_page(self):
        page = Adw.PreferencesPage()
        page.set_title(_("Privacy"))
        page.set_icon_name("system-lock-screen-symbolic")

        incog_group = Adw.PreferencesGroup()
        incog_group.set_title(_("Incognito mode"))
        incog_group.set_description(
            _("When on, new copies are ignored. History stays untouched.")
        )

        incog_row = Adw.SwitchRow()
        incog_row.set_title(_("Incognito mode"))
        incog_row.set_subtitle(
            _("Takes effect immediately and applies on every launch. "
              "Useful on shared machines or before a password manager.")
        )
        incog_row.set_active(self._get_bool("incognito_on_launch", False))
        incog_row.connect(
            "notify::active",
            lambda r, _p: self._save("incognito_on_launch", r.get_active()),
        )
        incog_group.add(incog_row)
        page.add(incog_group)

        sensitive_group = Adw.PreferencesGroup()
        sensitive_group.set_title(_("Sensitive data"))
        sensitive_group.set_description(
            _("Auto-clear clips matching password / token / card patterns.")
        )

        timeout_row = Adw.SpinRow.new_with_range(10, 300, 5)
        timeout_row.set_title(_("Auto-clear delay"))
        timeout_row.set_subtitle(_("Seconds before sensitive entries are purged."))
        timeout_row.set_value(self._get_int("sensitive_timeout", 30))
        timeout_row.connect(
            "notify::value",
            lambda r, _p: self._save("sensitive_timeout", int(r.get_value())),
        )
        sensitive_group.add(timeout_row)

        purge_row = Adw.ActionRow()
        purge_row.set_title(_("Purge sensitive entries now"))
        purge_row.set_subtitle(
            _("Clears every entry flagged as sensitive immediately.")
        )
        purge_btn = Gtk.Button(label=_("Purge now"))
        purge_btn.set_valign(Gtk.Align.CENTER)
        purge_btn.add_css_class("destructive-action")
        purge_btn.connect("clicked", self._on_purge_clicked)
        purge_row.add_suffix(purge_btn)
        purge_row.set_activatable_widget(purge_btn)
        sensitive_group.add(purge_row)
        page.add(sensitive_group)

        return page

    def _on_purge_clicked(self, _btn):
        # Force-expire by passing a zero timeout — same code path the
        # daemon's periodic cleanup uses.
        try:
            self.db.delete_expired_sensitive(0)
        except Exception:
            # The DB layer can raise OperationalError, IntegrityError,
            # or a wrapped FileNotFoundError if storage has been moved
            # mid-session. Trace it and tell the parent window the
            # purge happened so it refreshes — the user can retry from
            # the new state.
            logger.debug(
                "purge-sensitive failed; treating as no-op", exc_info=True
            )
        self._emit_event("sensitive_purged", True)

    # ------------------------------------------------------------------
    # Pane 3: Shortcuts
    # ------------------------------------------------------------------

    def _build_shortcuts_page(self):
        page = Adw.PreferencesPage()
        page.set_title(_("Shortcuts"))
        page.set_icon_name("input-keyboard-symbolic")

        global_group = Adw.PreferencesGroup()
        global_group.set_title(_("Global shortcut"))
        global_group.set_description(
            _("Bound through the GNOME Shell extension. Changes apply on next "
              "daemon restart.")
        )

        self._toggle_row = Adw.ActionRow()
        self._toggle_row.set_title(_("Toggle clipboard popup"))
        binding = keybindings.get_toggle_binding() or keybindings.DEFAULT_TOGGLE_BINDING
        self._toggle_row.set_subtitle(
            keybindings.format_binding_for_display(binding) or _("Not set")
        )
        change_btn = Gtk.Button(label=_("Change…"))
        change_btn.set_valign(Gtk.Align.CENTER)
        change_btn.add_css_class("flat")
        change_btn.connect("clicked", self._on_change_binding)
        self._toggle_row.add_suffix(change_btn)
        self._toggle_row.set_activatable_widget(change_btn)
        global_group.add(self._toggle_row)
        page.add(global_group)

        paste_group = Adw.PreferencesGroup()
        paste_group.set_title(_("Paste behaviour"))

        paste_model = Gtk.StringList.new([label for _id, label in PASTE_MODES])
        paste_row = Adw.ComboRow()
        paste_row.set_title(_("When I select a clip"))
        paste_row.set_subtitle(
            _("Auto-paste simulates a keystroke into the focused window.")
        )
        paste_row.set_model(paste_model)
        current_paste = self.db.get_setting("paste_mode", "auto")
        paste_ids = [pid for pid, _label in PASTE_MODES]
        paste_row.set_selected(
            paste_ids.index(current_paste) if current_paste in paste_ids else 0
        )
        paste_row.connect(
            "notify::selected",
            lambda row, _pspec: self._save(
                "paste_mode", paste_ids[row.get_selected()]
            ),
        )
        paste_group.add(paste_row)
        page.add(paste_group)

        return page

    def _on_change_binding(self, _btn):
        dialog = Adw.AlertDialog.new(
            _("Press a key combination"),
            _("Hold modifiers (Ctrl, Alt, Super, Shift) and press a key. "
              "Press Escape to cancel."),
        )
        dialog.add_response("cancel", _("Cancel"))
        controller = Gtk.EventControllerKey()
        controller.connect(
            "key-pressed", self._on_capture_key_pressed, dialog
        )
        dialog.add_controller(controller)
        self._kbd_dialog = dialog
        dialog.present(self)

    def _on_capture_key_pressed(self, _controller, keyval, _keycode, state, dialog):
        if keyval == Gdk.KEY_Escape:
            dialog.close()
            return True
        binding = keybindings.keyval_to_binding(keyval, state)
        if binding is None:
            return False  # pure modifier — wait for the real key
        if keybindings.set_toggle_binding(binding):
            self._toggle_row.set_subtitle(
                keybindings.format_binding_for_display(binding)
            )
        else:
            # Registration failed (gsettings schema missing / non-GNOME):
            # show the guided dialog instead of silently doing nothing
            # (mockup shortcut-failed).
            self._present_shortcut_failed()
        dialog.close()
        return True

    def _present_shortcut_failed(self):
        from clipman.edge_states import render_edge_state

        parent = self._parent_window
        if parent is not None and hasattr(parent, "_on_edge_action"):
            parent._show_edge_state("shortcut-failed")
            return
        # Standalone (tests / no parent): present unwired on this dialog.
        dlg = render_edge_state("shortcut-failed")
        dlg.present(self)

    # ------------------------------------------------------------------
    # Pane 4: Storage
    # ------------------------------------------------------------------

    def _build_storage_page(self):
        page = Adw.PreferencesPage()
        page.set_title(_("Storage"))
        page.set_icon_name("drive-harddisk-symbolic")

        cap_group = Adw.PreferencesGroup()
        cap_group.set_title(_("History"))

        max_row = Adw.SpinRow.new_with_range(50, 5000, 50)
        max_row.set_title(_("Maximum entries to keep"))
        max_row.set_subtitle(
            _("Older entries roll off when the cap is reached.")
        )
        max_row.set_value(self._get_int("max_entries", 500))
        max_row.connect(
            "notify::value",
            lambda r, _p: self._save("max_entries", int(r.get_value())),
        )
        cap_group.add(max_row)

        path_row = Adw.ActionRow()
        path_row.set_title(_("Database location"))
        path_row.set_subtitle(str(DB_PATH))
        cap_group.add(path_row)

        stats_row = Adw.ActionRow()
        stats_row.set_title(_("Stored entries"))
        stats_row.set_subtitle(self._format_db_stats())
        cap_group.add(stats_row)
        page.add(cap_group)

        backup_group = Adw.PreferencesGroup()
        # Group titles are parsed as Pango markup — a bare "&" logs a
        # markup-parse warning and drops the text; escape it.
        backup_group.set_title(_("Backup &amp; restore"))
        backup_group.set_description(
            _("Export your history as a portable .clipman file.")
        )

        backup_row = Adw.ActionRow()
        backup_row.set_title(_("Export backup"))
        backup_row.set_subtitle(
            _("Saves a copy you can store off-machine.")
        )
        backup_btn = Gtk.Button(label=_("Export…"))
        backup_btn.set_valign(Gtk.Align.CENTER)
        backup_btn.connect("clicked", self._on_backup_clicked)
        backup_row.add_suffix(backup_btn)
        backup_row.set_activatable_widget(backup_btn)
        backup_group.add(backup_row)

        restore_row = Adw.ActionRow()
        restore_row.set_title(_("Restore from backup"))
        restore_row.set_subtitle(
            _("Replaces all current history — you'll be asked to confirm.")
        )
        restore_btn = Gtk.Button(label=_("Restore…"))
        restore_btn.set_valign(Gtk.Align.CENTER)
        restore_btn.connect("clicked", self._on_restore_clicked)
        restore_row.add_suffix(restore_btn)
        restore_row.set_activatable_widget(restore_btn)
        backup_group.add(restore_row)
        page.add(backup_group)

        return page

    def _format_db_stats(self):
        try:
            count = self.db.count_entries()
        except Exception:
            count = 0
        try:
            size = os.path.getsize(DB_PATH)
        except OSError:
            size = 0
        size_kb = size / 1024.0
        size_str = (
            f"{size_kb / 1024.0:.1f} MB" if size_kb >= 1024 else f"{size_kb:.0f} KB"
        )
        return f"{count} entries · {size_str}"

    def _on_backup_clicked(self, _btn):
        chooser = Gtk.FileChooserNative.new(
            _("Export backup"),
            self._parent_window,
            Gtk.FileChooserAction.SAVE,
            _("Save"),
            _("Cancel"),
        )
        chooser.set_current_name(
            f"clipman-{time.strftime('%Y%m%d-%H%M%S')}.db"
        )
        chooser.connect("response", self._on_backup_response, chooser)
        chooser.show()

    def _on_backup_response(self, _native, response, chooser):
        if response == Gtk.ResponseType.ACCEPT:
            file = chooser.get_file()
            if file is not None:
                try:
                    self.db.export_backup(file.get_path())
                    self._emit_event("backup_succeeded", file.get_path())
                except Exception as exc:
                    self._emit_event("backup_failed", str(exc))
        chooser.destroy()

    def _on_restore_clicked(self, _btn):
        chooser = Gtk.FileChooserNative.new(
            _("Restore from backup"),
            self._parent_window,
            Gtk.FileChooserAction.OPEN,
            _("Open"),
            _("Cancel"),
        )
        chooser.connect("response", self._on_restore_response, chooser)
        chooser.show()

    def _on_restore_response(self, _native, response, chooser):
        if response == Gtk.ResponseType.ACCEPT:
            file = chooser.get_file()
            if file is not None:
                self._confirm_restore(file.get_path())
        chooser.destroy()

    def _confirm_restore(self, source_path):
        """Show a destructive AlertDialog before overwriting the DB.

        Restore is irreversible: the running connection is closed,
        ``DB_PATH`` is replaced, and any unbacked-up history is lost.
        We snapshot the current DB to a sibling ``.bak`` file (using
        the same ``export_backup`` code path the user invokes manually)
        so a botched restore can still be rolled back from disk.
        """
        dialog = Adw.AlertDialog.new(
            _("Restore from backup?"),
            _(
                "This replaces your entire clipboard history with the "
                "contents of:\n\n{path}\n\nA safety copy of the current "
                "database will be written next to it as a .bak file. "
                "This action cannot be undone from inside Clipman."
            ).format(path=source_path),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("restore", _("Restore"))
        dialog.set_response_appearance(
            "restore", Adw.ResponseAppearance.DESTRUCTIVE
        )
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_restore_confirmed, source_path)
        dialog.present(self)

    def _on_restore_confirmed(self, _dialog, response, source_path):
        if response != "restore":
            return
        # Snapshot current DB to a sibling .bak before overwriting.
        # If the snapshot itself fails (e.g. disk full) we abort the
        # restore — the user is better off keeping their current
        # history than losing it to a half-written copy.
        backup_path = str(DB_PATH) + ".bak"
        try:
            self.db.export_backup(backup_path)
        except Exception as exc:
            self._emit_event("restore_failed", str(exc))
            return
        try:
            self.db.import_backup(source_path)
            self._emit_event("restore_succeeded", source_path)
        except Exception as exc:
            self._emit_event("restore_failed", str(exc))

    # ------------------------------------------------------------------
    # Pane 5: Updates
    # ------------------------------------------------------------------

    def _build_updates_page(self):
        page = Adw.PreferencesPage()
        page.set_title(_("Updates"))
        page.set_icon_name("software-update-available-symbolic")

        channel_group = Adw.PreferencesGroup()
        channel_group.set_title(_("Update channel"))
        channel_group.set_description(
            _("Clipman polls the GitHub Releases API at most once per "
              "{hours} hours.").format(
                hours=int(updates.CHECK_INTERVAL_SECONDS / 3600)
            )
        )

        enabled_row = Adw.SwitchRow()
        enabled_row.set_title(_("Check for updates automatically"))
        enabled_row.set_subtitle(
            _("Shows an in-app banner when a newer version is available.")
        )
        enabled_row.set_active(updates._enabled(self.db))
        enabled_row.connect(
            "notify::active",
            lambda r, _p: updates.set_enabled(self.db, r.get_active()),
        )
        channel_group.add(enabled_row)

        freq_row = Adw.ActionRow()
        freq_row.set_title(_("Check frequency"))
        freq_row.set_subtitle(
            _("Every {hours} hours").format(
                hours=int(updates.CHECK_INTERVAL_SECONDS / 3600)
            )
        )
        channel_group.add(freq_row)

        last_row = Adw.ActionRow()
        last_row.set_title(_("Last checked"))
        last_row.set_subtitle(self._format_last_check())
        channel_group.add(last_row)
        page.add(channel_group)

        version_group = Adw.PreferencesGroup()
        version_group.set_title(_("Version"))

        current_row = Adw.ActionRow()
        current_row.set_title(_("Current version"))
        current_row.set_subtitle(f"v{__version__}")
        version_group.add(current_row)

        latest = updates.latest_known(self.db) or _("Unknown")
        latest_row = Adw.ActionRow()
        latest_row.set_title(_("Latest known version"))
        latest_row.set_subtitle(
            f"v{latest}" if latest != _("Unknown") else latest
        )
        version_group.add(latest_row)

        if latest != _("Unknown"):
            notes_row = Adw.ActionRow()
            notes_row.set_title(_("Release notes"))
            link = Gtk.LinkButton.new_with_label(
                f"https://github.com/MohammedEl-sayedAhmed/clipman/"
                f"releases/tag/v{latest}",
                _("View on GitHub"),
            )
            link.set_valign(Gtk.Align.CENTER)
            notes_row.add_suffix(link)
            notes_row.set_activatable_widget(link)
            version_group.add(notes_row)
        page.add(version_group)

        return page

    def _format_last_check(self):
        raw = self.db.get_setting(updates.SETTING_LAST_CHECK, "0")
        try:
            ts = float(raw)
        except (TypeError, ValueError):
            ts = 0.0
        if ts <= 0:
            return _("Never")
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))

    # ------------------------------------------------------------------
    # Pane 6: About
    # ------------------------------------------------------------------

    def _build_about_page(self):
        page = Adw.PreferencesPage()
        page.set_title(_("About"))
        page.set_icon_name("help-about-symbolic")

        about_group = Adw.PreferencesGroup()
        about_group.set_title(_("Clipman"))
        about_group.set_description(
            _("A Wayland-native clipboard history manager built with "
              "GTK 4 + libadwaita.")
        )

        version_row = Adw.ActionRow()
        version_row.set_title(_("Version"))
        version_row.set_subtitle(f"v{__version__}")
        about_group.add(version_row)

        license_row = Adw.ActionRow()
        license_row.set_title(_("License"))
        license_row.set_subtitle("Apache-2.0")
        about_group.add(license_row)

        maintainer_row = Adw.ActionRow()
        maintainer_row.set_title(_("Maintainer"))
        maintainer_row.set_subtitle("Mohammed El-sayed Ahmed")
        about_group.add(maintainer_row)
        page.add(about_group)

        links_group = Adw.PreferencesGroup()
        links_group.set_title(_("Links"))
        for label, url in [
            (_("Repository"),
             "https://github.com/MohammedEl-sayedAhmed/clipman"),
            (_("Website"),
             "https://mohammedel-sayedahmed.github.io/clipman/"),
            (_("Report an issue"),
             "https://github.com/MohammedEl-sayedAhmed/clipman/issues/new"),
            (_("Sponsor on GitHub"),
             "https://github.com/sponsors/MohammedEl-sayedAhmed"),
            (_("Sponsor on PayPal"),
             "https://paypal.me/MohammedElsayedAhmed"),
        ]:
            row = Adw.ActionRow()
            row.set_title(label)
            link = Gtk.LinkButton.new_with_label(url, _("Open"))
            link.set_valign(Gtk.Align.CENTER)
            row.add_suffix(link)
            row.set_activatable_widget(link)
            links_group.add(row)
        page.add(links_group)

        credits_group = Adw.PreferencesGroup()
        credits_group.set_title(_("Credits"))
        credits_group.set_description(
            _("Built with GTK 4 + libadwaita. Catppuccin palette by the "
              "Catppuccin community. Translations contributed by the "
              "community — see po/.")
        )
        page.add(credits_group)

        return page


def open_url(url):
    """Best-effort xdg-open helper. Returns ``False`` so it's GLib-idle safe.

    Restricted to ``http://`` and ``https://`` URLs. ``xdg-open`` will
    happily launch handlers for ``file://``, ``mailto:``, ``gopher:``,
    and (on misconfigured systems) arbitrary scheme-based exec rules,
    so an attacker-controlled string reaching this function would be
    a privilege-escalation surface. Anything that isn't plain web
    traffic is logged and dropped.
    """
    if not isinstance(url, str) or not (
        url.startswith("http://") or url.startswith("https://")
    ):
        logger.debug("open_url refused non-http(s) URL: %r", url)
        return False
    try:
        subprocess.Popen(
            ["xdg-open", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        # xdg-open isn't installed (minimal container) or PATH is
        # broken. Log for diagnostics; the caller has no recovery path.
        logger.debug("xdg-open failed for %s", url, exc_info=True)
    return False


# GLib re-export so future cleanup passes (e.g. paste-mode preview
# animation) can reach the same import without re-grabbing gi.
__all__ = [
    "ClipmanPreferences",
    "EVENT_KEYS",
    "GLib",
    "PASTE_MODES",
    "open_url",
]
