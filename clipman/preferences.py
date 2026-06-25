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
"""

import os
import subprocess
import time

import gi

from clipman import _, __version__, keybindings, updates
from clipman.database import DB_PATH

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

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


class ClipmanPreferences(Adw.PreferencesWindow):
    """Six-pane preferences window.

    ``on_setting_changed`` is a callable that the parent window passes
    in; it's invoked with ``(key, value)`` whenever any persisted
    setting changes so the popup can re-apply CSS / theme / paste-mode
    without a restart.
    """

    def __init__(self, db, parent, on_setting_changed=None):
        super().__init__()
        self.db = db
        self._on_setting_changed = on_setting_changed or (lambda k, v: None)
        self._kbd_dialog = None  # held so the GC doesn't collect mid-capture

        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_search_enabled(True)
        self.set_default_size(820, 600)

        self.add(self._build_appearance_page())
        self.add(self._build_privacy_page())
        self.add(self._build_shortcuts_page())
        self.add(self._build_storage_page())
        self.add(self._build_updates_page())
        self.add(self._build_about_page())

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    def _save(self, key, value):
        """Persist + notify. ``value`` is coerced to ``str`` for SQLite."""
        self.db.set_setting(key, str(value))
        try:
            self._on_setting_changed(key, value)
        except Exception:
            # The callback is best-effort. A broken hot-reload must
            # never break the preferences window itself.
            pass

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
        page.add(theme_group)

        # --- Accent / font color group ------------------------------------
        accent_group = Adw.PreferencesGroup()
        accent_group.set_title(_("Accent"))
        accent_group.set_description(
            _("Color applied to clip text in the popup.")
        )

        accent_row = Adw.ActionRow()
        accent_row.set_title(_("Font color"))
        accent_row.set_subtitle(_("Pick a preset or fall back to default."))

        swatches = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6
        )
        swatches.set_valign(Gtk.Align.CENTER)
        current_font_color = self.db.get_setting("font_color", "default")
        for preset_id, hex_value, tooltip in FONT_COLOR_PRESETS:
            btn = Gtk.Button()
            btn.set_tooltip_text(tooltip)
            btn.add_css_class("circular")
            btn.set_size_request(28, 28)
            if hex_value:
                # Inline CSS provider so the swatch fills with the preset.
                provider = Gtk.CssProvider()
                provider.load_from_data(
                    f"button {{ background: {hex_value}; }}".encode(), -1
                )
                btn.get_style_context().add_provider(
                    provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
            else:
                btn.set_label("A")
            if preset_id == current_font_color:
                btn.add_css_class("suggested-action")
            btn.connect(
                "clicked",
                lambda _b, pid=preset_id: self._on_font_color_picked(pid),
            )
            swatches.append(btn)
        accent_row.add_suffix(swatches)
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
        opacity_row.connect(
            "changed",
            lambda r: self._save("opacity", r.get_value()),
        )
        layout_group.add(opacity_row)

        font_row = Adw.SpinRow.new_with_range(8, 20, 1)
        font_row.set_title(_("Font size"))
        font_row.set_subtitle(_("Affects clip content; UI chrome unchanged."))
        font_row.set_value(self._get_int("font_size", 12))
        font_row.connect(
            "changed",
            lambda r: self._save("font_size", int(r.get_value())),
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

    def _on_font_color_picked(self, preset_id):
        self._save("font_color", preset_id)
        # Caller refreshes; we don't redraw the swatch row here because
        # the user will see the new color in the popup itself.

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
        incog_row.set_title(_("Start in incognito mode"))
        incog_row.set_subtitle(
            _("Useful on shared machines or before opening a password manager.")
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
            "changed",
            lambda r: self._save("sensitive_timeout", int(r.get_value())),
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
            pass
        self._on_setting_changed("sensitive_purged", True)

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
        dialog.close()
        return True

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
            "changed",
            lambda r: self._save("max_entries", int(r.get_value())),
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
        backup_group.set_title(_("Backup & restore"))
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
            self,
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
                    self._on_setting_changed("backup_succeeded", file.get_path())
                except Exception as exc:
                    self._on_setting_changed("backup_failed", str(exc))
        chooser.destroy()

    def _on_restore_clicked(self, _btn):
        chooser = Gtk.FileChooserNative.new(
            _("Restore from backup"),
            self,
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
                try:
                    self.db.import_backup(file.get_path())
                    self._on_setting_changed("restore_succeeded", file.get_path())
                except Exception as exc:
                    self._on_setting_changed("restore_failed", str(exc))
        chooser.destroy()

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
    """Best-effort xdg-open helper. Returns ``False`` so it's GLib-idle safe."""
    try:
        subprocess.Popen(
            ["xdg-open", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass
    return False


# GLib re-export so future cleanup passes (e.g. paste-mode preview
# animation) can reach the same import without re-grabbing gi.
__all__ = ["ClipmanPreferences", "GLib", "PASTE_MODES", "open_url"]
