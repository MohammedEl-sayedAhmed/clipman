import time
import unittest
from unittest.mock import patch, MagicMock


class FakeCompletedProcess:
    """Mimics subprocess.CompletedProcess."""
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestClipboardMonitor(unittest.TestCase):
    """Tests for the event-driven ClipboardMonitor."""

    def setUp(self):
        self.mock_db = MagicMock()
        self.new_entry_called = False

        def on_new_entry():
            self.new_entry_called = True

        from clipman.clipboard_monitor import ClipboardMonitor
        self.monitor = ClipboardMonitor(self.mock_db, on_new_entry=on_new_entry)

    def test_detects_new_text(self):
        self.monitor.handle_new_text("hello clipboard")

        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="hello clipboard", sensitive=False
        )

    def test_allows_duplicate_text(self):
        self.monitor.handle_new_text("same text")
        self.monitor._last_event_time = 0  # reset rate limiter
        self.monitor.handle_new_text("same text")

        self.assertEqual(self.mock_db.add_entry.call_count, 2)

    def test_detects_changed_text(self):
        self.monitor.handle_new_text("first text")
        self.monitor._last_event_time = 0  # reset rate limiter
        self.monitor.handle_new_text("second text")

        self.assertEqual(self.mock_db.add_entry.call_count, 2)

    def test_skips_oversized_text(self):
        big_text = "x" * (10 * 1024 * 1024 + 1)
        self.monitor.handle_new_text(big_text)

        self.mock_db.add_entry.assert_not_called()

    def test_skips_empty_text(self):
        self.monitor.handle_new_text("")
        self.monitor.handle_new_text(None)

        self.mock_db.add_entry.assert_not_called()

    def test_self_copy_skips_text(self):
        self.monitor.set_self_copy(True)
        self.monitor.handle_new_text("should be skipped")

        self.mock_db.add_entry.assert_not_called()
        self.assertFalse(self.monitor._self_copy)  # Reset after skip

    def test_self_copy_skips_image(self):
        self.monitor.set_self_copy(True)
        self.monitor.handle_new_image()

        self.mock_db.add_entry.assert_not_called()
        self.assertFalse(self.monitor._self_copy)

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_detects_new_image(self, mock_run):
        image_data = b"\x89PNG\r\n\x1a\nfake_image"
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=image_data
        )

        self.monitor.handle_new_image()

        self.mock_db.add_entry.assert_called_once_with(
            "image", image_data=image_data
        )

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_allows_duplicate_image(self, mock_run):
        image_data = b"\x89PNG\r\n\x1a\nfake_image"
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=image_data
        )

        self.monitor.handle_new_image()
        self.monitor._last_event_time = 0  # reset rate limiter
        self.monitor.handle_new_image()

        self.assertEqual(self.mock_db.add_entry.call_count, 2)

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_skips_oversized_image(self, mock_run):
        big_image = b"\x89" * (10 * 1024 * 1024 + 1)
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=big_image
        )

        self.monitor.handle_new_image()

        self.mock_db.add_entry.assert_not_called()

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_handles_wl_paste_error(self, mock_run):
        mock_run.return_value = FakeCompletedProcess(returncode=1, stdout=b"")

        self.monitor.handle_new_image()

        self.mock_db.add_entry.assert_not_called()

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_handles_wl_paste_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="wl-paste", timeout=5)

        # Should not raise
        self.monitor.handle_new_image()
        self.mock_db.add_entry.assert_not_called()

    def test_callback_fires_on_new_text(self):
        self.monitor.handle_new_text("trigger callback")
        self.assertTrue(self.new_entry_called)

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_callback_fires_on_new_image(self, mock_run):
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=b"\x89PNGdata"
        )
        self.monitor.handle_new_image()
        self.assertTrue(self.new_entry_called)

    def test_start_stop_are_noops(self):
        # Should not raise
        self.monitor.start()
        self.monitor.stop()

    # ── Incognito mode ─────────────────────────────────────────────

    def test_incognito_skips_text(self):
        self.monitor.set_incognito(True)
        self.monitor.handle_new_text("secret text")

        self.mock_db.add_entry.assert_not_called()
        self.assertFalse(self.new_entry_called)

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_incognito_skips_image(self, mock_run):
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=b"\x89PNGdata"
        )
        self.monitor.set_incognito(True)
        self.monitor.handle_new_image()

        self.mock_db.add_entry.assert_not_called()

    def test_incognito_toggle(self):
        self.monitor.set_incognito(True)
        self.assertTrue(self.monitor._incognito)
        self.monitor.set_incognito(False)
        self.assertFalse(self.monitor._incognito)

    # ── Sensitive detection ────────────────────────────────────────

    def test_sensitive_token_prefix(self):
        self.monitor.handle_new_text("ghp_ABC123xyzTOKEN")

        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="ghp_ABC123xyzTOKEN", sensitive=True
        )

    def test_sensitive_password_pattern(self):
        # Mixed case, digits, punctuation, >= 8 chars, no spaces
        self.monitor.handle_new_text("MyP@ssw0rd!")

        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="MyP@ssw0rd!", sensitive=True
        )

    def test_sensitive_sk_prefix(self):
        self.monitor.handle_new_text("sk-proj-abcdef123456")

        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="sk-proj-abcdef123456", sensitive=True
        )

    def test_normal_text_not_sensitive(self):
        self.monitor.handle_new_text("hello clipboard")

        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="hello clipboard", sensitive=False
        )

    def test_multiline_not_sensitive(self):
        self.monitor.handle_new_text("line1\nline2")

        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="line1\nline2", sensitive=False
        )

    def test_short_text_not_sensitive(self):
        self.monitor.handle_new_text("Ab1!")

        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="Ab1!", sensitive=False
        )

    # ── Extended sensitive detection ──────────────────────────────

    def test_sensitive_bearer_token(self):
        self.monitor.handle_new_text("Bearer eyJhbGciOiJIUzI1NiJ9.token")
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="Bearer eyJhbGciOiJIUzI1NiJ9.token", sensitive=True
        )

    def test_sensitive_jwt_token(self):
        self.monitor.handle_new_text("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
        self.mock_db.add_entry.assert_called_once_with(
            "text",
            content_text="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            sensitive=True
        )

    def test_sensitive_slack_token(self):
        self.monitor.handle_new_text("xoxb-123456789012-abcdef")
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="xoxb-123456789012-abcdef", sensitive=True
        )

    def test_sensitive_aws_key(self):
        self.monitor.handle_new_text("AKIAIOSFODNN7EXAMPLE")
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="AKIAIOSFODNN7EXAMPLE", sensitive=True
        )

    def test_sensitive_google_api_key(self):
        self.monitor.handle_new_text("AIzaSyB-1234567890abcdef")
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="AIzaSyB-1234567890abcdef", sensitive=True
        )

    def test_sensitive_github_pat(self):
        self.monitor.handle_new_text("github_pat_11ABCDEF0_xxxxxxxxxxxx")
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="github_pat_11ABCDEF0_xxxxxxxxxxxx", sensitive=True
        )

    def test_sensitive_stripe_live_key(self):
        self.monitor.handle_new_text("sk_live_51H3ABC1234567890abcdef")
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="sk_live_51H3ABC1234567890abcdef", sensitive=True
        )

    def test_sensitive_pk_live_key(self):
        self.monitor.handle_new_text("pk_live_51H3ABC1234567890abcdef")
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="pk_live_51H3ABC1234567890abcdef", sensitive=True
        )

    def test_not_sensitive_text_with_spaces(self):
        # Even with mixed chars, spaces disqualify it
        self.monitor.handle_new_text("My Pass 123!")
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="My Pass 123!", sensitive=False
        )

    def test_not_sensitive_too_long(self):
        # Over 128 chars — not sensitive
        self.monitor.handle_new_text("A" * 130)
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="A" * 130, sensitive=False
        )

    def test_not_sensitive_only_lowercase(self):
        # Only one char category
        self.monitor.handle_new_text("abcdefghij")
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="abcdefghij", sensitive=False
        )

    def test_not_sensitive_only_two_categories(self):
        # Only lower + digits = 2 categories, need >= 3
        self.monitor.handle_new_text("abc12345")
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="abc12345", sensitive=False
        )

    def test_sensitive_three_categories(self):
        # lower + upper + digit = 3 categories, >= 8 chars
        self.monitor.handle_new_text("Abc12345")
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="Abc12345", sensitive=True
        )

    def test_not_sensitive_exactly_seven_chars(self):
        # 3 categories but only 7 chars — under the 8-char minimum
        self.monitor.handle_new_text("Abc123!")
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="Abc123!", sensitive=False
        )

    def test_sensitive_exactly_eight_chars(self):
        # 3 categories, exactly 8 chars
        self.monitor.handle_new_text("Abc1234!")
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="Abc1234!", sensitive=True
        )

    def test_not_sensitive_multiline_with_password(self):
        # Even password-like content is ignored if multiline
        self.monitor.handle_new_text("MyP@ssw0rd!\nExtra line")
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="MyP@ssw0rd!\nExtra line", sensitive=False
        )

    def test_sensitive_boundary_128_chars(self):
        # Exactly 128 chars with 3+ categories — should be sensitive
        text = "A" + "a" * 125 + "1!"  # upper + lower + digit + punct = 4 cats
        self.assertEqual(len(text), 128)
        self.monitor.handle_new_text(text)
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text=text, sensitive=True
        )

    # ── Rate limiting ─────────────────────────────────────────────

    def test_rate_limited_drops_fast_events(self):
        self.monitor.handle_new_text("first")
        # Don't reset rate limiter — second call should be dropped
        self.monitor.handle_new_text("second")

        self.assertEqual(self.mock_db.add_entry.call_count, 1)
        self.mock_db.add_entry.assert_called_with(
            "text", content_text="first", sensitive=False
        )

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_rate_limited_drops_fast_image_events(self, mock_run):
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=b"\x89PNGdata"
        )
        self.monitor.handle_new_image()
        # Don't reset — second call should be dropped
        self.monitor.handle_new_image()

        self.assertEqual(self.mock_db.add_entry.call_count, 1)

    def test_rate_limiter_allows_after_interval(self):
        self.monitor.handle_new_text("first")
        self.assertEqual(self.mock_db.add_entry.call_count, 1)

        # Simulate time passing beyond MIN_EVENT_INTERVAL
        self.monitor._last_event_time = time.monotonic() - 0.2
        self.monitor.handle_new_text("second")
        self.assertEqual(self.mock_db.add_entry.call_count, 2)

    # ── Edge cases ────────────────────────────────────────────────

    def test_self_copy_auto_resets_after_text(self):
        self.monitor.set_self_copy(True)
        self.monitor.handle_new_text("skipped")
        # self_copy should auto-reset
        self.assertFalse(self.monitor._self_copy)
        # Now next text should be recorded
        self.monitor.handle_new_text("recorded")
        self.assertEqual(self.mock_db.add_entry.call_count, 1)
        self.mock_db.add_entry.assert_called_with(
            "text", content_text="recorded", sensitive=False
        )

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_self_copy_auto_resets_after_image(self, mock_run):
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=b"\x89PNGdata"
        )
        self.monitor.set_self_copy(True)
        self.monitor.handle_new_image()
        self.assertFalse(self.monitor._self_copy)
        # Next image should be recorded
        self.monitor.handle_new_image()
        self.assertEqual(self.mock_db.add_entry.call_count, 1)

    def test_no_callback_when_no_callback_set(self):
        from clipman.clipboard_monitor import ClipboardMonitor
        monitor = ClipboardMonitor(self.mock_db, on_new_entry=None)
        # Should not raise even without callback
        monitor.handle_new_text("no callback")
        self.mock_db.add_entry.assert_called()

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_handles_wl_paste_oserror(self, mock_run):
        mock_run.side_effect = OSError("wl-paste not found")
        # Should not raise
        self.monitor.handle_new_image()
        self.mock_db.add_entry.assert_not_called()

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_handles_empty_wl_paste_stdout(self, mock_run):
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=b""
        )
        self.monitor.handle_new_image()
        self.mock_db.add_entry.assert_not_called()

    def test_handles_unicode_text(self):
        self.monitor.handle_new_text("Hello \U0001f600 world \u00e9\u00e0\u00fc")
        self.mock_db.add_entry.assert_called_once()

    def test_handles_whitespace_only_text(self):
        self.monitor.handle_new_text("   ")
        # Whitespace-only is not empty, should be recorded
        self.mock_db.add_entry.assert_called_once()

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_rate_limiter_drops_image_after_text(self, mock_run):
        """Image event arriving within MIN_EVENT_INTERVAL after text is dropped."""
        image_data = b"\x89PNG\r\n\x1a\nimage_after_text"
        mock_run.return_value = FakeCompletedProcess(returncode=0, stdout=image_data)

        self.monitor.handle_new_text("some text")
        # Do NOT reset _last_event_time — image arrives immediately after
        self.monitor.handle_new_image()

        # Only the text event was stored; image was rate-limited
        self.assertEqual(self.mock_db.add_entry.call_count, 1)
        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="some text", sensitive=False
        )

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_rate_limiter_drops_text_after_image(self, mock_run):
        """Text event arriving within MIN_EVENT_INTERVAL after image is dropped."""
        image_data = b"\x89PNG\r\n\x1a\nimage_before_text"
        mock_run.return_value = FakeCompletedProcess(returncode=0, stdout=image_data)

        self.monitor.handle_new_image()
        # Do NOT reset _last_event_time — text arrives immediately after
        self.monitor.handle_new_text("text after image")

        # Only the image event was stored; text was rate-limited
        self.assertEqual(self.mock_db.add_entry.call_count, 1)
        self.mock_db.add_entry.assert_called_once_with(
            "image", image_data=image_data
        )

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_rate_limiter_allows_both_after_interval(self, mock_run):
        """Both text and image are accepted if separated by MIN_EVENT_INTERVAL."""
        image_data = b"\x89PNG\r\n\x1a\nimage_after_interval"
        mock_run.return_value = FakeCompletedProcess(returncode=0, stdout=image_data)

        self.monitor.handle_new_text("first")
        self.monitor._last_event_time = 0  # simulate time passing
        self.monitor.handle_new_image()

        self.assertEqual(self.mock_db.add_entry.call_count, 2)


class TestDebounce(unittest.TestCase):
    """Tests for the debounce / rate-limiting behaviour.

    The GNOME Shell extension debounces owner-changed signals with a 150ms
    GLib timeout (cancel-and-restart).  The Python daemon applies a second
    layer of rate-limiting via MIN_EVENT_INTERVAL so that bursts of D-Bus
    NewEntry calls are collapsed.
    """

    def setUp(self):
        self.mock_db = MagicMock()
        from clipman.clipboard_monitor import ClipboardMonitor
        self.monitor = ClipboardMonitor(self.mock_db)

    def test_min_event_interval_value(self):
        """MIN_EVENT_INTERVAL must be at least 100ms to complement the
        extension's 150ms debounce."""
        from clipman.clipboard_monitor import MIN_EVENT_INTERVAL
        self.assertGreaterEqual(MIN_EVENT_INTERVAL, 0.1)

    def test_burst_text_events_only_first_recorded(self):
        """A burst of text events with no delay records only the first."""
        for i in range(5):
            self.monitor.handle_new_text(f"burst-{i}")
        self.assertEqual(self.mock_db.add_entry.call_count, 1)
        self.mock_db.add_entry.assert_called_with(
            "text", content_text="burst-0", sensitive=False
        )

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_burst_image_events_only_first_recorded(self, mock_run):
        """A burst of image events with no delay records only the first."""
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=b"\x89PNGdata"
        )
        for _ in range(5):
            self.monitor.handle_new_image()
        self.assertEqual(self.mock_db.add_entry.call_count, 1)

    def test_burst_mixed_events_only_first_recorded(self):
        """Mixed text/image burst with no delay records only the first."""
        self.monitor.handle_new_text("text-first")
        with patch("clipman.clipboard_monitor.subprocess.run") as mock_run:
            mock_run.return_value = FakeCompletedProcess(
                returncode=0, stdout=b"\x89PNGdata"
            )
            self.monitor.handle_new_image()
        self.monitor.handle_new_text("text-third")
        self.assertEqual(self.mock_db.add_entry.call_count, 1)

    def test_events_accepted_after_interval_passes(self):
        """Each event is accepted when enough time has passed."""
        self.monitor.handle_new_text("first")
        self.assertEqual(self.mock_db.add_entry.call_count, 1)

        self.monitor._last_event_time = time.monotonic() - 0.2
        self.monitor.handle_new_text("second")
        self.assertEqual(self.mock_db.add_entry.call_count, 2)

        self.monitor._last_event_time = time.monotonic() - 0.2
        self.monitor.handle_new_text("third")
        self.assertEqual(self.mock_db.add_entry.call_count, 3)

    def test_rate_limiter_does_not_update_time_on_drop(self):
        """Dropped events must not reset the cooldown timer."""
        self.monitor.handle_new_text("accepted")
        saved_time = self.monitor._last_event_time

        # These should all be dropped
        self.monitor.handle_new_text("dropped-1")
        self.monitor.handle_new_text("dropped-2")

        # Timer should still reflect the accepted event
        self.assertEqual(self.monitor._last_event_time, saved_time)

    def test_first_event_always_accepted(self):
        """The very first event is never rate-limited."""
        self.monitor.handle_new_text("very first")
        self.assertEqual(self.mock_db.add_entry.call_count, 1)

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_image_after_text_accepted_after_interval(self, mock_run):
        """Image event accepted after text when interval has elapsed."""
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=b"\x89PNGdata"
        )
        self.monitor.handle_new_text("text")
        self.monitor._last_event_time = time.monotonic() - 0.2
        self.monitor.handle_new_image()
        self.assertEqual(self.mock_db.add_entry.call_count, 2)


class TestIsSensitiveFunction(unittest.TestCase):
    """Direct tests for the _is_sensitive() function."""

    def setUp(self):
        from clipman.clipboard_monitor import _is_sensitive
        self.is_sensitive = _is_sensitive

    def test_empty_string(self):
        self.assertFalse(self.is_sensitive(""))

    def test_none_like(self):
        self.assertFalse(self.is_sensitive("   "))  # < 8 chars stripped

    def test_all_token_prefixes(self):
        prefixes = [
            "ghp_ABCDEFGH12345678",
            "gho_ABCDEFGH12345678",
            "ghs_ABCDEFGH12345678",
            "github_pat_XXXXXXXXXXXXXXXX",
            "sk-proj-abcdef123456",
            "sk_live_1234567890abcdef",
            "pk_live_1234567890abcdef",
            "Bearer token12345678",
            "eyJhbGciOiJIUzI1NiJ9",
            "xoxb-123456789012",
            "AKIAIOSFODNN7EXAMPLE",
            "AIzaSyB-1234567890a",
        ]
        for token in prefixes:
            with self.subTest(token=token[:20]):
                self.assertTrue(self.is_sensitive(token), f"Expected sensitive: {token[:30]}")

    def test_mixed_case_with_digits_and_punct(self):
        # lower + upper + digit + punct = 4 categories
        self.assertTrue(self.is_sensitive("Hello123!"))

    def test_url_not_sensitive(self):
        # URLs have spaces=False but typically only 2 char categories
        self.assertFalse(self.is_sensitive("https://example.com"))

    def test_exactly_128_chars_sensitive(self):
        text = "Aa1!" + "x" * 124
        self.assertEqual(len(text), 128)
        self.assertTrue(self.is_sensitive(text))

    def test_129_chars_not_sensitive(self):
        text = "Aa1!" + "x" * 125
        self.assertEqual(len(text), 129)
        self.assertFalse(self.is_sensitive(text))


if __name__ == "__main__":
    unittest.main()
