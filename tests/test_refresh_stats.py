"""scripts/refresh_stats.py: the Snap Store devices-by-country summary.

The workflow passes the JSON that ``snapcraft metrics clipman --name
weekly_installed_base_by_country --format json`` prints; these tests feed
the same shape without the store.
"""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "refresh_stats", ROOT / "scripts" / "refresh_stats.py"
)
stats = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(stats)


def metric(series, buckets=("2026-11-01", "2026-11-02", "2026-11-03"),
           status="OK"):
    return {
        "buckets": list(buckets),
        "metric_name": "weekly_installed_base_by_country",
        "series": [{"name": name, "values": values}
                   for name, values in series.items()],
        "snap_id": "test-snap-id",
        "status": status,
    }


class TestSummary(unittest.TestCase):
    def test_newest_week_and_the_year(self):
        summary = stats.summarize_snap_countries(metric({
            "in": [30, 34, 35],
            "de": [18, 19, 20],
            "br": [21, 0, None],
            "us": [None, None, None],
        }))
        self.assertEqual(summary["date"], "2026-11-03")
        self.assertEqual(summary["since"], "2026-11-01")
        self.assertEqual(summary["by_country"], {"IN": 35, "DE": 20})
        self.assertEqual(summary["devices"], 55)
        self.assertEqual(summary["territories"], 2)
        # Brazil had devices earlier in the period; the US never did.
        self.assertEqual(summary["territories_year"], 3)

    def test_skips_trailing_days_without_data(self):
        summary = stats.summarize_snap_countries(metric({
            "fr": [10, 11, None],
            "eg": [8, 8, None],
        }))
        self.assertEqual(summary["date"], "2026-11-02")
        self.assertEqual(summary["by_country"], {"FR": 11, "EG": 8})

    def test_ties_sort_by_country_code(self):
        summary = stats.summarize_snap_countries(metric({
            "us": [0, 0, 5], "ca": [0, 0, 5], "in": [0, 0, 9],
        }))
        self.assertEqual(list(summary["by_country"]), ["IN", "CA", "US"])

    def test_numeric_text_counts(self):
        summary = stats.summarize_snap_countries(metric({"in": ["3", "x", "4"]}))
        self.assertEqual(summary["by_country"], {"IN": 4})

    def test_no_usable_data_gives_none(self):
        for bad in (None, [], {}, metric({}, status="FAIL"),
                    metric({"in": [1, 2, 3]}, status="NO DATA"),
                    metric({"in": [None, 0, None]}),
                    {"status": "OK", "buckets": "x", "series": []}):
            with self.subTest(bad=bad):
                self.assertIsNone(stats.summarize_snap_countries(bad))


class TestWrite(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="clipman-stats-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.out = os.path.join(self.dir, stats.SNAP_COUNTRIES_FILE)

    def _metrics_file(self, text):
        path = os.path.join(self.dir, "metrics.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_writes_the_summary(self):
        data = json.dumps(metric({"in": [1, 2, 3]}))
        self.assertTrue(stats.write_snap_countries(
            self.dir, self._metrics_file(data)))
        with open(self.out, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["by_country"], {"IN": 3})

    def test_reads_json_after_log_lines(self):
        data = "Fetching metrics...\n" + json.dumps(metric({"de": [0, 1, 2]}))
        self.assertTrue(stats.write_snap_countries(
            self.dir, self._metrics_file(data)))

    def test_the_same_input_writes_the_same_bytes(self):
        path = self._metrics_file(json.dumps(metric({"in": [1, 2, 3],
                                                     "de": [3, 2, 1]})))
        stats.write_snap_countries(self.dir, path)
        with open(self.out, "rb") as f:
            first = f.read()
        stats.write_snap_countries(self.dir, path)
        with open(self.out, "rb") as f:
            self.assertEqual(f.read(), first)

    def test_keeps_the_last_file_when_the_store_fails(self):
        with open(self.out, "w", encoding="utf-8") as f:
            f.write('{"territories_year": 62}\n')
        for text in ("", "not json", json.dumps(metric({}, status="FAIL"))):
            with self.subTest(text=text):
                self.assertFalse(stats.write_snap_countries(
                    self.dir, self._metrics_file(text)))
        self.assertFalse(stats.write_snap_countries(
            self.dir, os.path.join(self.dir, "missing.json")))
        with open(self.out, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"territories_year": 62})


if __name__ == "__main__":
    unittest.main()
