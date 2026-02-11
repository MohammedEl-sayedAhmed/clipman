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
        self.monitor.handle_new_text("same text")

        self.assertEqual(self.mock_db.add_entry.call_count, 2)

    def test_detects_changed_text(self):
        self.monitor.handle_new_text("first text")
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


if __name__ == "__main__":
    unittest.main()
