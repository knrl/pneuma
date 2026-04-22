"""
Mining state tracker — records which files have been mined so we can
incrementally re-mine only the changed ones.

State lives in <palace_dir>/mined_files.sqlite3, separate from the
actual palace data.

Schema:
  mined_files (
    rel_path      PRIMARY KEY,
    content_hash  TEXT,
    mtime         REAL,
    entry_ids     TEXT     -- JSON array of palace drawer IDs
    mined_at      REAL
  )

Typical flow on incremental re-mine:
  1. For each file currently on disk:
     - if hash matches DB row → skip (no change)
     - if hash differs         → delete old entries via entry_ids, re-mine,
                                 update DB
  2. After walking: find DB rows whose rel_path is no longer on disk,
     delete their entries, drop the DB row.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

MINE_LOCK_STALE_AFTER = 3600  # seconds — treat lock as stale after 1 hour


_SCHEMA = """
CREATE TABLE IF NOT EXISTS mined_files (
    rel_path      TEXT PRIMARY KEY,
    content_hash  TEXT NOT NULL,
    mtime         REAL NOT NULL,
    entry_ids     TEXT NOT NULL,
    mined_at      REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mined_files_hash ON mined_files(content_hash);
"""


@dataclass
class FileRecord:
    rel_path: str
    content_hash: str
    mtime: float
    entry_ids: list[str]
    mined_at: float


class MiningState:
    """Opens / manages the mined_files SQLite DB for a palace."""

    def __init__(self, palace_dir: str):
        self.db_path = Path(palace_dir) / "mined_files.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── Read ────────────────────────────────────────────────────────────────

    def get(self, rel_path: str) -> FileRecord | None:
        row = self._conn.execute(
            "SELECT rel_path, content_hash, mtime, entry_ids, mined_at "
            "FROM mined_files WHERE rel_path = ?",
            (rel_path,),
        ).fetchone()
        if not row:
            return None
        return FileRecord(
            rel_path=row[0],
            content_hash=row[1],
            mtime=row[2],
            entry_ids=json.loads(row[3]),
            mined_at=row[4],
        )

    def all_paths(self) -> set[str]:
        rows = self._conn.execute("SELECT rel_path FROM mined_files").fetchall()
        return {r[0] for r in rows}

    def all_records(self) -> list[FileRecord]:
        rows = self._conn.execute(
            "SELECT rel_path, content_hash, mtime, entry_ids, mined_at "
            "FROM mined_files"
        ).fetchall()
        return [
            FileRecord(r[0], r[1], r[2], json.loads(r[3]), r[4]) for r in rows
        ]

    # ── Write ───────────────────────────────────────────────────────────────

    def upsert(self, rel_path: str, content_hash: str, mtime: float, entry_ids: list[str]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO mined_files "
            "(rel_path, content_hash, mtime, entry_ids, mined_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (rel_path, content_hash, mtime, json.dumps(entry_ids), time.time()),
        )
        self._conn.commit()

    def delete(self, rel_path: str) -> None:
        self._conn.execute("DELETE FROM mined_files WHERE rel_path = ?", (rel_path,))
        self._conn.commit()

    # ── Helpers ─────────────────────────────────────────────────────────────

    def has_changed(self, rel_path: str, content_hash: str) -> bool:
        """Return True if this file's hash differs from the stored one (or is new)."""
        rec = self.get(rel_path)
        if rec is None:
            return True
        return rec.content_hash != content_hash


# ── Cross-process mine lock ──────────────────────────────────────────────────


class MineProcessLock:
    """Cross-process advisory lock preventing concurrent incremental mines.

    Uses ``os.open(O_EXCL)`` for atomic creation on local filesystems so that
    only one ``mine_project`` call (CLI *or* background auto-mine) can run at
    a time per palace directory.  Locks older than ``MINE_LOCK_STALE_AFTER``
    seconds are treated as stale and silently cleared on the next attempt
    (handles crashed processes that never released the lock).
    """

    def __init__(self, palace_dir: str | Path) -> None:
        self._path = Path(palace_dir) / "mine.lock"
        self._held = False

    def try_acquire(self) -> bool:
        """Return True if the lock was acquired, False if another mine is active."""
        if self._path.exists():
            try:
                age = time.time() - self._path.stat().st_mtime
                if age >= MINE_LOCK_STALE_AFTER:
                    self._path.unlink(missing_ok=True)
            except OSError:
                pass

        try:
            fd = os.open(str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            self._held = True
            return True
        except FileExistsError:
            return False
        except OSError:
            # Permission error or unsupported filesystem — degrade gracefully
            # rather than blocking a mine that may be the only way to recover.
            return True

    def release(self) -> None:
        if self._held:
            try:
                self._path.unlink()
            except Exception:
                pass
            self._held = False

    def __enter__(self) -> "MineProcessLock":
        return self

    def __exit__(self, *_) -> None:
        self.release()


# ── Standalone helpers ──────────────────────────────────────────────────────


def compute_content_hash(content: str) -> str:
    """SHA-256 of UTF-8 encoded content, first 16 hex chars. Matches metadata."""
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()[:16]


def resolve_state_path(palace_dir: str | None) -> Path | None:
    """Return the expected state file path for a palace dir, or None."""
    if not palace_dir:
        return None
    return Path(palace_dir) / "mined_files.sqlite3"
