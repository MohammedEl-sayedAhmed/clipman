import hashlib
import threading
import time
import unittest
from unittest.mock import patch, MagicMock, PropertyMock


class FakeCompletedProcess:
    """Mimics subprocess.CompletedProcess."""
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestClipboardMonitor(unittest.TestCase):
    """Tests for the ClipboardMonitor polling logic."""

    def setUp(self):
        self.mock_db = MagicMock()
        self.new_entry_called = threading.Event()

        def on_new_entry():
            self.new_entry_called.set()

        # Patch GLib.idle_add to run callbacks immediately (no GTK main loop)
        self.idle_add_patcher = patch(
            "clipman.clipboard_monitor.GLib.idle_add",
            side_effect=lambda func, *args: func(*args)
        )
        self.idle_add_patcher.start()

        from clipman.clipboard_monitor import ClipboardMonitor
        self.monitor = ClipboardMonitor(self.mock_db, on_new_entry=on_new_entry)

    def tearDown(self):
        self.monitor.stop()
        self.idle_add_patcher.stop()

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_detects_new_text(self, mock_run):
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=b"hello clipboard"
        )

        self.monitor._check_clipboard()

        self.mock_db.add_entry.assert_called_once_with(
            "text", content_text="hello clipboard"
        )

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_skips_duplicate_text(self, mock_run):
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=b"same text"
        )

        self.monitor._check_clipboard()
        self.monitor._check_clipboard()

        # Should only be called once (duplicate skipped)
        self.mock_db.add_entry.assert_called_once()

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_detects_changed_text(self, mock_run):
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=b"first text"
        )
        self.monitor._check_clipboard()

        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=b"second text"
        )
        self.monitor._check_clipboard()

        self.assertEqual(self.mock_db.add_entry.call_count, 2)

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_detects_new_image(self, mock_run):
        # First call for text returns failure, second for image returns data
        text_result = FakeCompletedProcess(returncode=1, stdout=b"")
        image_data = b"\x89PNG\r\n\x1a\nfake_image"
        image_result = FakeCompletedProcess(returncode=0, stdout=image_data)
        mock_run.side_effect = [text_result, image_result]

        self.monitor._check_clipboard()

        self.mock_db.add_entry.assert_called_once_with(
            "image", image_data=image_data
        )

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_skips_oversized_text(self, mock_run):
        big_text = b"x" * (10 * 1024 * 1024 + 1)  # Just over 10MB
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=big_text
        )

        self.monitor._check_clipboard()

        self.mock_db.add_entry.assert_not_called()

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_skips_oversized_image(self, mock_run):
        text_result = FakeCompletedProcess(returncode=1, stdout=b"")
        big_image = b"\x89" * (10 * 1024 * 1024 + 1)
        image_result = FakeCompletedProcess(returncode=0, stdout=big_image)
        mock_run.side_effect = [text_result, image_result]

        self.monitor._check_clipboard()

        self.mock_db.add_entry.assert_not_called()

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_self_copy_skips_poll(self, mock_run):
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=b"test"
        )

        self.monitor.set_self_copy(True)

        # Simulate one poll cycle
        # In _poll_loop, if _self_copy is True, _check_clipboard is not called
        if self.monitor._self_copy:
            self.monitor._self_copy = False
        else:
            self.monitor._check_clipboard()

        mock_run.assert_not_called()

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_handles_subprocess_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="wl-paste", timeout=2)

        # Should not raise
        self.monitor._check_clipboard()
        self.mock_db.add_entry.assert_not_called()

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_handles_empty_clipboard(self, mock_run):
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=b""
        )

        self.monitor._check_clipboard()

        self.mock_db.add_entry.assert_not_called()

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_handles_wl_paste_error(self, mock_run):
        mock_run.return_value = FakeCompletedProcess(
            returncode=1, stdout=b""
        )

        # Should not raise
        self.monitor._check_clipboard()
        self.mock_db.add_entry.assert_not_called()

    def test_start_creates_thread(self):
        with patch("clipman.clipboard_monitor.subprocess.run"):
            self.monitor.start()
            time.sleep(0.1)
            self.assertTrue(self.monitor._running)
            self.assertIsNotNone(self.monitor._thread)
            self.assertTrue(self.monitor._thread.is_alive())
            self.monitor.stop()

    def test_stop_terminates_thread(self):
        with patch("clipman.clipboard_monitor.subprocess.run"):
            self.monitor.start()
            time.sleep(0.1)
            self.monitor.stop()
            self.assertFalse(self.monitor._running)
            self.monitor._thread.join(timeout=3)
            self.assertFalse(self.monitor._thread.is_alive())

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_callback_fires_on_new_entry(self, mock_run):
        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=b"trigger callback"
        )

        self.monitor._check_clipboard()

        self.assertTrue(self.new_entry_called.is_set())

    @patch("clipman.clipboard_monitor.subprocess.run")
    def test_hash_tracking(self, mock_run):
        text = b"tracked text"
        expected_hash = hashlib.sha256(text).hexdigest()

        mock_run.return_value = FakeCompletedProcess(
            returncode=0, stdout=text
        )

        self.monitor._check_clipboard()

        self.assertEqual(self.monitor._last_hash, expected_hash)


if __name__ == "__main__":
    unittest.main()
