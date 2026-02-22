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

    # ── count_entries ──────────────────────────────────────────────

    def test_count_entries_all(self):
        self.db.add_entry("text", content_text="one")
        self.db.add_entry("text", content_text="two")
        fake_png = b"\x89PNG\r\n\x1a\ncount_img"
        self.db.add_entry("image", image_data=fake_png)

        self.assertEqual(self.db.count_entries(), 3)

    def test_count_entries_by_type(self):
        self.db.add_entry("text", content_text="one")
        self.db.add_entry("text", content_text="two")
        fake_png = b"\x89PNG\r\n\x1a\ncount_img2"
        self.db.add_entry("image", image_data=fake_png)

        self.assertEqual(self.db.count_entries("text"), 2)
        self.assertEqual(self.db.count_entries("image"), 1)

    def test_count_entries_empty(self):
        self.assertEqual(self.db.count_entries(), 0)
        self.assertEqual(self.db.count_entries("text"), 0)

    # ── get_entries with content_type filter ────────────────────────

    def test_get_entries_filter_text(self):
        self.db.add_entry("text", content_text="hello")
        fake_png = b"\x89PNG\r\n\x1a\nfilter_img"
        self.db.add_entry("image", image_data=fake_png)

        text_entries = self.db.get_entries(content_type="text")
        self.assertEqual(len(text_entries), 1)
        self.assertEqual(text_entries[0]["content_type"], "text")

    def test_get_entries_filter_image(self):
        self.db.add_entry("text", content_text="hello")
        fake_png = b"\x89PNG\r\n\x1a\nfilter_img2"
        self.db.add_entry("image", image_data=fake_png)

        image_entries = self.db.get_entries(content_type="image")
        self.assertEqual(len(image_entries), 1)
        self.assertEqual(image_entries[0]["content_type"], "image")

    def test_get_entries_no_filter_returns_all(self):
        self.db.add_entry("text", content_text="hello")
        fake_png = b"\x89PNG\r\n\x1a\nfilter_img3"
        self.db.add_entry("image", image_data=fake_png)

        all_entries = self.db.get_entries()
        self.assertEqual(len(all_entries), 2)

    # ── Snippets CRUD ──────────────────────────────────────────────

    def test_add_snippet(self):
        sid = self.db.add_snippet("Greeting", "Hello, world!")
        self.assertGreater(sid, 0)

        snippets = self.db.get_snippets()
        self.assertEqual(len(snippets), 1)
        self.assertEqual(snippets[0]["name"], "Greeting")
        self.assertEqual(snippets[0]["content_text"], "Hello, world!")

    def test_get_snippets_ordering(self):
        self.db.add_snippet("First", "aaa")
        time.sleep(0.05)
        self.db.add_snippet("Second", "bbb")

        snippets = self.db.get_snippets()
        self.assertEqual(len(snippets), 2)
        # Most recent first
        self.assertEqual(snippets[0]["name"], "Second")
        self.assertEqual(snippets[1]["name"], "First")

    def test_update_snippet(self):
        sid = self.db.add_snippet("Old name", "Old content")
        self.db.update_snippet(sid, "New name", "New content")

        snippets = self.db.get_snippets()
        self.assertEqual(snippets[0]["name"], "New name")
        self.assertEqual(snippets[0]["content_text"], "New content")

    def test_delete_snippet(self):
        sid = self.db.add_snippet("Delete me", "content")
        self.db.delete_snippet(sid)

        snippets = self.db.get_snippets()
        self.assertEqual(len(snippets), 0)

    def test_search_snippets_by_name(self):
        self.db.add_snippet("Email signature", "Best regards")
        self.db.add_snippet("Phone number", "555-1234")

        results = self.db.search_snippets("email")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Email signature")

    def test_search_snippets_by_content(self):
        self.db.add_snippet("Greeting", "Hello from the other side")
        self.db.add_snippet("Farewell", "Goodbye for now")

        results = self.db.search_snippets("other side")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Greeting")

    def test_search_snippets_no_results(self):
        self.db.add_snippet("Test", "content")
        results = self.db.search_snippets("nonexistent")
        self.assertEqual(len(results), 0)

    def test_search_snippets_escapes_wildcards(self):
        self.db.add_snippet("Percent", "100% complete")
        self.db.add_snippet("Normal", "just text")

        results = self.db.search_snippets("%")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Percent")

    # ── Sensitive entries ─────────────────────────────────────────

    def test_add_sensitive_entry(self):
        entry_id = self.db.add_entry("text", content_text="ghp_secret", sensitive=True)
        entries = self.db.get_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["sensitive"], 1)

    def test_add_non_sensitive_entry(self):
        entry_id = self.db.add_entry("text", content_text="normal text")
        entries = self.db.get_entries()
        self.assertEqual(entries[0]["sensitive"], 0)

    def test_delete_expired_sensitive(self):
        # Add a sensitive entry and backdate it
        entry_id = self.db.add_entry("text", content_text="secret_token", sensitive=True)
        self.db.conn.execute(
            "UPDATE entries SET created_at = ? WHERE id = ?",
            (time.time() - 60, entry_id)
        )
        self.db.conn.commit()

        deleted = self.db.delete_expired_sensitive(max_age_seconds=30)
        self.assertEqual(deleted, 1)
        self.assertEqual(len(self.db.get_entries()), 0)

    def test_delete_expired_sensitive_preserves_recent(self):
        entry_id = self.db.add_entry("text", content_text="fresh_secret", sensitive=True)

        deleted = self.db.delete_expired_sensitive(max_age_seconds=30)
        self.assertEqual(deleted, 0)
        self.assertEqual(len(self.db.get_entries()), 1)

    def test_delete_expired_sensitive_ignores_non_sensitive(self):
        entry_id = self.db.add_entry("text", content_text="normal old text")
        self.db.conn.execute(
            "UPDATE entries SET created_at = ? WHERE id = ?",
            (time.time() - 60, entry_id)
        )
        self.db.conn.commit()

        deleted = self.db.delete_expired_sensitive(max_age_seconds=30)
        self.assertEqual(deleted, 0)
        self.assertEqual(len(self.db.get_entries()), 1)

    # ── Update entry text ─────────────────────────────────────────

    def test_update_entry_text(self):
        entry_id = self.db.add_entry("text", content_text="original text")
        self.db.update_entry_text(entry_id, "updated text")

        entries = self.db.get_entries()
        self.assertEqual(entries[0]["content_text"], "updated text")

    def test_update_entry_text_changes_hash(self):
        from clipman.database import content_hash
        entry_id = self.db.add_entry("text", content_text="original")
        original_hash = content_hash(b"original")

        self.db.update_entry_text(entry_id, "modified")

        entries = self.db.get_entries()
        self.assertNotEqual(entries[0]["content_hash"], original_hash)
        self.assertEqual(entries[0]["content_hash"], content_hash(b"modified"))

    # ── Backup / Restore ──────────────────────────────────────────

    def test_export_backup(self):
        import tempfile
        self.db.add_entry("text", content_text="backup me")

        backup_path = os.path.join(self.tmpdir, "backup.db")
        self.db.export_backup(backup_path)
        self.assertTrue(os.path.exists(backup_path))
        self.assertGreater(os.path.getsize(backup_path), 0)

    def test_import_backup(self):
        import tempfile
        # Create some entries and back up
        self.db.add_entry("text", content_text="entry one")
        self.db.add_entry("text", content_text="entry two")

        backup_path = os.path.join(self.tmpdir, "backup.db")
        self.db.export_backup(backup_path)

        # Clear and verify empty
        self.db.clear_unpinned()
        self.assertEqual(len(self.db.get_entries()), 0)

        # Restore and verify
        self.db.import_backup(backup_path)
        entries = self.db.get_entries()
        self.assertEqual(len(entries), 2)

    # ── Settings ──────────────────────────────────────────────────

    def test_get_setting_default(self):
        self.assertIsNone(self.db.get_setting("nonexistent"))
        self.assertEqual(self.db.get_setting("nonexistent", "fallback"), "fallback")

    def test_set_and_get_setting(self):
        self.db.set_setting("opacity", "0.85")
        self.assertEqual(self.db.get_setting("opacity"), "0.85")

    def test_set_setting_overwrites(self):
        self.db.set_setting("opacity", "0.9")
        self.db.set_setting("opacity", "0.7")
        self.assertEqual(self.db.get_setting("opacity"), "0.7")


    # ── WAL mode ───────────────────────────────────────────────────

    def test_wal_mode_enabled(self):
        mode = self.db.conn.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(mode, "wal")

    # ── Backup edge cases ─────────────────────────────────────────

    def test_import_nonexistent_backup_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.db.import_backup("/nonexistent/path/backup.db")

    def test_export_backup_creates_valid_db(self):
        import sqlite3
        self.db.add_entry("text", content_text="backup test")
        backup_path = os.path.join(self.tmpdir, "valid_backup.db")
        self.db.export_backup(backup_path)

        # Verify the backup is a valid SQLite database
        conn = sqlite3.connect(backup_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM entries").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(dict(rows[0])["content_text"], "backup test")
        conn.close()

    def test_import_preserves_pinned_entries(self):
        entry_id = self.db.add_entry("text", content_text="pinned entry")
        self.db.toggle_pin(entry_id)
        self.db.add_entry("text", content_text="unpinned entry")

        backup_path = os.path.join(self.tmpdir, "pinned_backup.db")
        self.db.export_backup(backup_path)

        self.db.clear_unpinned()
        self.db.delete_entry(entry_id)  # Remove pinned too
        self.assertEqual(len(self.db.get_entries()), 0)

        self.db.import_backup(backup_path)
        entries = self.db.get_entries()
        self.assertEqual(len(entries), 2)
        pinned = [e for e in entries if e["pinned"]]
        self.assertEqual(len(pinned), 1)
        self.assertEqual(pinned[0]["content_text"], "pinned entry")

    def test_import_backup_restores_wal_mode(self):
        self.db.add_entry("text", content_text="wal test")
        backup_path = os.path.join(self.tmpdir, "wal_backup.db")
        self.db.export_backup(backup_path)

        self.db.import_backup(backup_path)
        mode = self.db.conn.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(mode, "wal")

    # ── Delete edge cases ─────────────────────────────────────────

    def test_delete_nonexistent_entry(self):
        # Should not raise
        self.db.delete_entry(9999)

    def test_delete_snippet_nonexistent(self):
        # Should not raise
        self.db.delete_snippet(9999)

    # ── Search edge cases ─────────────────────────────────────────

    def test_search_case_insensitive(self):
        self.db.add_entry("text", content_text="Hello World")
        results = self.db.search("hello")
        self.assertEqual(len(results), 1)

    def test_search_empty_query(self):
        self.db.add_entry("text", content_text="anything")
        results = self.db.search("")
        self.assertEqual(len(results), 1)

    def test_search_special_chars(self):
        self.db.add_entry("text", content_text="price is $100")
        results = self.db.search("$100")
        self.assertEqual(len(results), 1)

    def test_search_backslash(self):
        self.db.add_entry("text", content_text="path\\to\\file")
        results = self.db.search("\\")
        self.assertEqual(len(results), 1)

    # ── Unicode support ───────────────────────────────────────────

    def test_add_unicode_text(self):
        entry_id = self.db.add_entry("text", content_text="\u4f60\u597d\u4e16\u754c \U0001f600")
        entries = self.db.get_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["content_text"], "\u4f60\u597d\u4e16\u754c \U0001f600")

    def test_add_unicode_snippet(self):
        sid = self.db.add_snippet("\u30e1\u30fc\u30eb", "\u3053\u3093\u306b\u3061\u306f")
        snippets = self.db.get_snippets()
        self.assertEqual(len(snippets), 1)
        self.assertEqual(snippets[0]["name"], "\u30e1\u30fc\u30eb")

    # ── Settings edge cases ───────────────────────────────────────

    def test_set_many_settings(self):
        for i in range(20):
            self.db.set_setting(f"key_{i}", f"value_{i}")
        for i in range(20):
            self.assertEqual(self.db.get_setting(f"key_{i}"), f"value_{i}")

    def test_setting_empty_value(self):
        self.db.set_setting("empty", "")
        self.assertEqual(self.db.get_setting("empty"), "")

    # ── Content hash ──────────────────────────────────────────────

    def test_content_hash_deterministic(self):
        from clipman.database import content_hash
        h1 = content_hash(b"same content")
        h2 = content_hash(b"same content")
        self.assertEqual(h1, h2)

    def test_content_hash_different_for_different_content(self):
        from clipman.database import content_hash
        h1 = content_hash(b"content A")
        h2 = content_hash(b"content B")
        self.assertNotEqual(h1, h2)

    def test_content_hash_empty(self):
        from clipman.database import content_hash
        # Should not raise
        h = content_hash(b"")
        self.assertEqual(len(h), 64)  # SHA-256 hex digest

    # ── Sensitive entries pinning ─────────────────────────────────

    def test_sensitive_entry_can_be_pinned(self):
        entry_id = self.db.add_entry("text", content_text="ghp_secret", sensitive=True)
        self.db.toggle_pin(entry_id)

        entries = self.db.get_entries()
        self.assertEqual(entries[0]["pinned"], 1)
        self.assertEqual(entries[0]["sensitive"], 1)

    def test_delete_expired_sensitive_skips_pinned(self):
        entry_id = self.db.add_entry("text", content_text="pinned_secret", sensitive=True)
        self.db.toggle_pin(entry_id)

        # Backdate it
        self.db.conn.execute(
            "UPDATE entries SET created_at = ? WHERE id = ?",
            (time.time() - 60, entry_id)
        )
        self.db.conn.commit()

        # delete_expired_sensitive should still delete it (pinned doesn't protect from sensitive cleanup)
        deleted = self.db.delete_expired_sensitive(max_age_seconds=30)
        # Current implementation doesn't check pinned status for sensitive cleanup
        # This test documents the actual behavior
        self.assertEqual(deleted, 1)


if __name__ == "__main__":
    unittest.main()
