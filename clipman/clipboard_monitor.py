import subprocess
import threading
import hashlib
import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib


class ClipboardMonitor:
    def __init__(self, db, on_new_entry=None):
        self.db = db
        self.on_new_entry = on_new_entry
        self._process = None
        self._thread = None
        self._running = False
        self._last_hash = None
        self._self_copy = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        self._process = None

    def set_self_copy(self, val: bool):
        self._self_copy = val

    def _watch_loop(self):
        while self._running:
            try:
                self._process = subprocess.Popen(
                    ["wl-paste", "--watch", "echo", "CLIP_CHANGED"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                for line in self._process.stdout:
                    if not self._running:
                        break
                    decoded = line.decode("utf-8", errors="replace").strip()
                    if decoded == "CLIP_CHANGED":
                        if self._self_copy:
                            self._self_copy = False
                            continue
                        self._handle_clip_change()
                self._process.wait()
            except Exception:
                if self._running:
                    import time
                    time.sleep(1)

    def _handle_clip_change(self):
        # Try text first
        try:
            result = subprocess.run(
                ["wl-paste", "--no-newline"],
                capture_output=True, timeout=2
            )
            if result.returncode == 0 and result.stdout:
                text = result.stdout.decode("utf-8", errors="replace")
                h = hashlib.sha256(text.encode("utf-8")).hexdigest()
                if h == self._last_hash:
                    return
                self._last_hash = h
                GLib.idle_add(self._add_text_entry, text)
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
                h = hashlib.sha256(result.stdout).hexdigest()
                if h == self._last_hash:
                    return
                self._last_hash = h
                GLib.idle_add(self._add_image_entry, result.stdout)
                return
        except Exception:
            pass

    def _add_text_entry(self, text):
        self.db.add_entry("text", content_text=text)
        if self.on_new_entry:
            self.on_new_entry()
        return False  # Remove from idle

    def _add_image_entry(self, data):
        self.db.add_entry("image", image_data=data)
        if self.on_new_entry:
            self.on_new_entry()
        return False
