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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ClipboardDB:
    def __init__(self):
        _ensure_dirs()
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

    def get_entries(self, limit: int = 50, offset: int = 0):
        rows = self.conn.execute(
            """SELECT * FROM entries
               ORDER BY pinned DESC, accessed_at DESC
               LIMIT ? OFFSET ?""",
            (limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, limit: int = 50):
        rows = self.conn.execute(
            """SELECT * FROM entries
               WHERE content_type = 'text' AND content_text LIKE ?
               ORDER BY pinned DESC, accessed_at DESC
               LIMIT ?""",
            (f"%{query}%", limit)
        ).fetchall()
        return [dict(r) for r in rows]

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
        count = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM entries WHERE pinned = 0"
        ).fetchone()["cnt"]
        if count <= MAX_ENTRIES:
            return
        excess = count - MAX_ENTRIES
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

    def close(self):
        self.conn.close()
