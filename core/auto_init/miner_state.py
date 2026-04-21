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
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


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


# ── Standalone helpers ──────────────────────────────────────────────────────


def compute_content_hash(content: str) -> str:
    """SHA-256 of UTF-8 encoded content, first 16 hex chars. Matches metadata."""
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()[:16]


def resolve_state_path(palace_dir: str | None) -> Path | None:
    """Return the expected state file path for a palace dir, or None."""
    if not palace_dir:
        return None
    return Path(palace_dir) / "mined_files.sqlite3"
