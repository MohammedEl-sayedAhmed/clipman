"""Smoke tests for the GTK 4 + libadwaita port.

Tests skip cleanly when GTK / libadwaita aren't importable (e.g. on a
headless CI runner without the system packages installed). When they
ARE importable, the tests assert that:

- the new modules import without raising,
- ``ClipmanWindow`` boots with an in-memory DB,
- ``ClipmanPreferences`` and ``SnippetsDialog`` can be constructed,
- ``render_edge_state`` returns a widget for every one of the 16
  state ids declared in ``clipman.edge_states.STATES``.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Force off-screen behaviour so the test runner doesn't need a real
# display server. Adw still needs to initialise but it's happy to do
# so with the offscreen backend.
os.environ.setdefault("GDK_BACKEND", "x11")
os.environ.setdefault("GTK_A11Y", "none")

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw  # noqa: F401
    _HAS_GTK = True
except (ImportError, ValueError, AttributeError):
    # ImportError: pygobject / gi missing on the runner.
    # ValueError: gi present but the GTK4 / Adw1 typelibs aren't.
    # AttributeError: a stub ``gi`` shim (some CI sandboxes ship one)
    # lacks ``require_version`` — same outcome: no widgets available.
    _HAS_GTK = False

_ADW_INIT_OK = False
if _HAS_GTK:
    try:
        Adw.init()
        _ADW_INIT_OK = True
    except Exception:
        # No display available — skip the widget tests.
        _ADW_INIT_OK = False

# CI sets ``CLIPMAN_REQUIRE_GTK4=1`` so an apt-package rename or a
# missing typelib turns into a HARD failure instead of a silent skip.
# Locally the variable stays unset, so contributors without GTK4
# installed still get the rest of the test suite passing.
if os.environ.get("CLIPMAN_REQUIRE_GTK4") == "1" and not (_HAS_GTK and _ADW_INIT_OK):
    raise RuntimeError(
        "CLIPMAN_REQUIRE_GTK4=1 but GTK 4 + libadwaita are not "
        "importable in this environment. Install gir1.2-gtk-4.0, "
        "gir1.2-adw-1 and libadwaita-1-0 (and run under xvfb-run if "
        "no display is available)."
    )


@unittest.skipUnless(_HAS_GTK and _ADW_INIT_OK,
                     "GTK 4 + libadwaita not available")
class TestEdgeStates(unittest.TestCase):
    """The 16 mockup states must all map to a renderable widget."""

    EXPECTED_IDS = {
        "populated", "empty", "no-snippets-yet", "no-results", "first-run",
        "incognito-on", "sensitive-shown", "sensitive-cleared",
        "extension-missing", "backup-failed", "restore-failed",
        "network-error", "db-locked", "paused", "paste-target-missing",
        "history-too-large",
    }

    def test_state_id_inventory(self):
        """Lock the inventory — adding a state requires updating this set.

        Renamed from ``test_all_states_declared`` to make the intent
        (inventory lock-in, not a smoke test) explicit. Touching this
        list should be a deliberate, reviewer-visible action.
        """
        from clipman.edge_states import STATES
        self.assertEqual(set(STATES.keys()), self.EXPECTED_IDS)
        self.assertEqual(len(STATES), 16)

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
                # ``kind`` -> widget class invariant. The renderer
                # dispatches on ``spec.kind`` and the host window relies
                # on the resulting type to decide where to mount it.
                spec = widget.state_spec
                if spec.kind == "banner":
                    self.assertIsInstance(widget, Adw.Banner)
                elif spec.kind == "alertdialog":
                    self.assertIsInstance(widget, Adw.AlertDialog)
                else:
                    self.assertEqual(spec.kind, "statuspage")
                    self.assertIsInstance(widget, Adw.StatusPage)

    def test_unknown_state_falls_back_to_empty(self):
        from clipman.edge_states import render_edge_state
        widget = render_edge_state("does-not-exist")
        self.assertIsNotNone(widget)
        # The fallback must be the ``empty`` spec specifically — the
        # popup relies on this so a typo in window.py doesn't leak a
        # random spec into the empty slot.
        self.assertEqual(widget.state_spec.id, "empty")


@unittest.skipUnless(_HAS_GTK and _ADW_INIT_OK,
                     "GTK 4 + libadwaita not available")
class TestWindowConstruction(unittest.TestCase):
    """ClipmanWindow + ClipmanPreferences + SnippetsDialog all build."""

    def _make_db(self):
        # Use a temp dir so the test never touches the real DB.
        # Mirrors the pattern in test_database.py: patch the module-level
        # paths (do NOT mutate them — that leaks across tests) and register
        # an addCleanup for each patch + the tmpdir.
        from clipman import database

        tmp = tempfile.mkdtemp(prefix="clipman-test-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        data_dir = Path(tmp) / "clipman"
        images_dir = data_dir / "images"
        db_path = data_dir / "clipman.db"
        for target, value in (
            ("clipman.database.DATA_DIR", data_dir),
            ("clipman.database.IMAGES_DIR", images_dir),
            ("clipman.database.DB_PATH", db_path),
        ):
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)
        db = database.ClipboardDB()
        self.addCleanup(db.close)
        return db

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

    def test_refresh_with_seeded_entries(self):
        """Three seeded entries -> three ActionRows with their titles."""
        from clipman.window import ClipmanWindow

        db = self._make_db()
        # Seed in reverse chronological order — get_entries returns most
        # recent first, so we insert "old" then "mid" then "new" and
        # expect the listbox to show them in (new, mid, old) order.
        for text in ("old entry", "mid entry", "new entry"):
            db.add_entry("text", content_text=text)

        app = Adw.Application(application_id="com.clipman.Test")
        window = ClipmanWindow(application=app, db=db, monitor=None)
        window.refresh()

        # The listbox should now contain three Adw.ActionRow widgets.
        rows = []
        i = 0
        while True:
            row = window.listbox.get_row_at_index(i)
            if row is None:
                break
            rows.append(row)
            i += 1
        self.assertEqual(len(rows), 3)

        titles = [r.get_title() for r in rows]
        # Order: get_entries returns most-recent first.
        self.assertEqual(titles[0], "new entry")
        self.assertEqual(titles[1], "mid entry")
        self.assertEqual(titles[2], "old entry")

    def test_on_setting_changed_fan_out(self):
        """ClipmanPreferences._save fans out (key, value) to the callback."""
        from clipman.preferences import ClipmanPreferences
        from clipman.window import ClipmanWindow

        db = self._make_db()
        app = Adw.Application(application_id="com.clipman.Test")
        parent = ClipmanWindow(application=app, db=db, monitor=None)

        received: list[tuple[str, object]] = []

        def recorder(key, value):
            received.append((key, value))

        prefs = ClipmanPreferences(db, parent, on_setting_changed=recorder)
        # Simulate the SpinRow notify -> _save path the font-size row
        # uses (preferences.py wires `lambda r: self._save("font_size",
        # int(r.get_value()))`).
        prefs._save("font_size", 14)

        self.assertIn(("font_size", 14), received)
        # And the value persisted to the DB as a stringified int.
        self.assertEqual(db.get_setting("font_size"), "14")

    def test_refresh_update_banner_revealed(self):
        """should_show_banner -> (True, version) reveals the banner."""
        from clipman import updates
        from clipman.window import ClipmanWindow

        db = self._make_db()
        app = Adw.Application(application_id="com.clipman.Test")
        window = ClipmanWindow(application=app, db=db, monitor=None)

        # The banner is built revealed=False at construction time. Patch
        # should_show_banner so the next refresh_update_banner call
        # flips the revealed flag and writes a title containing the
        # advertised version.
        with patch.object(updates, "should_show_banner",
                          return_value=(True, "1.0.7")):
            window.refresh_update_banner()

        self.assertTrue(window._update_banner.get_revealed())
        self.assertIn("1.0.7", window._update_banner.get_title())


class TestEdgeStateDeclaration(unittest.TestCase):
    """Module-level invariants of edge_states.py that don't need GTK.

    These tests intentionally avoid importing ``render_edge_state``
    (which pulls in Adw) so they run even on a stock CI image.
    """

    def test_module_importable_without_widgets(self):
        # ``edge_states`` lazy-imports GTK inside ``render_edge_state``
        # so the module itself must import on a stock CI runner with
        # no system GTK installed. If this raises we've regressed the
        # import-policy invariant — fail loudly instead of skipping.
        from clipman import edge_states

        # The lazy-import invariant: the inventory dict exists at
        # module scope, but Adw must NOT have been pulled into the
        # module namespace by the import — that would defeat the
        # whole point of the lazy import inside render_edge_state.
        self.assertTrue(hasattr(edge_states, "STATES"))
        self.assertFalse(
            hasattr(edge_states, "Adw"),
            "edge_states must not eagerly import Adw at module scope",
        )

    def test_state_specs_have_required_fields(self):
        from clipman.edge_states import STATES

        # Sanity: the dict is the one the renderer dispatches on.
        self.assertTrue(STATES, "edge_states.STATES must not be empty")
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
                # Adwaita StatusPage / Banner artwork is the symbolic
                # variant — anything else looks chunky and out of place
                # next to the rest of GNOME's UI.
                self.assertTrue(
                    spec.icon_name.endswith("-symbolic"),
                    f"{state_id} icon {spec.icon_name!r} must be symbolic",
                )
                # Action specs (when present) are ``(label, action_id)``
                # tuples — the renderer indexes both fields and the host
                # window dispatches on ``action_id``.
                for slot in ("primary_action", "secondary_action"):
                    action = getattr(spec, slot)
                    if action is None:
                        continue
                    self.assertIsInstance(action, tuple)
                    self.assertEqual(len(action), 2)
                    label, action_id = action
                    self.assertTrue(label)
                    self.assertTrue(action_id)
                    self.assertIsInstance(action_id, str)


if __name__ == "__main__":
    unittest.main()
