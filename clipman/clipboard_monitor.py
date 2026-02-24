import os
import string
import subprocess
import time

from gi.repository import GLib

MAX_TEXT_SIZE = 10 * 1024 * 1024   # 10 MB
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
MIN_EVENT_INTERVAL = 0.1  # seconds — ignore events faster than this

_TOKEN_PREFIXES = ("ghp_", "gho_", "ghs_", "github_pat_", "sk-", "sk_live_",
                   "pk_live_", "Bearer ", "eyJ", "xox", "AKIA", "AIza",
                   "npm_", "-----BEGIN ")

_SENSITIVE_INFIXES = ("postgresql://", "mysql://", "mongodb://", "redis://",
                      "ssh-rsa ", "ssh-ed25519 ")


def _is_sensitive(text: str) -> bool:
    if "\n" in text.strip():
        # Still check multiline text for private keys and connection strings
        t = text.strip()
        if any(t.startswith(p) for p in _TOKEN_PREFIXES):
            return True
        if any(infix in t for infix in _SENSITIVE_INFIXES):
            return True
        return False
    t = text.strip()
    if not t or len(t) < 8 or len(t) > 128:
        return False
    if any(t.startswith(p) for p in _TOKEN_PREFIXES):
        return True
    if any(infix in t for infix in _SENSITIVE_INFIXES):
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


class _WlPasteWatcher:
    """Fallback clipboard watcher using wl-paste --watch.

    Used when the GNOME Shell extension is not available.  Spawns
    ``wl-paste --watch echo CLIP_CHANGED`` and integrates with the
    GLib main loop via io_add_watch on the subprocess stdout fd.
    """

    _SENTINEL = "CLIP_CHANGED"

    def __init__(self, monitor):
        self._monitor = monitor
        self._proc = None
        self._io_watch_id = None
        self._fd = -1
        self._buf = b""

    def start(self):
        if self._proc is not None:
            return
        try:
            self._proc = subprocess.Popen(
                ["wl-paste", "--watch", "echo", self._SENTINEL],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            self._proc = None
            return

        self._fd = self._proc.stdout.fileno()
        os.set_blocking(self._fd, False)

        self._io_watch_id = GLib.io_add_watch(
            self._fd,
            GLib.PRIORITY_DEFAULT,
            GLib.IOCondition.IN | GLib.IOCondition.HUP | GLib.IOCondition.ERR,
            self._on_stdout_ready,
        )

    def stop(self):
        if self._io_watch_id is not None:
            GLib.source_remove(self._io_watch_id)
            self._io_watch_id = None
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    self._proc.kill()
                except OSError:
                    pass
            self._proc = None
        self._fd = -1
        self._buf = b""

    def _on_stdout_ready(self, fd, condition):
        if condition & (GLib.IOCondition.HUP | GLib.IOCondition.ERR):
            GLib.timeout_add_seconds(1, self._restart)
            return GLib.SOURCE_REMOVE

        try:
            data = os.read(fd, 4096)
        except OSError:
            return GLib.SOURCE_CONTINUE

        if not data:
            GLib.timeout_add_seconds(1, self._restart)
            return GLib.SOURCE_REMOVE

        self._buf += data
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            if line.strip() == self._SENTINEL.encode():
                self._on_clipboard_changed()

        return GLib.SOURCE_CONTINUE

    def _restart(self):
        self.stop()
        self.start()
        return GLib.SOURCE_REMOVE

    def _on_clipboard_changed(self):
        try:
            result = subprocess.run(
                ["wl-paste", "--list-types"],
                capture_output=True, timeout=2,
            )
            if result.returncode != 0:
                return
            mime_types = result.stdout.decode("utf-8", errors="replace").strip()
        except (subprocess.SubprocessError, OSError):
            return

        mime_list = mime_types.split("\n")

        has_text = any(
            mt.startswith("text/plain") or mt in ("UTF8_STRING", "STRING")
            for mt in mime_list
        )
        has_image = any(mt.startswith("image/") for mt in mime_list)

        if has_text:
            self._read_text()
        elif has_image:
            self._monitor.handle_new_image()

    def _read_text(self):
        try:
            result = subprocess.run(
                ["wl-paste", "--no-newline"],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout:
                text = result.stdout.decode("utf-8", errors="replace")
                if text:
                    self._monitor.handle_new_text(text)
        except (subprocess.SubprocessError, OSError):
            pass


class ClipboardMonitor:
    """Event-driven clipboard monitor.

    Receives clipboard change notifications from the GNOME Shell extension
    via D-Bus.  When the extension is not available, falls back to
    wl-paste --watch for clipboard monitoring.
    """

    def __init__(self, db, on_new_entry=None):
        self.db = db
        self.on_new_entry = on_new_entry
        self._self_copy = False
        self._incognito = False
        self._last_event_time = 0.0
        self._watcher = None

    def start(self):
        """Start wl-paste --watch fallback (called when extension absent)."""
        if self._watcher is not None:
            return
        self._watcher = _WlPasteWatcher(self)
        self._watcher.start()

    def stop(self):
        """Stop the wl-paste --watch fallback if running."""
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None

    def set_self_copy(self, val: bool):
        self._self_copy = val

    def set_incognito(self, val: bool):
        self._incognito = val

    def _rate_limited(self):
        """Return True if this event arrived too fast (debounce)."""
        now = time.monotonic()
        if now - self._last_event_time < MIN_EVENT_INTERVAL:
            return True
        self._last_event_time = now
        return False

    def handle_new_text(self, text):
        """Called from D-Bus when the extension detects a text copy."""
        if self._self_copy:
            self._self_copy = False
            return

        if self._incognito or self._rate_limited():
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

        if self._incognito or self._rate_limited():
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
