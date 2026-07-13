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
except (ImportError, ValueError, AttributeError, RuntimeError):
    # ImportError: pygobject / gi missing on the runner.
    # ValueError: gi present but the GTK4 / Adw1 typelibs aren't.
    # AttributeError: a stub ``gi`` shim (some CI sandboxes ship one)
    # lacks ``require_version`` — same outcome: no widgets available.
    # RuntimeError: re-raised by clipman.window's own guard (kept here
    # so the import chain raises a single, predictable class).
    _HAS_GTK = False
    Adw = None  # type: ignore[assignment]

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

    def test_on_edge_action_covers_states_contract(self):
        """Every action_id declared by STATES must have a dispatch handler.

        Previously the renderer wired buttons to action_ids the host
        window didn't know about (9 of 15 ids in STATES were unwired),
        so every Retry / Open / Pick-another button in production fell
        through to ``logger.warning`` and silently no-op'd. This test
        is the contract that catches the next regression: introduce a
        new state in edge_states.STATES without a handler in window.py
        and CI fails here.
        """
        from clipman.edge_states import STATES
        from clipman.window import ClipmanWindow

        declared_ids: set[str] = set()
        for spec in STATES.values():
            for slot in (spec.primary_action, spec.secondary_action):
                if slot is not None:
                    declared_ids.add(slot[1])

        # Class-level frozenset is the source of truth for the
        # dispatcher; the property builds a dict with these keys.
        missing = declared_ids - ClipmanWindow._EDGE_ACTION_IDS
        self.assertFalse(
            missing,
            f"action_ids declared in STATES but not handled by "
            f"ClipmanWindow._on_edge_action: {sorted(missing)}",
        )

    def test_on_edge_action_dispatch_table_matches_declared_ids(self):
        """The runtime dispatch dict keys must equal the class-level set.

        Guards against the property and the frozenset drifting apart:
        if a maintainer adds a handler to the dict without updating the
        set (or vice versa), CI fails before the no-op regression can
        reach production.
        """
        from clipman import database
        from clipman.window import ClipmanWindow

        tmp = tempfile.mkdtemp(prefix="clipman-test-dispatch-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        data_dir = Path(tmp) / "clipman"
        for target, value in (
            ("clipman.database.DATA_DIR", data_dir),
            ("clipman.database.IMAGES_DIR", data_dir / "images"),
            ("clipman.database.DB_PATH", data_dir / "clipman.db"),
        ):
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

        db = database.ClipboardDB()
        self.addCleanup(db.close)
        app = Adw.Application(application_id="com.clipman.TestDispatch")
        window = ClipmanWindow(application=app, db=db, monitor=None)
        self.assertEqual(
            set(window._edge_action_dispatch.keys()),
            set(ClipmanWindow._EDGE_ACTION_IDS),
        )


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

    def test_incognito_toggle_syncs_monitor_and_banner(self):
        """set_incognito drives the monitor, button and privacy banner.

        Regression for two bugs: the incognito-on banner (and its
        "Resume recording" action) was never surfaced by the toggle, and
        set_incognito is the launch-time entry point for the previously
        ignored incognito_on_launch setting.
        """
        from unittest.mock import MagicMock

        from clipman.window import ClipmanWindow

        db = self._make_db()
        app = Adw.Application(application_id="com.clipman.TestIncognito")
        monitor = MagicMock()
        window = ClipmanWindow(application=app, db=db, monitor=monitor)

        window.set_incognito(True)
        self.assertTrue(window._incognito_btn.get_active())
        monitor.set_incognito.assert_called_with(True)
        self.assertIsNotNone(window._current_edge_banner)  # banner shown

        window.set_incognito(False)
        self.assertFalse(window._incognito_btn.get_active())
        monitor.set_incognito.assert_called_with(False)
        self.assertIsNone(window._current_edge_banner)  # banner dismissed

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

    def test_on_edge_action_dispatches_every_states_action_id(self):
        """Runtime contract: every action_id from STATES fires its handler.

        Constructs a ClipmanWindow, monkey-patches the side-effect
        callees (xdg-open, open-prefs, refresh_update_banner,
        snippets dialog) into no-ops, then invokes _on_edge_action
        once per action_id declared in edge_states.STATES. The
        ``logger.warning`` branch is captured via assertLogs — the
        test fails if any id falls through to ``unhandled
        edge-state action_id``.
        """
        from clipman import window as window_module
        from clipman.edge_states import STATES
        from clipman.window import ClipmanWindow

        db = self._make_db()
        app = Adw.Application(application_id="com.clipman.TestDispatch")
        window = ClipmanWindow(application=app, db=db, monitor=None)

        # Side-effect callees we never want to fire during the test:
        #   - _open_url shells out to xdg-open
        #   - _on_prefs_clicked spawns Adw.PreferencesWindow
        #   - _on_snippets_clicked spawns Adw.Dialog
        #   - refresh_update_banner pokes the updates module
        # Replace them with recorders so we can assert the dispatch
        # actually called something rather than the warning fallback.
        called: list[str] = []
        window._open_url = lambda url: called.append(("url", url))
        window._on_prefs_clicked = lambda _b: called.append(("prefs", None))
        window._on_snippets_clicked = lambda _b: called.append(
            ("snippets", None)
        )
        window.refresh_update_banner = lambda: called.append(
            ("update-check", None)
        )

        # Collect every action_id declared in STATES.
        declared_ids: list[str] = []
        for spec in STATES.values():
            for slot in (spec.primary_action, spec.secondary_action):
                if slot is not None:
                    declared_ids.append(slot[1])

        # Drive every id through the dispatcher. assertNoLogs ensures
        # NONE of them hits the ``logger.warning("unhandled ...")``
        # branch. clear-search and close-dialog have inline behaviour
        # (no recorder hit) — they're still tested by virtue of not
        # emitting the warning.
        with self.assertLogs(window_module.logger, level="WARNING") as cm:
            # Append a deliberately-unknown id at the end so assertLogs
            # has SOMETHING to capture (it raises if zero records).
            for action_id in declared_ids:
                window._on_edge_action(action_id)
            window._on_edge_action("definitely-not-an-action")

        # Only the synthetic unknown id should have produced a warning.
        warning_messages = [r.getMessage() for r in cm.records]
        self.assertEqual(len(warning_messages), 1, warning_messages)
        self.assertIn(
            "definitely-not-an-action", warning_messages[0]
        )

    def test_scaled_thumbnail_decodes_at_scale_not_full_res(self):
        """A large stored image yields a bounded-size thumbnail texture.

        Regression for the perf bug where the image-row thumbnail decoded
        the FULL-resolution stored screenshot into a GPU texture on every
        history refresh, then shrank it. The fix decodes-and-scales at
        load, so the resulting texture must be far smaller than the
        1600x1200 source — bounded by the requested oversampled box, not
        the source dimensions.
        """
        from gi.repository import GdkPixbuf

        from clipman.window import ClipmanWindow

        # Build a real 1600x1200 PNG in memory (no alpha needed).
        big = GdkPixbuf.Pixbuf.new(
            GdkPixbuf.Colorspace.RGB, False, 8, 1600, 1200
        )
        big.fill(0x3366FFFF)  # solid blue; RGBA packed
        ok, png_bytes = big.save_to_bufferv("png", [], [])
        self.assertTrue(ok, "failed to encode source PNG")

        db = self._make_db()
        entry_id = db.add_entry("image", image_data=bytes(png_bytes))
        self.assertIsNotNone(entry_id)

        app = Adw.Application(application_id="com.clipman.TestThumb")
        window = ClipmanWindow(application=app, db=db, monitor=None)

        # Grab the stored path the same way _make_entry_row does.
        entry = db.get_entries(limit=1)[0]
        size = 48
        thumb = window._scaled_thumbnail(entry["image_path"], size=size)
        self.assertIsNotNone(thumb, "expected a Gtk.Picture thumbnail")

        paintable = thumb.get_paintable()
        self.assertIsNotNone(paintable)
        iw = paintable.get_intrinsic_width()
        ih = paintable.get_intrinsic_height()

        # The oversampled decode box: size * scale_factor * 2 (COVER
        # headroom). Even at a large HiDPI scale this stays well under
        # the 1600x1200 source — proving we no longer decode full-res.
        scale = max(1, window.get_scale_factor())
        box = size * scale * 2
        self.assertLessEqual(iw, box)
        self.assertLessEqual(ih, box)
        self.assertLess(iw, 1600)
        self.assertLess(ih, 1200)


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
