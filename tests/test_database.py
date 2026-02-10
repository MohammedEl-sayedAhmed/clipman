import os
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path


class TestClipboardDB(unittest.TestCase):
    """Tests for the ClipboardDB storage layer."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmpdir) / "clipman"
        self.images_dir = self.data_dir / "images"
        self.db_path = self.data_dir / "clipman.db"

        # Patch module-level paths before importing
        self._patches = [
            patch("clipman.database.DATA_DIR", self.data_dir),
            patch("clipman.database.IMAGES_DIR", self.images_dir),
            patch("clipman.database.DB_PATH", self.db_path),
        ]
        for p in self._patches:
            p.start()

        from clipman.database import ClipboardDB
        self.db = ClipboardDB()

    def tearDown(self):
        self.db.close()
        for p in self._patches:
            p.stop()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_add_text_entry(self):
        entry_id = self.db.add_entry("text", content_text="hello world")
        self.assertGreater(entry_id, 0)

        entries = self.db.get_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["content_text"], "hello world")
        self.assertEqual(entries[0]["content_type"], "text")
        self.assertEqual(entries[0]["pinned"], 0)

    def test_add_image_entry(self):
        fake_png = b"\x89PNG\r\n\x1a\nfake_image_data"
        entry_id = self.db.add_entry("image", image_data=fake_png)
        self.assertGreater(entry_id, 0)

        entries = self.db.get_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["content_type"], "image")
        self.assertIsNotNone(entries[0]["image_path"])
        self.assertTrue(os.path.exists(entries[0]["image_path"]))

    def test_add_invalid_entry(self):
        result = self.db.add_entry("text")  # no content_text
        self.assertEqual(result, -1)

        result = self.db.add_entry("image")  # no image_data
        self.assertEqual(result, -1)

    def test_duplicate_text_updates_timestamp(self):
        self.db.add_entry("text", content_text="duplicate")
        entries_before = self.db.get_entries()
        original_time = entries_before[0]["accessed_at"]

        time.sleep(0.05)
        entry_id = self.db.add_entry("text", content_text="duplicate")

        entries_after = self.db.get_entries()
        self.assertEqual(len(entries_after), 1)  # Still only one entry
        self.assertGreater(entries_after[0]["accessed_at"], original_time)

    def test_duplicate_image_updates_timestamp(self):
        fake_png = b"\x89PNG\r\n\x1a\ntest_dup_image"
        self.db.add_entry("image", image_data=fake_png)
        entries_before = self.db.get_entries()

        time.sleep(0.05)
        self.db.add_entry("image", image_data=fake_png)

        entries_after = self.db.get_entries()
        self.assertEqual(len(entries_after), 1)
        self.assertGreater(entries_after[0]["accessed_at"],
                           entries_before[0]["accessed_at"])

    def test_get_entries_ordering(self):
        self.db.add_entry("text", content_text="first")
        time.sleep(0.05)
        self.db.add_entry("text", content_text="second")
        time.sleep(0.05)
        self.db.add_entry("text", content_text="third")

        entries = self.db.get_entries()
        self.assertEqual(len(entries), 3)
        # Most recent first
        self.assertEqual(entries[0]["content_text"], "third")
        self.assertEqual(entries[1]["content_text"], "second")
        self.assertEqual(entries[2]["content_text"], "first")

    def test_pinned_entries_come_first(self):
        id1 = self.db.add_entry("text", content_text="unpinned")
        time.sleep(0.05)
        id2 = self.db.add_entry("text", content_text="will be pinned")
        time.sleep(0.05)
        self.db.add_entry("text", content_text="latest unpinned")

        self.db.toggle_pin(id2)

        entries = self.db.get_entries()
        self.assertEqual(entries[0]["content_text"], "will be pinned")
        self.assertEqual(entries[0]["pinned"], 1)

    def test_get_entries_limit(self):
        for i in range(10):
            self.db.add_entry("text", content_text=f"entry {i}")

        entries = self.db.get_entries(limit=5)
        self.assertEqual(len(entries), 5)

    def test_get_entries_offset(self):
        for i in range(10):
            self.db.add_entry("text", content_text=f"entry {i}")
            time.sleep(0.01)

        entries = self.db.get_entries(limit=5, offset=5)
        self.assertEqual(len(entries), 5)
        # These should be the older entries
        self.assertEqual(entries[0]["content_text"], "entry 4")

    def test_search(self):
        self.db.add_entry("text", content_text="hello world")
        self.db.add_entry("text", content_text="goodbye world")
        self.db.add_entry("text", content_text="hello there")

        results = self.db.search("hello")
        self.assertEqual(len(results), 2)
        texts = {r["content_text"] for r in results}
        self.assertIn("hello world", texts)
        self.assertIn("hello there", texts)

    def test_search_no_results(self):
        self.db.add_entry("text", content_text="hello world")
        results = self.db.search("nonexistent")
        self.assertEqual(len(results), 0)

    def test_search_escapes_wildcards(self):
        self.db.add_entry("text", content_text="100% done")
        self.db.add_entry("text", content_text="file_name.txt")
        self.db.add_entry("text", content_text="normal text")

        results = self.db.search("%")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content_text"], "100% done")

        results = self.db.search("_")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content_text"], "file_name.txt")

    def test_toggle_pin(self):
        entry_id = self.db.add_entry("text", content_text="pin me")

        result = self.db.toggle_pin(entry_id)
        self.assertTrue(result)  # Now pinned

        entries = self.db.get_entries()
        self.assertEqual(entries[0]["pinned"], 1)

        result = self.db.toggle_pin(entry_id)
        self.assertFalse(result)  # Now unpinned

        entries = self.db.get_entries()
        self.assertEqual(entries[0]["pinned"], 0)

    def test_toggle_pin_nonexistent(self):
        result = self.db.toggle_pin(9999)
        self.assertFalse(result)

    def test_delete_entry(self):
        entry_id = self.db.add_entry("text", content_text="delete me")
        entries = self.db.get_entries()
        self.assertEqual(len(entries), 1)

        self.db.delete_entry(entry_id)
        entries = self.db.get_entries()
        self.assertEqual(len(entries), 0)

    def test_delete_image_removes_file(self):
        fake_png = b"\x89PNG\r\n\x1a\nimage_to_delete"
        entry_id = self.db.add_entry("image", image_data=fake_png)

        entries = self.db.get_entries()
        image_path = entries[0]["image_path"]
        self.assertTrue(os.path.exists(image_path))

        self.db.delete_entry(entry_id)
        self.assertFalse(os.path.exists(image_path))

    def test_clear_unpinned(self):
        id1 = self.db.add_entry("text", content_text="unpinned 1")
        id2 = self.db.add_entry("text", content_text="pinned 1")
        id3 = self.db.add_entry("text", content_text="unpinned 2")

        self.db.toggle_pin(id2)  # Pin entry 2

        self.db.clear_unpinned()

        entries = self.db.get_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["content_text"], "pinned 1")
        self.assertEqual(entries[0]["pinned"], 1)

    def test_clear_unpinned_removes_images(self):
        fake_png = b"\x89PNG\r\n\x1a\nunpinned_image"
        self.db.add_entry("image", image_data=fake_png)

        entries = self.db.get_entries()
        image_path = entries[0]["image_path"]
        self.assertTrue(os.path.exists(image_path))

        self.db.clear_unpinned()
        self.assertFalse(os.path.exists(image_path))

    def test_clear_unpinned_with_no_entries(self):
        # Should not raise
        self.db.clear_unpinned()
        entries = self.db.get_entries()
        self.assertEqual(len(entries), 0)

    def test_update_accessed(self):
        entry_id = self.db.add_entry("text", content_text="access me")
        entries = self.db.get_entries()
        original_time = entries[0]["accessed_at"]

        time.sleep(0.05)
        self.db.update_accessed(entry_id)

        entries = self.db.get_entries()
        self.assertGreater(entries[0]["accessed_at"], original_time)

    def test_enforce_max_entries(self):
        from clipman.database import MAX_ENTRIES

        # Add more than MAX_ENTRIES
        for i in range(MAX_ENTRIES + 10):
            self.db.add_entry("text", content_text=f"entry {i}")
            time.sleep(0.001)

        entries = self.db.get_entries(limit=MAX_ENTRIES + 10)
        self.assertLessEqual(len(entries), MAX_ENTRIES)

    def test_enforce_max_entries_preserves_pinned(self):
        # Pin one entry, then fill up to max
        first_id = self.db.add_entry("text", content_text="pinned entry")
        self.db.toggle_pin(first_id)

        with patch("clipman.database.MAX_ENTRIES", 5):
            for i in range(10):
                self.db.add_entry("text", content_text=f"entry {i}")
                time.sleep(0.001)

        entries = self.db.get_entries(limit=100)
        pinned = [e for e in entries if e["pinned"]]
        self.assertEqual(len(pinned), 1)
        self.assertEqual(pinned[0]["content_text"], "pinned entry")

    def test_data_dir_permissions(self):
        stat = os.stat(self.data_dir)
        self.assertEqual(stat.st_mode & 0o777, 0o700)

        stat = os.stat(self.images_dir)
        self.assertEqual(stat.st_mode & 0o777, 0o700)

    def test_content_hash_uniqueness(self):
        from clipman.database import content_hash

        h1 = content_hash(b"hello")
        h2 = content_hash(b"world")
        h3 = content_hash(b"hello")

        self.assertNotEqual(h1, h2)
        self.assertEqual(h1, h3)


if __name__ == "__main__":
    unittest.main()
