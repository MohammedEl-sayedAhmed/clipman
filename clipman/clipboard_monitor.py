import os
import string
import subprocess

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import GLib

MAX_TEXT_SIZE = 10 * 1024 * 1024   # 10 MB
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB

_TOKEN_PREFIXES = ("ghp_", "gho_", "ghs_", "github_pat_", "sk-", "sk_live_",
                   "pk_live_", "Bearer ", "eyJ", "xox", "AKIA", "AIza")


def _is_sensitive(text: str) -> bool:
    if "\n" in text.strip():
        return False
    t = text.strip()
    if not t or len(t) < 8 or len(t) > 128:
        return False
    if any(t.startswith(p) for p in _TOKEN_PREFIXES):
        return True
    if " " in t:
        return False
    cats = set()
    for ch in t:
        if ch in string.ascii_lowercase:
            cats.add("lower")
        elif ch in string.ascii_uppercase:
            cats.add("upper")
        elif ch in string.digits:
            cats.add("digit")
        elif ch in string.punctuation:
            cats.add("punct")
    if len(cats) >= 3 and len(t) >= 8:
        return True
    return False


class ClipboardMonitor:
    """Hybrid clipboard monitor.

    Primary: wl-paste --watch detects ALL clipboard changes (Wayland native
    and XWayland apps). Secondary: the GNOME Shell extension can also push
    entries via D-Bus. The DB deduplicates by content hash, so overlapping
    detections are harmless.
    """

    def __init__(self, db, on_new_entry=None):
        self.db = db
        self.on_new_entry = on_new_entry
        self._self_copy = False
        self._incognito = False
        self._watch_proc = None
        self._watch_source = None
        self._last_text = None

    def start(self):
        self._start_watcher()

    def stop(self):
        if self._watch_source:
            GLib.source_remove(self._watch_source)
            self._watch_source = None
        if self._watch_proc:
            self._watch_proc.kill()
            self._watch_proc.wait()
            self._watch_proc = None

    def _start_watcher(self):
        """Spawn wl-paste --watch to detect clipboard changes."""
        try:
            self._watch_proc = subprocess.Popen(
                ["wl-paste", "--watch", "echo", ""],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            self._watch_source = GLib.io_add_watch(
                self._watch_proc.stdout.fileno(),
                GLib.PRIORITY_DEFAULT,
                GLib.IO_IN | GLib.IO_HUP,
                self._on_watch_event,
            )
        except (FileNotFoundError, OSError):
            pass  # wl-paste not installed

    def _on_watch_event(self, fd, condition):
        if condition & GLib.IO_HUP:
            # wl-paste exited — clean up and restart after a short delay
            if self._watch_proc:
                self._watch_proc.stdout.close()
                self._watch_proc.wait()
                self._watch_proc = None
            self._watch_source = None
            GLib.timeout_add_seconds(2, self._start_watcher)
            return False  # remove this source

        os.read(fd, 4096)  # consume the echo output

        if self._self_copy or self._incognito:
            return True

        # Read text content
        try:
            result = subprocess.run(
                ["wl-paste", "--no-newline", "--type", "text/plain"],
                capture_output=True, timeout=2,
            )
            if result.returncode == 0 and result.stdout:
                text = result.stdout.decode("utf-8", errors="replace")
                if text != self._last_text:
                    self._last_text = text
                    self.handle_new_text(text)
                return True
        except (subprocess.SubprocessError, OSError):
            pass

        # No text — try image
        try:
            result = subprocess.run(
                ["wl-paste", "--type", "image/png"],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout:
                if len(result.stdout) <= MAX_IMAGE_SIZE:
                    self.db.add_entry("image", image_data=result.stdout)
                    if self.on_new_entry:
                        self.on_new_entry()
        except (subprocess.SubprocessError, OSError):
            pass

        return True

    def set_self_copy(self, val: bool):
        self._self_copy = val

    def set_incognito(self, val: bool):
        self._incognito = val

    def handle_new_text(self, text):
        """Called when new text is detected (from wl-paste watcher or D-Bus)."""
        if self._self_copy:
            self._self_copy = False
            return

        if self._incognito:
            return

        if not text or len(text.encode("utf-8", errors="replace")) > MAX_TEXT_SIZE:
            return

        self._last_text = text
        sensitive = _is_sensitive(text)
        self.db.add_entry("text", content_text=text, sensitive=sensitive)
        if self.on_new_entry:
            self.on_new_entry()

    def handle_new_image(self):
        """Called from D-Bus when the extension detects an image copy.

        Uses a single wl-paste call to read the image data. This only
        happens when an image is actually copied (not on a timer), so
        the single subprocess call does not cause visible flicker.
        """
        if self._self_copy:
            self._self_copy = False
            return

        if self._incognito:
            return

        try:
            result = subprocess.run(
                ["wl-paste", "--type", "image/png"],
                capture_output=True, timeout=5
            )
            if result.returncode == 0 and result.stdout:
                if len(result.stdout) <= MAX_IMAGE_SIZE:
                    self.db.add_entry("image", image_data=result.stdout)
                    if self.on_new_entry:
                        self.on_new_entry()
        except (subprocess.SubprocessError, OSError):
            pass
