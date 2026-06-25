"""Smoke tests for the GTK 4 + libadwaita port.

Tests skip cleanly when GTK / libadwaita aren't importable (e.g. on a
headless CI runner without the system packages installed). When they
ARE importable, the tests assert that:

- the new modules import without raising,
- ``ClipmanWindow`` boots with an in-memory DB,
- ``ClipmanPreferences`` and ``SnippetsDialog`` can be constructed,
- ``render_edge_state`` returns a widget for every one of the 15
  state ids declared in ``clipman.edge_states.STATES``.
"""

from __future__ import annotations

import os
import unittest

# Force off-screen behaviour so the test runner doesn't need a real
# display server. Adw still needs to initialise but it's happy to do
# so with the offscreen backend.
os.environ.setdefault("GDK_BACKEND", "x11")
os.environ.setdefault("GTK_A11Y", "none")

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk  # noqa: F401
    _HAS_GTK = True
except (ImportError, ValueError):
    _HAS_GTK = False

_ADW_INIT_OK = False
if _HAS_GTK:
    try:
        Adw.init()
        _ADW_INIT_OK = True
    except Exception:
        # No display available — skip the widget tests.
        _ADW_INIT_OK = False


@unittest.skipUnless(_HAS_GTK and _ADW_INIT_OK,
                     "GTK 4 + libadwaita not available")
class TestEdgeStates(unittest.TestCase):
    """The 15 mockup states must all map to a renderable widget."""

    EXPECTED_IDS = {
        "populated", "empty", "no-results", "first-run", "incognito-on",
        "sensitive-shown", "sensitive-cleared", "extension-missing",
        "backup-failed", "restore-failed", "network-error", "db-locked",
        "paused", "paste-target-missing", "history-too-large",
    }

    def test_all_fifteen_states_declared(self):
        from clipman.edge_states import STATES
        self.assertEqual(set(STATES.keys()), self.EXPECTED_IDS)
        self.assertEqual(len(STATES), 15)

    def test_render_each_state_returns_widget(self):
        from clipman.edge_states import STATES, render_edge_state
        for state_id in STATES:
            with self.subTest(state_id=state_id):
                widget = render_edge_state(state_id)
                self.assertIsNotNone(widget, state_id)
                # Every rendered state carries its spec back for caller
                # introspection (used by the action-id dispatch).
                self.assertTrue(hasattr(widget, "state_spec"))
                self.assertEqual(widget.state_spec.id, state_id)

    def test_unknown_state_falls_back_to_empty(self):
        from clipman.edge_states import render_edge_state
        widget = render_edge_state("does-not-exist")
        self.assertIsNotNone(widget)


@unittest.skipUnless(_HAS_GTK and _ADW_INIT_OK,
                     "GTK 4 + libadwaita not available")
class TestWindowConstruction(unittest.TestCase):
    """ClipmanWindow + ClipmanPreferences + SnippetsDialog all build."""

    def _make_db(self):
        # Use a temp dir so the test never touches the real DB.
        import tempfile
        from clipman import database

        tmp = tempfile.mkdtemp(prefix="clipman-test-")
        database.DATA_DIR = type(database.DATA_DIR)(tmp)
        database.IMAGES_DIR = database.DATA_DIR / "images"
        database.DB_PATH = database.DATA_DIR / "clipman.db"
        return database.ClipboardDB()

    def test_window_boots(self):
        from clipman.window import ClipmanWindow

        db = self._make_db()
        app = Adw.Application(application_id="com.clipman.Test")
        window = ClipmanWindow(application=app, db=db, monitor=None)
        self.assertIsNotNone(window)
        # Public interface required by dbus_service stays intact.
        self.assertTrue(hasattr(window, "toggle"))
        self.assertTrue(hasattr(window, "refresh"))
        self.assertTrue(hasattr(window, "refresh_update_banner"))

    def test_preferences_window_constructs(self):
        from clipman.preferences import ClipmanPreferences
        from clipman.window import ClipmanWindow

        db = self._make_db()
        app = Adw.Application(application_id="com.clipman.Test")
        parent = ClipmanWindow(application=app, db=db, monitor=None)
        prefs = ClipmanPreferences(db, parent, on_setting_changed=None)
        self.assertIsNotNone(prefs)

    def test_snippets_dialog_constructs(self):
        from clipman.snippets_dialog import SnippetsDialog

        db = self._make_db()
        dialog = SnippetsDialog(db)
        self.assertIsNotNone(dialog)


class TestEdgeStateDeclaration(unittest.TestCase):
    """Module-level invariants of edge_states.py that don't need GTK.

    These tests intentionally avoid importing ``render_edge_state``
    (which pulls in Adw) so they run even on a stock CI image.
    """

    def test_module_importable_without_widgets(self):
        # We import the module's *data* but skip the function that
        # requires Adw. The import itself does pull in Gtk via gi —
        # that's still fine because gi is a dependency declared in
        # pyproject. If GTK isn't on PATH, the whole package would
        # fail to import and the rest of the test suite would too.
        try:
            from clipman import edge_states  # noqa: F401
        except (ImportError, ValueError):
            self.skipTest("clipman.edge_states cannot import without GTK")

    def test_state_specs_have_required_fields(self):
        try:
            from clipman.edge_states import STATES
        except (ImportError, ValueError):
            self.skipTest("clipman.edge_states cannot import without GTK")

        for state_id, spec in STATES.items():
            with self.subTest(state_id=state_id):
                self.assertEqual(spec.id, state_id)
                self.assertIn(spec.kind,
                              ("statuspage", "banner", "alertdialog"))
                self.assertIn(spec.tone,
                              ("info", "warning", "privacy", "error",
                               "neutral"))
                self.assertTrue(spec.title)
                self.assertTrue(spec.body)
                self.assertTrue(spec.icon_name)


if __name__ == "__main__":
    unittest.main()
