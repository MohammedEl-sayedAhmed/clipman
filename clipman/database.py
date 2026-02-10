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


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ClipboardDB:
    def __init__(self):
        _ensure_dirs()
        # Safe: all DB access happens on the GLib main thread (D-Bus callbacks
        # and GTK signal handlers both run on the main loop).
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
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
        self.conn.commit()

    def add_entry(self, content_type: str, content_text: str = None,
                  image_data: bytes = None) -> int:
        now = time.time()

        if content_type == "text" and content_text:
            h = content_hash(content_text.encode("utf-8"))
            image_path = None
        elif content_type == "image" and image_data:
            h = content_hash(image_data)
            image_path = str(IMAGES_DIR / f"{h}.png")
            with open(image_path, "wb") as f:
                f.write(image_data)
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
               (content_type, content_text, image_path, content_hash, pinned, created_at, accessed_at)
               VALUES (?, ?, ?, ?, 0, ?, ?)""",
            (content_type, content_text, image_path, h, now, now)
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
        if row and row["image_path"]:
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
            if row["image_path"]:
                try:
                    os.remove(row["image_path"])
                except FileNotFoundError:
                    pass
            self.conn.execute("DELETE FROM entries WHERE id = ?", (row["id"],))
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
