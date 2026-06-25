"""Master-detail snippets editor implemented as an Adw.Dialog.

Mirrors ``docs/design/snippets.html``: a NavigationSplitView with a
searchable list on the left and a name + multi-line content form on
the right. Save is enabled only while the form is dirty.

The variable substitution hint (``${date}`` / ``${time}`` /
``${clipboard}``) is documentation only — the actual expansion is the
popup's responsibility, not this dialog's.
"""

import gi

# Bind ``_`` directly to gettext.gettext to avoid the
# ``from clipman import _`` back-reference that closes a CodeQL
# py/cyclic-import. clipman/__init__.py has already called
# ``textdomain("clipman")`` by the time this submodule loads.
from gettext import gettext as _

# Module-level GTK4 binding. Wrapped because some CI sandboxes ship a
# placeholder ``gi`` shim that lacks ``require_version`` (or has the
# typelibs unavailable). Re-raise as RuntimeError so importers can
# guard with a single except clause.
try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk  # noqa: E402
except (AttributeError, ValueError, ImportError) as e:
    raise RuntimeError(
        "GTK 4 + libadwaita not available: %s" % e
    ) from e

# Sidebar minimum width — the mockup uses 280px which fits 24 chars
# of snippet name comfortably without truncating common templates.
SIDEBAR_WIDTH = 280


class SnippetsDialog(Adw.Dialog):
    """Floating snippets editor.

    Lifecycle:
    - constructor only assembles widgets; ``present(parent)`` shows it.
    - selecting a snippet loads it into the right pane; switching away
      from a dirty snippet discards changes silently (matches the
      mockup's "save explicit, cancel implicit" semantics).
    - delete / add / save all hit the DB synchronously.
    """

    def __init__(self, db):
        super().__init__()
        self.db = db
        self._snippets = []
        self._selected_id = None
        self._dirty = False
        self._suppress_dirty = False  # set while we programmatically reload

        self.set_title(_("Snippets"))
        self.set_content_width(820)
        self.set_content_height(560)

        split = Adw.NavigationSplitView()
        split.set_min_sidebar_width(SIDEBAR_WIDTH)
        split.set_max_sidebar_width(SIDEBAR_WIDTH)
        split.set_sidebar(self._build_sidebar())
        split.set_content(self._build_content())
        self.set_child(split)

        self._reload_list()

    # ------------------------------------------------------------------
    # Sidebar (master)
    # ------------------------------------------------------------------

    def _build_sidebar(self):
        page = Adw.NavigationPage()
        page.set_title(_("Snippets"))

        toolbar = Adw.ToolbarView()

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        add_btn = Gtk.Button.new_from_icon_name("list-add-symbolic")
        add_btn.set_tooltip_text(_("New snippet"))
        add_btn.add_css_class("flat")
        add_btn.connect("clicked", self._on_new_clicked)
        header.pack_end(add_btn)
        toolbar.add_top_bar(header)

        outer = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=0
        )
        outer.set_vexpand(True)

        self._search = Gtk.SearchEntry()
        self._search.set_placeholder_text(_("Search snippets…"))
        self._search.set_margin_start(8)
        self._search.set_margin_end(8)
        self._search.set_margin_top(8)
        self._search.set_margin_bottom(4)
        self._search.connect("search-changed", lambda _e: self._reload_list())
        outer.append(self._search)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._listbox.add_css_class("navigation-sidebar")
        self._listbox.connect("row-selected", self._on_row_selected)
        scrolled.set_child(self._listbox)
        outer.append(scrolled)

        self._count_label = Gtk.Label()
        self._count_label.add_css_class("dim-label")
        self._count_label.set_margin_top(6)
        self._count_label.set_margin_bottom(6)
        outer.append(self._count_label)

        toolbar.set_content(outer)
        page.set_child(toolbar)
        return page

    # ------------------------------------------------------------------
    # Content (detail)
    # ------------------------------------------------------------------

    def _build_content(self):
        page = Adw.NavigationPage()
        page.set_title(_("Edit snippet"))

        toolbar = Adw.ToolbarView()

        header = Adw.HeaderBar()
        self._title_label = Gtk.Label(label=_("No snippet selected"))
        self._title_label.add_css_class("heading")
        header.set_title_widget(self._title_label)
        toolbar.add_top_bar(header)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_margin_top(16)
        body.set_margin_bottom(8)
        body.set_margin_start(16)
        body.set_margin_end(16)
        body.set_vexpand(True)

        # Name (single-line, AdwEntryRow gives us the labelled chrome).
        name_group = Adw.PreferencesGroup()
        self._name_row = Adw.EntryRow()
        self._name_row.set_title(_("Name"))
        self._name_row.connect("changed", self._on_name_changed)
        name_group.add(self._name_row)
        body.append(name_group)

        # Content (multiline). Adw has no textarea row so we build the
        # AdwPreferencesGroup wrapper manually.
        content_group = Adw.PreferencesGroup()
        content_group.set_title(_("Content"))
        content_group.set_description(
            _("Use ${date}, ${time}, or ${clipboard} for substitutions "
              "when pasting.")
        )

        text_frame = Gtk.Frame()
        text_frame.add_css_class("card")
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(220)
        scrolled.set_vexpand(True)

        self._textview = Gtk.TextView()
        self._textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._textview.set_top_margin(8)
        self._textview.set_bottom_margin(8)
        self._textview.set_left_margin(8)
        self._textview.set_right_margin(8)
        self._textview.set_monospace(True)
        self._textview.get_buffer().connect(
            "changed", self._on_content_changed
        )
        scrolled.set_child(self._textview)
        text_frame.set_child(scrolled)
        content_group.add(text_frame)
        body.append(content_group)

        # Meta row: use count + variable hint.
        self._meta_label = Gtk.Label()
        self._meta_label.set_halign(Gtk.Align.START)
        self._meta_label.add_css_class("dim-label")
        self._meta_label.add_css_class("caption")
        body.append(self._meta_label)

        toolbar.set_content(body)

        # Footer: Delete on the left, Cancel + Save on the right.
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        footer.set_margin_top(8)
        footer.set_margin_bottom(12)
        footer.set_margin_start(16)
        footer.set_margin_end(16)

        self._delete_btn = Gtk.Button(label=_("Delete"))
        self._delete_btn.add_css_class("destructive-action")
        self._delete_btn.set_sensitive(False)
        self._delete_btn.connect("clicked", self._on_delete_clicked)
        footer.append(self._delete_btn)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        footer.append(spacer)

        self._cancel_btn = Gtk.Button(label=_("Cancel"))
        self._cancel_btn.connect("clicked", self._on_cancel_clicked)
        footer.append(self._cancel_btn)

        self._save_btn = Gtk.Button(label=_("Save"))
        self._save_btn.add_css_class("suggested-action")
        self._save_btn.set_sensitive(False)
        self._save_btn.connect("clicked", self._on_save_clicked)
        footer.append(self._save_btn)

        toolbar.add_bottom_bar(footer)

        page.set_child(toolbar)
        return page

    # ------------------------------------------------------------------
    # List handling
    # ------------------------------------------------------------------

    def _reload_list(self):
        query = self._search.get_text().strip() if hasattr(self, "_search") else ""
        if query:
            self._snippets = self.db.search_snippets(query)
        else:
            self._snippets = self.db.get_snippets()

        # Drain existing rows.
        while True:
            row = self._listbox.get_row_at_index(0)
            if row is None:
                break
            self._listbox.remove(row)

        for snippet in self._snippets:
            row = self._make_list_row(snippet)
            self._listbox.append(row)
            if snippet["id"] == self._selected_id:
                self._listbox.select_row(row)

        self._count_label.set_text(
            _("{n} snippet").format(n=len(self._snippets))
            if len(self._snippets) == 1
            else _("{n} snippets").format(n=len(self._snippets))
        )

    def _make_list_row(self, snippet):
        row = Adw.ActionRow()
        row.set_title(snippet["name"])
        preview = (snippet.get("content_text") or "").split("\n", 1)[0]
        row.set_subtitle(preview[:80])
        row.snippet_id = snippet["id"]
        return row

    def _on_row_selected(self, _listbox, row):
        if row is None:
            self._load_into_form(None)
            return
        snippet_id = getattr(row, "snippet_id", None)
        if snippet_id is None or snippet_id == self._selected_id:
            return
        snippet = next(
            (s for s in self._snippets if s["id"] == snippet_id), None
        )
        if snippet:
            self._load_into_form(snippet)

    def _load_into_form(self, snippet):
        self._suppress_dirty = True
        try:
            if snippet is None:
                self._selected_id = None
                self._name_row.set_text("")
                self._textview.get_buffer().set_text("")
                self._title_label.set_text(_("No snippet selected"))
                self._meta_label.set_text("")
                self._delete_btn.set_sensitive(False)
            else:
                self._selected_id = snippet["id"]
                self._name_row.set_text(snippet["name"])
                self._textview.get_buffer().set_text(
                    snippet.get("content_text") or ""
                )
                self._title_label.set_text(snippet["name"])
                self._meta_label.set_text(
                    _("ID {sid} · {chars} characters").format(
                        sid=snippet["id"],
                        chars=len(snippet.get("content_text") or ""),
                    )
                )
                self._delete_btn.set_sensitive(True)
        finally:
            self._suppress_dirty = False
        self._set_dirty(False)

    # ------------------------------------------------------------------
    # Dirty state
    # ------------------------------------------------------------------

    def _set_dirty(self, dirty):
        self._dirty = dirty
        self._save_btn.set_sensitive(dirty and bool(self._name_row.get_text().strip()))

    def _on_name_changed(self, _entry):
        if self._suppress_dirty:
            return
        self._set_dirty(True)

    def _on_content_changed(self, _buffer):
        if self._suppress_dirty:
            return
        self._set_dirty(True)

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _on_new_clicked(self, _btn):
        sid = self.db.add_snippet(_("New snippet"), "")
        self._selected_id = sid
        self._reload_list()
        # The new snippet is loaded automatically by _reload_list's
        # row_selected handler when the matching row reappears.

    def _on_save_clicked(self, _btn):
        name = self._name_row.get_text().strip()
        if not name:
            return
        buf = self._textview.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        if self._selected_id is None:
            self._selected_id = self.db.add_snippet(name, text)
        else:
            self.db.update_snippet(self._selected_id, name, text)
        self._set_dirty(False)
        self._reload_list()

    def _on_cancel_clicked(self, _btn):
        # Reload the persisted version of the current snippet, discarding
        # whatever the user typed since the last save.
        if self._selected_id is None:
            self._load_into_form(None)
            return
        fresh = next(
            (s for s in self.db.get_snippets() if s["id"] == self._selected_id),
            None,
        )
        self._load_into_form(fresh)

    def _on_delete_clicked(self, _btn):
        if self._selected_id is None:
            return
        self.db.delete_snippet(self._selected_id)
        self._selected_id = None
        self._load_into_form(None)
        self._reload_list()

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------

    def present(self, parent_window):
        """Show the dialog modally over ``parent_window``."""
        super().present(parent_window)


__all__ = ["SnippetsDialog"]
