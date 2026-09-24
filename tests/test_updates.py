import http.client
import json
import os
import threading
import time
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from clipman import updates

_URL = "https://github.com/MohammedEl-sayedAhmed/clipman/releases/tag/v1.0.5"


class _FakeResponse:
    """Tiny stand-in for the object urlopen returns as a context manager."""

    def __init__(self, payload):
        # Bytes are sent as they are; anything else as JSON.
        if isinstance(payload, (bytes, bytearray)):
            self._body = bytes(payload)
        else:
            self._body = json.dumps(payload).encode("utf-8")
        self._pos = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size=-1):
        end = len(self._body) if size < 0 else self._pos + size
        chunk = self._body[self._pos:end]
        self._pos += len(chunk)
        return chunk


class _SlowResponse(_FakeResponse):
    """A server that sends one byte at a time, each after ``delay``."""

    def __init__(self, payload, delay):
        super().__init__(payload)
        self._delay = delay

    def read(self, size=-1):
        body = bytearray()
        while self._pos < len(self._body) and size != 0:
            time.sleep(self._delay)
            body += self._body[self._pos:self._pos + 1]
            self._pos += 1
            if size > 0:
                break
        return bytes(body)


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

    def test_invalid_tag_against_valid_version_does_not_raise(self):
        # With packaging present, "1.2.3-hotfix" fails to parse while
        # "1.2.1" parses; both sides must then use the simple compare.
        fake_pkg = MagicMock()

        def _parse(s):
            if not s.replace(".", "").isdigit():
                raise ValueError(s)
            return tuple(int(x) for x in s.split("."))

        fake_pkg.parse.side_effect = _parse
        with patch.dict("sys.modules", {"packaging": MagicMock(),
                                        "packaging.version": fake_pkg}):
            self.assertTrue(updates._is_newer("1.2.3-hotfix", "1.2.1"))
            self.assertFalse(updates._is_newer("1.2.1", "1.2.3-hotfix"))
            self.assertTrue(updates._is_newer("1.2.3", "1.2.1"))


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
                                               "html_url": _URL})):
            is_newer, latest, url = updates.check_for_update("1.0.4")
        self.assertTrue(is_newer)
        self.assertEqual(latest, "1.0.5")
        self.assertEqual(url, _URL)

    def test_same_version_not_newer(self):
        with patch("clipman.updates.urllib.request.urlopen",
                   return_value=_FakeResponse({"tag_name": "v1.0.4",
                                               "html_url": _URL})):
            is_newer, latest, _ = updates.check_for_update("1.0.4")
        self.assertFalse(is_newer)
        self.assertEqual(latest, "1.0.4")

    def test_older_version_not_newer(self):
        # Could happen if a release is yanked or pre-release.
        with patch("clipman.updates.urllib.request.urlopen",
                   return_value=_FakeResponse({"tag_name": "v1.0.3",
                                               "html_url": _URL})):
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
                   return_value=_FakeResponse({"html_url": _URL})):
            is_newer, latest, url = updates.check_for_update("1.0.4")
        self.assertFalse(is_newer)
        self.assertIsNone(latest)
        self.assertEqual(url, _URL)

    def test_answer_that_is_not_an_object_swallowed(self):
        """CORE-11: a JSON list raised AttributeError in the thread."""
        for payload in ([1, 2], "v1.0.5", 7, None):
            with self.subTest(payload=payload), \
                 patch("clipman.updates.urllib.request.urlopen",
                       return_value=_FakeResponse(payload)):
                result = updates.check_for_update("1.0.4")
            self.assertEqual(result, (False, None, None))

    def test_tag_that_is_not_a_string_ignored(self):
        with patch("clipman.updates.urllib.request.urlopen",
                   return_value=_FakeResponse({"tag_name": 105,
                                               "html_url": _URL})):
            result = updates.check_for_update("1.0.4")
        self.assertEqual(result, (False, None, _URL))

    def test_url_that_is_not_https_dropped(self):
        for url in ("javascript:alert(1)", "http://example.com/", 7, ""):
            with self.subTest(url=url), \
                 patch("clipman.updates.urllib.request.urlopen",
                       return_value=_FakeResponse({"tag_name": "v1.0.5",
                                                   "html_url": url})):
                result = updates.check_for_update("1.0.4")
            self.assertEqual(result, (True, "1.0.5", None))

    def test_cut_short_answer_swallowed(self):
        """CORE-11: IncompleteRead is not an OSError, so it escaped."""
        response = _FakeResponse(b"{")
        response.read = MagicMock(side_effect=http.client.IncompleteRead(b"{"))
        with patch("clipman.updates.urllib.request.urlopen",
                   return_value=response):
            result = updates.check_for_update("1.0.4")
        self.assertEqual(result, (False, None, None))

    def test_deeply_nested_answer_swallowed(self):
        body = b"[" * 100_000 + b"]" * 100_000
        with patch("clipman.updates.urllib.request.urlopen",
                   return_value=_FakeResponse(body)):
            result = updates.check_for_update("1.0.4")
        self.assertEqual(result, (False, None, None))

    def test_oversized_answer_refused(self):
        payload = {"tag_name": "v1.0.5", "html_url": _URL,
                   "body": "x" * updates.MAX_RESPONSE_BYTES}
        response = _FakeResponse(payload)
        with patch("clipman.updates.urllib.request.urlopen",
                   return_value=response):
            result = updates.check_for_update("1.0.4")
        self.assertEqual(result, (False, None, None))
        # It stopped reading soon after the limit.
        self.assertLess(response._pos, updates.MAX_RESPONSE_BYTES + 32 * 1024)

    def test_slow_answer_stops_at_the_deadline(self):
        """CORE-11: the timeout applied to each read, so a server that
        sent a byte now and then could hold the check for ever."""
        body = b" " * 60 + json.dumps({"tag_name": "v1.0.5"}).encode()
        started = time.monotonic()
        with patch.object(updates, "HTTP_TIMEOUT_SECONDS", 0.2), \
             patch("clipman.updates.urllib.request.urlopen",
                   return_value=_SlowResponse(body, delay=0.05)):
            result = updates.check_for_update("1.0.4")
        self.assertEqual(result, (False, None, None))
        # Sending it all would take about 4 seconds.
        self.assertLess(time.monotonic() - started, 2)

    def test_user_agent_includes_clipman_version(self):
        captured = {}

        def _spy(req, timeout=None):
            captured["ua"] = req.headers.get("User-agent")
            return _FakeResponse({"tag_name": "v1.0.4", "html_url": _URL})

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
                                               "html_url": _URL})):
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
            return _FakeResponse({"tag_name": "v1.0.4", "html_url": _URL})

        with patch("clipman.updates.urllib.request.urlopen",
                   side_effect=_slow_urlopen):
            thread = updates.check_async(db, callback=None)
            thread.join(timeout=5)

        self.assertEqual(len(seen_last), 1)
        # The value at the time of the urlopen call must already be set.
        self.assertNotEqual(seen_last[0], "0")
        self.assertNotEqual(seen_last[0], None)

    def test_result_is_stored_from_the_main_loop_not_the_thread(self):
        db = _fake_db({updates.SETTING_ENABLED: "true"})
        scheduled = []
        fake_glib = MagicMock()
        fake_glib.GLib.idle_add.side_effect = lambda fn, *a: scheduled.append((fn, a))

        with patch.dict("sys.modules", {"gi.repository": fake_glib}), \
             patch("clipman.updates.urllib.request.urlopen",
                   return_value=_FakeResponse({"tag_name": "v9.9.9",
                                               "html_url": _URL})):
            thread = updates.check_async(db, callback=None)
            thread.join(timeout=5)

        # The thread only scheduled the work; nothing was written yet.
        self.assertNotIn(updates.SETTING_LATEST_VERSION, db._store)
        self.assertEqual(len(scheduled), 1)
        fn, args = scheduled[0]
        self.assertFalse(fn(*args))
        self.assertEqual(db._store[updates.SETTING_LATEST_VERSION], "9.9.9")


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
