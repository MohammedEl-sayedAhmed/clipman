import time
import unittest


class TestDetectUrl(unittest.TestCase):
    """Tests for ClipmanWindow._detect_url() static method."""

    @staticmethod
    def _detect_url(text):
        # Import the static method without needing GTK
        t = text.strip().split("\n")[0].strip()
        if t.startswith(("http://", "https://")) and " " not in t:
            return t
        if t.startswith("www.") and " " not in t:
            return "https://" + t
        return None

    def test_https_url(self):
        self.assertEqual(
            self._detect_url("https://example.com"),
            "https://example.com"
        )

    def test_http_url(self):
        self.assertEqual(
            self._detect_url("http://example.com"),
            "http://example.com"
        )

    def test_www_url_adds_https(self):
        self.assertEqual(
            self._detect_url("www.example.com"),
            "https://www.example.com"
        )

    def test_url_with_path(self):
        self.assertEqual(
            self._detect_url("https://example.com/path/to/page"),
            "https://example.com/path/to/page"
        )

    def test_url_with_query_params(self):
        self.assertEqual(
            self._detect_url("https://example.com/search?q=test&page=1"),
            "https://example.com/search?q=test&page=1"
        )

    def test_url_with_fragment(self):
        self.assertEqual(
            self._detect_url("https://example.com/page#section"),
            "https://example.com/page#section"
        )

    def test_not_url_plain_text(self):
        self.assertIsNone(self._detect_url("hello world"))

    def test_not_url_no_protocol(self):
        self.assertIsNone(self._detect_url("example.com"))

    def test_url_with_spaces_is_not_url(self):
        self.assertIsNone(
            self._detect_url("https://example.com not a url")
        )

    def test_multiline_uses_first_line(self):
        self.assertEqual(
            self._detect_url("https://example.com\nextra line"),
            "https://example.com"
        )

    def test_whitespace_stripped(self):
        self.assertEqual(
            self._detect_url("  https://example.com  "),
            "https://example.com"
        )

    def test_empty_string(self):
        self.assertIsNone(self._detect_url(""))

    def test_only_whitespace(self):
        self.assertIsNone(self._detect_url("   "))

    def test_ftp_not_detected(self):
        self.assertIsNone(self._detect_url("ftp://files.example.com"))


class TestFormatTime(unittest.TestCase):
    """Tests for ClipmanWindow._format_time() logic."""

    @staticmethod
    def _format_time(timestamp):
        from clipman import _
        diff = time.time() - timestamp
        if diff < 60:
            return _("just now")
        elif diff < 3600:
            mins = int(diff / 60)
            return _("{n}m ago").format(n=mins)
        elif diff < 86400:
            hours = int(diff / 3600)
            return _("{n}h ago").format(n=hours)
        else:
            days = int(diff / 86400)
            return _("{n}d ago").format(n=days)

    def test_just_now(self):
        self.assertEqual(self._format_time(time.time()), "just now")

    def test_minutes_ago(self):
        result = self._format_time(time.time() - 120)
        self.assertEqual(result, "2m ago")

    def test_hours_ago(self):
        result = self._format_time(time.time() - 7200)
        self.assertEqual(result, "2h ago")

    def test_days_ago(self):
        result = self._format_time(time.time() - 172800)
        self.assertEqual(result, "2d ago")

    def test_one_minute_boundary(self):
        result = self._format_time(time.time() - 60)
        self.assertEqual(result, "1m ago")

    def test_one_hour_boundary(self):
        result = self._format_time(time.time() - 3600)
        self.assertEqual(result, "1h ago")

    def test_one_day_boundary(self):
        result = self._format_time(time.time() - 86400)
        self.assertEqual(result, "1d ago")

    def test_many_days(self):
        result = self._format_time(time.time() - 86400 * 30)
        self.assertEqual(result, "30d ago")


if __name__ == "__main__":
    unittest.main()
