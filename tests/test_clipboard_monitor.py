import hashlib
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
            "text", content_text="hello clipboard"
        )

    def test_skips_duplicate_text(self):
        self.monitor.handle_new_text("same text")
        self.monitor.handle_new_text("same text")

        self.mock_db.add_entry.assert_called_once()

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
    def test_skips_duplicate_image(self, mock_run):
        image_data = b"\x89PNG\r\n\x1a\nfake_image"
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=image_data
        )

        self.monitor.handle_new_image()
        self.monitor.handle_new_image()

        self.mock_db.add_entry.assert_called_once()

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

    def test_hash_tracking_text(self):
        text = "tracked text"
        expected_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        self.monitor.handle_new_text(text)

        self.assertEqual(self.monitor._last_hash, expected_hash)

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_hash_tracking_image(self, mock_run):
        image_data = b"\x89PNGtracked"
        expected_hash = hashlib.sha256(image_data).hexdigest()
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=image_data
        )

        self.monitor.handle_new_image()

        self.assertEqual(self.monitor._last_hash, expected_hash)

    def test_start_stop_are_noops(self):
        # Should not raise
        self.monitor.start()
        self.monitor.stop()


if __name__ == "__main__":
    unittest.main()
