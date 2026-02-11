import re
import string
import subprocess

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
    """Event-driven clipboard monitor.

    Receives clipboard change notifications from the GNOME Shell extension
    via D-Bus. No polling, no subprocesses for text. Images are read with
    a single wl-paste call only when the extension reports an image copy.
    """

    def __init__(self, db, on_new_entry=None):
        self.db = db
        self.on_new_entry = on_new_entry
        self._self_copy = False
        self._incognito = False

    def start(self):
        pass  # Event-driven — nothing to start

    def stop(self):
        pass  # Event-driven — nothing to stop

    def set_self_copy(self, val: bool):
        self._self_copy = val

    def set_incognito(self, val: bool):
        self._incognito = val

    def handle_new_text(self, text):
        """Called from D-Bus when the extension detects a text copy."""
        if self._self_copy:
            self._self_copy = False
            return

        if self._incognito:
            return

        if not text or len(text.encode("utf-8", errors="replace")) > MAX_TEXT_SIZE:
            return

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
