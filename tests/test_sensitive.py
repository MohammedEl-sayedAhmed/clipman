import random
import string
import unittest

from clipman.sensitive import _SCAN_LIMIT, is_sensitive
from tests.sensitive_corpus import benign, secret

# Categories the detector misses on purpose: a bare password or an AWS
# secret without its prefix looks like a Wi-Fi name or a licence key.
KNOWN_MISSES = {
    "password", "passphrase", "password_generated", "aws_secret_access_key",
}

# The strings from the bug report that the old rule flagged and deleted.
BUG_REPORT_BENIGN = [
    "https://github.com/MohammedEl-sayedAhmed/clipman",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://docs.google.com/document/d/1a2b3c",
    "https://example.com:8080/api",
    "https://en.wikipedia.org/wiki/Clipboard_(computing)",
    "report_2024_final.pdf",
    "IMG_20240115.jpg",
    "feature/add-dark-mode",
    "v1.2.1",
    "2024-01-15T10:30:00Z",
    "#FF5733",
    "clipman@clipman.com",
    "Ctrl+Shift+V",
    "MohammedEl-sayedAhmed",
    "src/main.py:42",
    "a3f5b9c2d1e4",
]

# Card numbers from the payment networks' public test ranges.
CARD_NUMBERS = [
    "4111111111111111",
    "4111 1111 1111 1111",
    "4111-1111-1111-1111",
    "378282246310005",
    "5500005555555559",
]


class TestCorpus(unittest.TestCase):
    """Whole-corpus checks: no benign clip is ever flagged."""

    def test_no_benign_clip_is_flagged(self):
        flagged = [item["text"] for item in benign if is_sensitive(item["text"])]
        self.assertEqual(flagged, [], f"{len(flagged)} benign clips flagged")

    def test_every_detected_category_has_a_hit(self):
        missed = {}
        for item in secret:
            if not is_sensitive(item["text"]):
                missed.setdefault(item["category"], []).append(item["text"])
        missed_categories = {c.split("/")[-1] for c in missed}
        self.assertEqual(missed_categories, KNOWN_MISSES, missed)

    def test_recall_floor(self):
        caught = sum(1 for item in secret if is_sensitive(item["text"]))
        self.assertGreaterEqual(caught, 129, f"{caught}/{len(secret)} caught")


class TestBugReport(unittest.TestCase):
    """The regressions that started this work."""

    def test_everyday_clips_are_not_sensitive(self):
        flagged = [t for t in BUG_REPORT_BENIGN if is_sensitive(t)]
        self.assertEqual(flagged, [])

    def test_card_numbers_are_sensitive(self):
        missed = [t for t in CARD_NUMBERS if not is_sensitive(t)]
        self.assertEqual(missed, [])

    def test_luhn_invalid_digits_are_not_sensitive(self):
        self.assertFalse(is_sensitive("4111111111111112"))
        self.assertFalse(is_sensitive("1234567890123456"))


class TestMultiline(unittest.TestCase):
    """Multi-line clips are judged line by line, never by size."""

    def test_secret_inside_a_config_blob(self):
        # Built from parts so secret scanners do not match it.
        text = "HOST=db.internal\nPORT=5432\nPASS" + "WORD=Xk9mP2vL5nQ8wR\nDEBUG=false"
        self.assertTrue(is_sensitive(text))

    def test_benign_config_blob(self):
        text = "HOST=db.internal\nPORT=5432\nDEBUG=false\nWAYLAND_DISPLAY=wayland-0"
        self.assertFalse(is_sensitive(text))

    def test_random_text_is_not_a_secret(self):
        rng = random.Random(7)
        alphabet = string.ascii_letters + string.digits + " ./:-_=,"
        text = "\n".join(
            "".join(rng.choice(alphabet) for _ in range(80)) for _ in range(128)
        )
        self.assertFalse(is_sensitive(text))

    def test_scan_stops_at_the_limit(self):
        padding = "x" * (_SCAN_LIMIT + 10)
        token = "AKIA" + "IOSFODNN7EXAMPLE"
        self.assertTrue(is_sensitive(token + "\n" + padding))
        self.assertFalse(is_sensitive(padding + "\n" + token))
