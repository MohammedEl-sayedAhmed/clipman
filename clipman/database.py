import contextlib
import logging
import sqlite3
import hashlib
import os
import time
from pathlib import Path


logger = logging.getLogger(__name__)

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
    # SQLite's WAL mode creates two sidecar files (-wal, -shm) next to
    # the main DB. They contain unflushed clipboard contents — exactly
    # the data the main DB itself protects — but SQLite creates them
    # with the process umask, which is typically 0o022. Tighten any
    # that already exist; new ones are clamped by ClipboardDB.__init__
    # right after the WAL pragma fires.
    for sidecar in (
        DB_PATH,
        DB_PATH.with_name(DB_PATH.name + "-wal"),
        DB_PATH.with_name(DB_PATH.name + "-shm"),
    ):
        try:
            os.chmod(sidecar, 0o600)
        except FileNotFoundError:
            # Sidecars only exist while a connection is open. Missing
            # is fine — they'll be created with the right perms.
            pass
        except OSError:
            # Filesystem may not support chmod (vfat, some FUSE mounts).
            # Best-effort: log nothing, the main DB still protects.
            pass


def _safe_image_path(image_path: str) -> bool:
    """Return True only if image_path resolves inside IMAGES_DIR."""
    if not image_path:
        return False
    try:
        resolved = Path(image_path).resolve()
        return resolved.parent == IMAGES_DIR.resolve()
    except (OSError, ValueError):
        return False


def _remove_file(path):
    """Delete ``path``; a file that is already gone is fine."""
    with contextlib.suppress(FileNotFoundError):
        os.remove(path)


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# Columns a restored backup must carry. Older databases lacked only the
# columns _create_schema adds (entries.sensitive, snippets.use_count), so
# a table missing one of these cannot be repaired, and the backup is
# refused before anything is replaced.
_REQUIRED_COLUMNS = {
    "entries": {"id", "content_type", "content_text", "image_path",
                "content_hash", "pinned", "created_at", "accessed_at"},
    "snippets": {"id", "name", "content_text", "created_at"},
    "settings": {"key", "value"},
}

# Safety copies taken before a restore: clipman.db.<time>.bak, never
# overwritten. Only the newest few are kept, because each one holds the
# whole history, masked sensitive clips included.
SAFETY_COPY_KEEP = 3

# The range Preferences offers for the history size.
MAX_ENTRIES_RANGE = (50, 5000)


def _check_backup(conn):
    """Raise ValueError unless ``conn`` holds a backup this app can use."""
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("Invalid backup: the file is damaged")
    objects = conn.execute("SELECT type, name, sql FROM sqlite_master").fetchall()
    # Triggers and views could run arbitrary SQL on later writes.
    dangerous = sorted(name for kind, name, _sql in objects
                       if kind in ("trigger", "view"))
    if dangerous:
        raise ValueError(
            "Invalid backup: contains disallowed objects: " + ", ".join(dangerous)
        )
    tables = {name: sql or "" for kind, name, sql in objects if kind == "table"}
    if "entries" not in tables:
        raise ValueError("Invalid backup: missing 'entries' table")
    for table, required in _REQUIRED_COLUMNS.items():
        if table not in tables:
            continue
        if tables[table].lstrip().upper().startswith("CREATE VIRTUAL"):
            raise ValueError(f"Invalid backup: '{table}' is not a plain table")
        have = {row[0] for row in conn.execute(
            "SELECT name FROM pragma_table_info(?)", (table,))}
        missing = required - have
        if missing:
            raise ValueError(
                f"Invalid backup: '{table}' lacks {', '.join(sorted(missing))}"
            )


def _sanitize_image_paths(conn):
    """Null out image paths that point outside IMAGES_DIR."""
    rows = conn.execute(
        "SELECT id, image_path FROM entries WHERE image_path IS NOT NULL"
    ).fetchall()
    for row_id, image_path in rows:
        if not _safe_image_path(image_path):
            conn.execute(
                "UPDATE entries SET image_path = NULL WHERE id = ?", (row_id,)
            )


def _remove_sidecars(db_path):
    for suffix in ("-wal", "-shm", "-journal"):
        _remove_file(f"{db_path}{suffix}")


def _prepare_restore(path):
    """Copy the backup at ``path`` next to the live database, then check,
    migrate and clean the copy. Returns the copy's path. The live database
    is never touched here. Raises ValueError when the backup is unusable.
    """
    import shutil
    try:
        if DB_PATH.exists() and os.path.samefile(path, DB_PATH):
            raise ValueError("That file is the live history itself; "
                             "choose a backup")
    except OSError as exc:
        raise ValueError(f"Cannot read the backup: {exc}") from exc
    _ensure_dirs()
    tmp = DB_PATH.with_name(DB_PATH.name + ".restoring")
    _remove_file(tmp)
    _remove_sidecars(tmp)
    ready = False
    try:
        # Created 0600 before any data lands in it, like the live database.
        os.close(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600))
        shutil.copyfile(path, tmp)
        conn = sqlite3.connect(str(tmp))
        try:
            # A backup is untrusted input: its schema may not call SQL
            # functions.
            conn.execute("PRAGMA trusted_schema=OFF")
            _check_backup(conn)
            _create_schema(conn)
            _sanitize_image_paths(conn)
            conn.commit()
        finally:
            conn.close()
        ready = True
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"Not a valid database: {exc}") from exc
    finally:
        if not ready:
            _remove_file(tmp)
            _remove_sidecars(tmp)
    return tmp


def _replace_live_db(tmp):
    """Swap the prepared copy in as the live database, in one rename.

    The caller has closed every connection to the live file. Sidecars
    left behind belong to the old file and must never be applied to the
    new one.
    """
    _remove_sidecars(DB_PATH)
    os.replace(tmp, DB_PATH)
    _remove_sidecars(tmp)


def restore_backup_file(path):
    """Replace the history on disk with the backup at ``path``, with no
    connection open (the database-error screen, where the live file may
    not even open). Raises ValueError when the backup is unusable."""
    _replace_live_db(_prepare_restore(path))


def _reap_orphan_images(conn):
    """Delete image files that no entry points at, so the screenshots of
    a replaced history do not stay on disk forever."""
    try:
        names = set(os.listdir(IMAGES_DIR))
    except OSError:
        return
    used = {os.path.basename(row[0]) for row in conn.execute(
        "SELECT image_path FROM entries WHERE image_path IS NOT NULL")}
    for name in names - used:
        path = IMAGES_DIR / name
        if path.is_file() and not path.is_symlink():
            _remove_file(path)


def prune_safety_copies(keep=SAFETY_COPY_KEEP, spare=None):
    """Delete all but the newest ``keep`` safety copies, never ``spare``
    (the file a restore just read)."""
    copies = sorted(
        DB_PATH.parent.glob(DB_PATH.name + ".*.bak"),
        key=lambda p: (p.stat().st_mtime, p.name),
    )
    spared = Path(spare).resolve() if spare else None
    for old in copies[:max(len(copies) - keep, 0)]:
        if spared is None or old.resolve() != spared:
            _remove_file(old)


def _create_schema(conn):
    """Create any missing table or index, and add columns that older
    databases lack. Safe to run on every open, and on a restored copy."""
    conn.execute("""
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
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_accessed_at ON entries(accessed_at DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_content_hash ON entries(content_hash)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snippets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            content_text TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    # Migration: add sensitive column if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(entries)")]
    if "sensitive" not in cols:
        conn.execute(
            "ALTER TABLE entries ADD COLUMN sensitive INTEGER NOT NULL DEFAULT 0"
        )
    # Migration: snippet paste counter ("Snippet · used N×" row meta)
    scols = [r[1] for r in conn.execute("PRAGMA table_info(snippets)")]
    if "use_count" not in scols:
        conn.execute(
            "ALTER TABLE snippets ADD COLUMN use_count INTEGER NOT NULL DEFAULT 0"
        )
    conn.commit()


class ClipboardDB:
    def __init__(self):
        _ensure_dirs()
        self._open()
        self._create_table()

    def _open(self):
        # Safe: all DB access happens on the GLib main thread (D-Bus callbacks
        # and GTK signal handlers both run on the main loop).
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        # Re-run the sidecar chmod now that WAL is on — this is the
        # first moment -wal/-shm are guaranteed to exist with our
        # process as the creator.
        _ensure_dirs()

    def _create_table(self):
        _create_schema(self.conn)

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
            _remove_file(row["image_path"])
        self.conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        self.conn.commit()

    def clear_unpinned(self):
        rows = self.conn.execute(
            "SELECT image_path FROM entries WHERE pinned = 0 AND image_path IS NOT NULL"
        ).fetchall()
        for row in rows:
            if _safe_image_path(row["image_path"]):
                _remove_file(row["image_path"])
        self.conn.execute("DELETE FROM entries WHERE pinned = 0")
        self.conn.commit()

    def enforce_max_entries(self):
        # Older builds stored the value as a float string; never let a
        # bad setting break every copy.
        try:
            max_entries = int(float(self.get_setting("max_entries", str(MAX_ENTRIES))))
        except (TypeError, ValueError, OverflowError):
            max_entries = MAX_ENTRIES
        # Keep to the range Preferences offers: a restored or hand-edited
        # value of 0 or -1 would delete every new clip.
        low, high = MAX_ENTRIES_RANGE
        max_entries = min(max(max_entries, low), high)
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
                _remove_file(row["image_path"])
            self.conn.execute("DELETE FROM entries WHERE id = ?", (row["id"],))
        self.conn.commit()

    def delete_expired_sensitive(self, max_age_seconds: int = 30) -> int:
        # The Privacy pane can switch the auto-clear off; rows stay masked.
        if self.get_setting("sensitive_autoclear", "true") != "true":
            return 0
        cutoff = time.time() - max_age_seconds
        rows = self.conn.execute(
            """SELECT id, image_path FROM entries
               WHERE sensitive = 1 AND created_at < ?""",
            (cutoff,)
        ).fetchall()
        for row in rows:
            if row["image_path"] and _safe_image_path(row["image_path"]):
                _remove_file(row["image_path"])
            self.conn.execute("DELETE FROM entries WHERE id = ?", (row["id"],))
        if rows:
            self.conn.commit()
        return len(rows)

    def get_latest_text(self) -> str:
        """Return the most recently used text clip, pinned or not."""
        row = self.conn.execute(
            """SELECT content_text FROM entries
               WHERE content_type = 'text' AND content_text IS NOT NULL
               ORDER BY accessed_at DESC LIMIT 1"""
        ).fetchone()
        return row["content_text"] if row else ""

    def export_backup(self, path: str):
        import shutil
        # The destination is truncated below, so it must never be the live
        # database or one of its sidecars.
        target = Path(path).resolve()
        live = DB_PATH.resolve()
        if target in {live} | {Path(f"{live}{s}") for s in ("-wal", "-shm", "-journal")}:
            raise ValueError("Choose another file: that one is the live history")
        self.conn.commit()
        self.conn.execute("PRAGMA wal_checkpoint(FULL)")
        # Create (or clamp) the destination to 0o600 before any history
        # lands in it: the user's umask (typically 0o022) would otherwise
        # leave the copy readable by others while it is being written.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.fchmod(fd, 0o600)
        except OSError:
            # A filesystem without modes (vfat, some FUSE mounts) keeps
            # its own; the export still works.
            logger.debug("chmod 0o600 failed on exported backup %s", path,
                         exc_info=True)
        finally:
            os.close(fd)
        shutil.copyfile(str(DB_PATH), path)

    def write_safety_copy(self) -> str:
        """Save the current history as ``clipman.db.<time>.bak`` next to
        the live database, never over an existing file, and return its
        path. Taken before a restore, so a bad restore can be undone."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = DB_PATH.with_name(f"{DB_PATH.name}.{stamp}.bak")
        n = 1
        while path.exists():
            n += 1
            path = DB_PATH.with_name(f"{DB_PATH.name}.{stamp}-{n}.bak")
        self.export_backup(str(path))
        return str(path)

    def import_backup(self, path: str):
        """Replace the whole history with the backup at ``path``.

        The backup is checked, migrated and cleaned in a copy next to the
        live database first, and only a copy that passed every step
        replaces it, in one rename. Any failure leaves the history, and
        this connection, as they were.
        """
        tmp = _prepare_restore(path)
        self.conn.commit()
        self.conn.close()
        try:
            _replace_live_db(tmp)
        finally:
            # Reopen whichever file is live now: the restored one, or the
            # old one if the rename failed.
            self._open()
            _remove_file(tmp)
        _reap_orphan_images(self.conn)

    # --- Snippets ---

    def add_snippet(self, name: str, content_text: str) -> int:
        cursor = self.conn.execute(
            "INSERT INTO snippets (name, content_text, created_at) VALUES (?, ?, ?)",
            (name, content_text, time.time())
        )
        self.conn.commit()
        return cursor.lastrowid

    def increment_snippet_use(self, snippet_id: int):
        """Bump the paste counter shown in the snippet row meta."""
        self.conn.execute(
            "UPDATE snippets SET use_count = use_count + 1 WHERE id = ?",
            (snippet_id,),
        )
        self.conn.commit()

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
