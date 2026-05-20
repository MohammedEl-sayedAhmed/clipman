import json
import os
import threading
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from clipman import updates


class _FakeResponse:
    """Tiny stand-in for the object urlopen returns as a context manager."""

    def __init__(self, payload: dict | bytes):
        if isinstance(payload, (bytes, bytearray)):
            self._body = bytes(payload)
        else:
            self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _fake_db(initial: dict | None = None):
    """Lightweight in-memory stand-in for ClipboardDB's settings API."""
    store = dict(initial or {})

    db = MagicMock()
    db.get_setting.side_effect = lambda key, default=None: store.get(key, default)

    def _set(key, value):
        store[key] = str(value)

    db.set_setting.side_effect = _set
    db._store = store
    return db


class TestIsNewer(unittest.TestCase):
    def test_strictly_newer(self):
        self.assertTrue(updates._is_newer("1.0.5", "1.0.4"))

    def test_equal_is_not_newer(self):
        self.assertFalse(updates._is_newer("1.0.4", "1.0.4"))

    def test_older_is_not_newer(self):
        self.assertFalse(updates._is_newer("1.0.3", "1.0.4"))

    def test_minor_bump(self):
        self.assertTrue(updates._is_newer("1.1.0", "1.0.99"))

    def test_strips_v_prefix(self):
        self.assertTrue(updates._is_newer("v1.0.5", "1.0.4"))
        self.assertTrue(updates._is_newer("1.0.5", "v1.0.4"))


class TestInstallKind(unittest.TestCase):
    def test_snap_detected(self):
        with patch.dict(os.environ, {"SNAP": "/snap/clipman/current"}, clear=False):
            self.assertEqual(updates.install_kind(), "snap")

    def test_flatpak_detected(self):
        env = {k: v for k, v in os.environ.items() if k != "SNAP"}
        env["FLATPAK_ID"] = "io.github.MohammedEl_sayedAhmed.Clipman"
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(updates.install_kind(), "flatpak")

    def test_other_detected(self):
        env = {
            k: v for k, v in os.environ.items()
            if k not in ("SNAP", "FLATPAK_ID")
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(updates.install_kind(), "other")

    def test_default_enabled_other(self):
        with patch("clipman.updates.install_kind", return_value="other"):
            self.assertTrue(updates.default_enabled())

    def test_default_disabled_snap(self):
        with patch("clipman.updates.install_kind", return_value="snap"):
            self.assertFalse(updates.default_enabled())

    def test_default_disabled_flatpak(self):
        with patch("clipman.updates.install_kind", return_value="flatpak"):
            self.assertFalse(updates.default_enabled())


class TestCheckForUpdate(unittest.TestCase):
    def test_newer_detected(self):
        with patch("clipman.updates.urllib.request.urlopen",
                   return_value=_FakeResponse({"tag_name": "v1.0.5",
                                               "html_url": "u"})):
            is_newer, latest, url = updates.check_for_update("1.0.4")
        self.assertTrue(is_newer)
        self.assertEqual(latest, "1.0.5")
        self.assertEqual(url, "u")

    def test_same_version_not_newer(self):
        with patch("clipman.updates.urllib.request.urlopen",
                   return_value=_FakeResponse({"tag_name": "v1.0.4",
                                               "html_url": "u"})):
            is_newer, latest, _ = updates.check_for_update("1.0.4")
        self.assertFalse(is_newer)
        self.assertEqual(latest, "1.0.4")

    def test_older_version_not_newer(self):
        # Could happen if a release is yanked or pre-release.
        with patch("clipman.updates.urllib.request.urlopen",
                   return_value=_FakeResponse({"tag_name": "v1.0.3",
                                               "html_url": "u"})):
            is_newer, latest, _ = updates.check_for_update("1.0.4")
        self.assertFalse(is_newer)
        self.assertEqual(latest, "1.0.3")

    def test_network_error_swallowed(self):
        with patch("clipman.updates.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("offline")):
            result = updates.check_for_update("1.0.4")
        self.assertEqual(result, (False, None, None))

    def test_timeout_swallowed(self):
        with patch("clipman.updates.urllib.request.urlopen",
                   side_effect=TimeoutError("slow")):
            result = updates.check_for_update("1.0.4")
        self.assertEqual(result, (False, None, None))

    def test_bad_json_swallowed(self):
        with patch("clipman.updates.urllib.request.urlopen",
                   return_value=_FakeResponse(b"not-json")):
            result = updates.check_for_update("1.0.4")
        self.assertEqual(result, (False, None, None))

    def test_missing_tag_field(self):
        with patch("clipman.updates.urllib.request.urlopen",
                   return_value=_FakeResponse({"html_url": "u"})):
            is_newer, latest, url = updates.check_for_update("1.0.4")
        self.assertFalse(is_newer)
        self.assertIsNone(latest)
        self.assertEqual(url, "u")

    def test_user_agent_includes_clipman_version(self):
        captured = {}

        def _spy(req, timeout=None):
            captured["ua"] = req.headers.get("User-agent")
            return _FakeResponse({"tag_name": "v1.0.4", "html_url": "u"})

        with patch("clipman.updates.urllib.request.urlopen", side_effect=_spy):
            updates.check_for_update("1.0.4")
        self.assertTrue(captured["ua"].startswith("clipman/"))


class TestShouldCheckNow(unittest.TestCase):
    def test_skipped_when_disabled(self):
        db = _fake_db({updates.SETTING_ENABLED: "false"})
        self.assertFalse(updates.should_check_now(db, now=1_000_000.0))

    def test_first_run_when_enabled(self):
        db = _fake_db({updates.SETTING_ENABLED: "true"})
        # last-check is unset → "0" → vast delta → True.
        self.assertTrue(updates.should_check_now(db, now=1_000_000.0))

    def test_rate_limited_within_24h(self):
        db = _fake_db({
            updates.SETTING_ENABLED: "true",
            updates.SETTING_LAST_CHECK: str(1_000_000.0),
        })
        self.assertFalse(updates.should_check_now(db, now=1_000_000.0 + 60))

    def test_allowed_after_24h(self):
        db = _fake_db({
            updates.SETTING_ENABLED: "true",
            updates.SETTING_LAST_CHECK: str(1_000_000.0),
        })
        later = 1_000_000.0 + updates.CHECK_INTERVAL_SECONDS + 1
        self.assertTrue(updates.should_check_now(db, now=later))


class TestEnabledAndDefault(unittest.TestCase):
    def test_default_when_empty(self):
        db = _fake_db({})
        with patch("clipman.updates.install_kind", return_value="other"):
            self.assertTrue(updates._enabled(db))
        with patch("clipman.updates.install_kind", return_value="snap"):
            self.assertFalse(updates._enabled(db))

    def test_explicit_true_overrides_default(self):
        db = _fake_db({updates.SETTING_ENABLED: "true"})
        with patch("clipman.updates.install_kind", return_value="snap"):
            self.assertTrue(updates._enabled(db))

    def test_explicit_false_overrides_default(self):
        db = _fake_db({updates.SETTING_ENABLED: "false"})
        with patch("clipman.updates.install_kind", return_value="other"):
            self.assertFalse(updates._enabled(db))

    def test_set_enabled_persists(self):
        db = _fake_db({})
        updates.set_enabled(db, True)
        self.assertEqual(db._store[updates.SETTING_ENABLED], "true")
        updates.set_enabled(db, False)
        self.assertEqual(db._store[updates.SETTING_ENABLED], "false")


class TestShouldShowBanner(unittest.TestCase):
    def test_hidden_when_disabled(self):
        db = _fake_db({
            updates.SETTING_ENABLED: "false",
            updates.SETTING_LATEST_VERSION: "1.0.5",
        })
        show, _ = updates.should_show_banner(db, current_version="1.0.4")
        self.assertFalse(show)

    def test_hidden_when_no_latest_cached(self):
        db = _fake_db({updates.SETTING_ENABLED: "true"})
        show, latest = updates.should_show_banner(db, current_version="1.0.4")
        self.assertFalse(show)
        self.assertIsNone(latest)

    def test_hidden_when_up_to_date(self):
        db = _fake_db({
            updates.SETTING_ENABLED: "true",
            updates.SETTING_LATEST_VERSION: "1.0.4",
        })
        show, _ = updates.should_show_banner(db, current_version="1.0.4")
        self.assertFalse(show)

    def test_shown_when_newer_and_not_dismissed(self):
        db = _fake_db({
            updates.SETTING_ENABLED: "true",
            updates.SETTING_LATEST_VERSION: "1.0.5",
        })
        show, latest = updates.should_show_banner(db, current_version="1.0.4")
        self.assertTrue(show)
        self.assertEqual(latest, "1.0.5")

    def test_hidden_when_user_dismissed_same_version(self):
        db = _fake_db({
            updates.SETTING_ENABLED: "true",
            updates.SETTING_LATEST_VERSION: "1.0.5",
            updates.SETTING_DISMISSED_VERSION: "1.0.5",
        })
        show, _ = updates.should_show_banner(db, current_version="1.0.4")
        self.assertFalse(show)

    def test_shown_when_older_dismissal_does_not_carry_over(self):
        # User dismissed 1.0.5; now 1.0.6 is the latest → banner returns.
        db = _fake_db({
            updates.SETTING_ENABLED: "true",
            updates.SETTING_LATEST_VERSION: "1.0.6",
            updates.SETTING_DISMISSED_VERSION: "1.0.5",
        })
        show, latest = updates.should_show_banner(db, current_version="1.0.4")
        self.assertTrue(show)
        self.assertEqual(latest, "1.0.6")


class TestCheckAsync(unittest.TestCase):
    def test_thread_writes_latest_and_invokes_callback(self):
        db = _fake_db({updates.SETTING_ENABLED: "true"})
        seen = {}
        cb_event = threading.Event()

        def _cb(is_newer, latest, url):
            seen["args"] = (is_newer, latest, url)
            cb_event.set()

        # Force the gi import inside check_async to fail so the
        # callback is invoked inline (no GTK main loop runs in tests).
        with patch.dict("sys.modules", {"gi.repository": None}), \
             patch("clipman.updates.urllib.request.urlopen",
                   return_value=_FakeResponse({"tag_name": "v1.0.5",
                                               "html_url": "u"})):
            thread = updates.check_async(db, callback=_cb)
            thread.join(timeout=5)
            cb_event.wait(timeout=2)

        self.assertEqual(db._store[updates.SETTING_LATEST_VERSION], "1.0.5")
        self.assertEqual(seen["args"][1], "1.0.5")

    def test_last_check_recorded_before_io(self):
        db = _fake_db({updates.SETTING_ENABLED: "true"})
        # Use an event so we can confirm last_update_check is set
        # *before* the network call returns.
        seen_last = []

        def _slow_urlopen(*_a, **_kw):
            seen_last.append(db._store.get(updates.SETTING_LAST_CHECK))
            return _FakeResponse({"tag_name": "v1.0.4", "html_url": "u"})

        with patch("clipman.updates.urllib.request.urlopen",
                   side_effect=_slow_urlopen):
            thread = updates.check_async(db, callback=None)
            thread.join(timeout=5)

        self.assertEqual(len(seen_last), 1)
        # The value at the time of the urlopen call must already be set.
        self.assertNotEqual(seen_last[0], "0")
        self.assertNotEqual(seen_last[0], None)


class TestDismissAndLatestKnown(unittest.TestCase):
    def test_dismiss_writes_setting(self):
        db = _fake_db({})
        updates.dismiss(db, "1.0.5")
        self.assertEqual(db._store[updates.SETTING_DISMISSED_VERSION], "1.0.5")

    def test_latest_known_none_when_unset(self):
        self.assertIsNone(updates.latest_known(_fake_db({})))

    def test_latest_known_round_trip(self):
        db = _fake_db({updates.SETTING_LATEST_VERSION: "1.0.5"})
        self.assertEqual(updates.latest_known(db), "1.0.5")


if __name__ == "__main__":
    unittest.main()
