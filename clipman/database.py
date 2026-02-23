import sqlite3
import hashlib
import os
import time
from pathlib import Path


DATA_DIR = Path.home() / ".local" / "share" / "clipman"
IMAGES_DIR = DATA_DIR / "images"
DB_PATH = DATA_DIR / "clipman.db"
MAX_ENTRIES = 500


def _ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Enforce permissions even if dirs already existed with wrong perms
    os.chmod(DATA_DIR, 0o700)
    os.chmod(IMAGES_DIR, 0o700)


def _safe_image_path(image_path: str) -> bool:
    """Return True only if image_path resolves inside IMAGES_DIR."""
    if not image_path:
        return False
    try:
        resolved = Path(image_path).resolve()
        return resolved.parent == IMAGES_DIR.resolve()
    except (OSError, ValueError):
        return False


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ClipboardDB:
    def __init__(self):
        _ensure_dirs()
        # Safe: all DB access happens on the GLib main thread (D-Bus callbacks
        # and GTK signal handlers both run on the main loop).
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_table()

    def _create_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_type TEXT NOT NULL,
                content_text TEXT,
                image_path TEXT,
                content_hash TEXT NOT NULL UNIQUE,
                pinned INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                accessed_at REAL NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_accessed_at ON entries(accessed_at DESC)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_content_hash ON entries(content_hash)
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS snippets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                content_text TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        # Migration: add sensitive column if missing
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(entries)")]
        if "sensitive" not in cols:
            self.conn.execute(
                "ALTER TABLE entries ADD COLUMN sensitive INTEGER NOT NULL DEFAULT 0"
            )
        self.conn.commit()

    def add_entry(self, content_type: str, content_text: str = None,
                  image_data: bytes = None, sensitive: bool = False) -> int:
        now = time.time()

        if content_type == "text" and content_text:
            h = content_hash(content_text.encode("utf-8"))
            image_path = None
        elif content_type == "image" and image_data:
            # Validate image magic bytes (PNG, JPEG, GIF, BMP, WebP)
            _MAGIC = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"BM", b"RIFF")
            if not any(image_data[:8].startswith(m) for m in _MAGIC):
                return -1
            h = content_hash(image_data)
            image_path = str(IMAGES_DIR / f"{h}.png")
            fd = os.open(image_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, image_data)
            finally:
                os.close(fd)
        else:
            return -1

        existing = self.conn.execute(
            "SELECT id FROM entries WHERE content_hash = ?", (h,)
        ).fetchone()

        if existing:
            self.conn.execute(
                "UPDATE entries SET accessed_at = ? WHERE id = ?",
                (now, existing["id"])
            )
            self.conn.commit()
            return existing["id"]

        cursor = self.conn.execute(
            """INSERT INTO entries
               (content_type, content_text, image_path, content_hash, pinned,
                created_at, accessed_at, sensitive)
               VALUES (?, ?, ?, ?, 0, ?, ?, ?)""",
            (content_type, content_text, image_path, h, now, now,
             1 if sensitive else 0)
        )
        self.conn.commit()
        self.enforce_max_entries()
        return cursor.lastrowid

    def get_entries(self, limit: int = 50, offset: int = 0,
                    content_type: str = None):
        if content_type:
            rows = self.conn.execute(
                """SELECT * FROM entries WHERE content_type = ?
                   ORDER BY pinned DESC, accessed_at DESC
                   LIMIT ? OFFSET ?""",
                (content_type, limit, offset)
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM entries
                   ORDER BY pinned DESC, accessed_at DESC
                   LIMIT ? OFFSET ?""",
                (limit, offset)
            ).fetchall()
        return [dict(r) for r in rows]

    def count_entries(self, content_type: str = None) -> int:
        if content_type:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM entries WHERE content_type = ?",
                (content_type,)
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM entries"
            ).fetchone()
        return row["cnt"]

    def search(self, query: str, limit: int = 50):
        # Escape LIKE wildcards so user input is treated literally
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = self.conn.execute(
            """SELECT * FROM entries
               WHERE content_type = 'text' AND content_text LIKE ? ESCAPE '\\'
               ORDER BY pinned DESC, accessed_at DESC
               LIMIT ?""",
            (f"%{escaped}%", limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def update_accessed(self, entry_id: int):
        self.conn.execute(
            "UPDATE entries SET accessed_at = ? WHERE id = ?",
            (time.time(), entry_id)
        )
        self.conn.commit()

    def toggle_pin(self, entry_id: int) -> bool:
        row = self.conn.execute(
            "SELECT pinned FROM entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if not row:
            return False
        new_val = 0 if row["pinned"] else 1
        self.conn.execute(
            "UPDATE entries SET pinned = ? WHERE id = ?", (new_val, entry_id)
        )
        self.conn.commit()
        return bool(new_val)

    def delete_entry(self, entry_id: int):
        row = self.conn.execute(
            "SELECT image_path FROM entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if row and row["image_path"] and _safe_image_path(row["image_path"]):
            try:
                os.remove(row["image_path"])
            except FileNotFoundError:
                pass
        self.conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        self.conn.commit()

    def clear_unpinned(self):
        rows = self.conn.execute(
            "SELECT image_path FROM entries WHERE pinned = 0 AND image_path IS NOT NULL"
        ).fetchall()
        for row in rows:
            if _safe_image_path(row["image_path"]):
                try:
                    os.remove(row["image_path"])
                except FileNotFoundError:
                    pass
        self.conn.execute("DELETE FROM entries WHERE pinned = 0")
        self.conn.commit()

    def enforce_max_entries(self):
        max_entries = int(self.get_setting("max_entries", str(MAX_ENTRIES)))
        count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM entries WHERE pinned = 0"
        ).fetchone()["cnt"]
        if count <= max_entries:
            return
        excess = count - max_entries
        rows = self.conn.execute(
            """SELECT id, image_path FROM entries
               WHERE pinned = 0
               ORDER BY accessed_at ASC
               LIMIT ?""",
            (excess,)
        ).fetchall()
        for row in rows:
            if row["image_path"] and _safe_image_path(row["image_path"]):
                try:
                    os.remove(row["image_path"])
                except FileNotFoundError:
                    pass
            self.conn.execute("DELETE FROM entries WHERE id = ?", (row["id"],))
        self.conn.commit()

    def delete_expired_sensitive(self, max_age_seconds: int = 30) -> int:
        cutoff = time.time() - max_age_seconds
        rows = self.conn.execute(
            """SELECT id, image_path FROM entries
               WHERE sensitive = 1 AND created_at < ?""",
            (cutoff,)
        ).fetchall()
        for row in rows:
            if row["image_path"] and _safe_image_path(row["image_path"]):
                try:
                    os.remove(row["image_path"])
                except FileNotFoundError:
                    pass
            self.conn.execute("DELETE FROM entries WHERE id = ?", (row["id"],))
        if rows:
            self.conn.commit()
        return len(rows)

    def update_entry_text(self, entry_id: int, new_text: str):
        h = content_hash(new_text.encode("utf-8"))
        self.conn.execute(
            """UPDATE entries SET content_text = ?, content_hash = ?,
               accessed_at = ? WHERE id = ?""",
            (new_text, h, time.time(), entry_id)
        )
        self.conn.commit()

    def export_backup(self, path: str):
        import shutil
        self.conn.commit()
        self.conn.execute("PRAGMA wal_checkpoint(FULL)")
        shutil.copy2(str(DB_PATH), path)

    def import_backup(self, path: str):
        import shutil
        from urllib.parse import quote
        # Validate the backup is a real SQLite database with expected tables
        try:
            # URL-encode path to prevent SQLite URI parameter injection
            # (a filename containing '?' could inject mode=rw, etc.)
            safe_uri = "file:" + quote(str(path), safe="/") + "?mode=ro"
            test_conn = sqlite3.connect(safe_uri, uri=True)
            schema = {(r[0], r[1]) for r in test_conn.execute(
                "SELECT type, name FROM sqlite_master"
            ).fetchall()}
            test_conn.close()
        except sqlite3.Error as e:
            raise ValueError(f"Not a valid database: {e}")
        tables = {name for typ, name in schema if typ == "table"}
        if "entries" not in tables:
            raise ValueError("Invalid backup: missing 'entries' table")
        # Reject backups containing triggers or views (could execute
        # arbitrary SQL on INSERT/UPDATE/DELETE after import)
        dangerous = {name for typ, name in schema
                     if typ in ("trigger", "view")}
        if dangerous:
            raise ValueError(
                f"Invalid backup: contains disallowed objects: "
                f"{', '.join(sorted(dangerous))}"
            )
        self.conn.close()
        shutil.copy2(path, str(DB_PATH))
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_table()
        # Sanitize any image_path values that point outside IMAGES_DIR
        bad = self.conn.execute(
            "SELECT id, image_path FROM entries WHERE image_path IS NOT NULL"
        ).fetchall()
        for row in bad:
            if not _safe_image_path(row["image_path"]):
                self.conn.execute(
                    "UPDATE entries SET image_path = NULL WHERE id = ?",
                    (row["id"],)
                )
        self.conn.commit()

    # --- Snippets ---

    def add_snippet(self, name: str, content_text: str) -> int:
        cursor = self.conn.execute(
            "INSERT INTO snippets (name, content_text, created_at) VALUES (?, ?, ?)",
            (name, content_text, time.time())
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_snippets(self):
        rows = self.conn.execute(
            "SELECT * FROM snippets ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_snippet(self, snippet_id: int, name: str, content_text: str):
        self.conn.execute(
            "UPDATE snippets SET name = ?, content_text = ? WHERE id = ?",
            (name, content_text, snippet_id)
        )
        self.conn.commit()

    def delete_snippet(self, snippet_id: int):
        self.conn.execute("DELETE FROM snippets WHERE id = ?", (snippet_id,))
        self.conn.commit()

    def search_snippets(self, query: str, limit: int = 50):
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = self.conn.execute(
            """SELECT * FROM snippets
               WHERE name LIKE ? ESCAPE '\\' OR content_text LIKE ? ESCAPE '\\'
               ORDER BY created_at DESC LIMIT ?""",
            (f"%{escaped}%", f"%{escaped}%", limit)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Settings ---

    def get_setting(self, key: str, default: str = None) -> str:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
