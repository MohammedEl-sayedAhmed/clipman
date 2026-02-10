import subprocess
import hashlib
import threading
import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib


MAX_TEXT_SIZE = 10 * 1024 * 1024   # 10 MB
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
POLL_INTERVAL_SEC = 1.5  # Poll clipboard every 1.5 seconds


class ClipboardMonitor:
    def __init__(self, db, on_new_entry=None):
        self.db = db
        self.on_new_entry = on_new_entry
        self._last_hash = None
        self._self_copy = False
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def set_self_copy(self, val: bool):
        self._self_copy = val

    def _poll_loop(self):
        """Runs in background thread. Polls wl-paste without blocking GTK."""
        while self._running:
            if self._self_copy:
                self._self_copy = False
            else:
                self._check_clipboard()

            # Sleep in small increments so stop() is responsive
            elapsed = 0.0
            while elapsed < POLL_INTERVAL_SEC and self._running:
                threading.Event().wait(0.1)
                elapsed += 0.1

    def _check_clipboard(self):
        # Try text first
        try:
            result = subprocess.run(
                ["wl-paste", "--no-newline"],
                capture_output=True, timeout=2
            )
            if result.returncode == 0 and result.stdout:
                if len(result.stdout) <= MAX_TEXT_SIZE:
                    text = result.stdout.decode("utf-8", errors="replace")
                    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    if h != self._last_hash:
                        self._last_hash = h
                        # Dispatch DB write and callback to main thread
                        GLib.idle_add(self._handle_new_text, text)
                return
        except Exception:
            pass

        # Try image
        try:
            result = subprocess.run(
                ["wl-paste", "--type", "image/png"],
                capture_output=True, timeout=5
            )
            if result.returncode == 0 and result.stdout:
                if len(result.stdout) <= MAX_IMAGE_SIZE:
                    h = hashlib.sha256(result.stdout).hexdigest()
                    if h != self._last_hash:
                        self._last_hash = h
                        image_data = result.stdout
                        GLib.idle_add(self._handle_new_image, image_data)
        except Exception:
            pass

    def _handle_new_text(self, text):
        """Called on GTK main thread via GLib.idle_add."""
        self.db.add_entry("text", content_text=text)
        if self.on_new_entry:
            self.on_new_entry()
        return False  # Don't repeat

    def _handle_new_image(self, image_data):
        """Called on GTK main thread via GLib.idle_add."""
        self.db.add_entry("image", image_data=image_data)
        if self.on_new_entry:
            self.on_new_entry()
        return False  # Don't repeat
