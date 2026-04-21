"""
Codebase miner — walks a project directory and stores source files into
the project's palace wing, using directory-mirroring room layout.

Rooms come from top-level directories of the project (see templates.py).
Files at project root go to the `general` room.

Called by auto_initialize() after the palace structure is provisioned,
and on demand via the mine_codebase MCP tool.
"""

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from core.auto_init.templates import slugify_room
from core.auto_init.miner_config import MinerConfig, load_config
from core.auto_init.miner_chunker import get_chunker, Chunk
from core.auto_init.miner_summary import build_summary
from core.auto_init.miner_state import MiningState, compute_content_hash

# ── Constants ────────────────────────────────────────────────────────────────
# These are fallbacks when no MinerConfig is passed. MinerConfig values
# override them.

CHUNK_SIZE = 1500       # chars per stored chunk (char-based fallback)
CHUNK_OVERLAP = 150     # overlap between consecutive chunks
MAX_FILE_SIZE = 100_000 # bytes — skip files larger than this
MAX_FILES = 5_000       # safety ceiling

_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".tox", "dist", "build", ".mypy_cache", ".pytest_cache", ".next",
    "target", ".idea", ".vs", "obj", "out", "coverage", ".coverage",
    "vendor", "third_party", "thirdparty", "external",
}

_BINARY_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib", ".bin", ".obj", ".o", ".a", ".lib",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".webp", ".tiff",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flac",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".pyc", ".pyo", ".class", ".jar", ".war", ".ear",
    ".db", ".sqlite", ".sqlite3",
    ".wasm", ".map",
    ".lock",
}

_MINE_EXTENSIONS = {
    # Code
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cs", ".go",
    ".rs", ".rb", ".php", ".swift", ".kt", ".cpp", ".c", ".h",
    ".hpp", ".cc", ".cxx", ".m", ".scala", ".clj", ".ex", ".exs",
    ".lua", ".r", ".jl", ".zig", ".v", ".nim",
    # Shell / scripts
    ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
    # Config / infra
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env",
    ".dockerfile", ".tf", ".hcl",
    # Data schemas
    ".sql", ".graphql", ".proto", ".thrift", ".avsc",
    # Docs
    ".md", ".rst", ".txt", ".adoc",
}

_SKIP_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.lock", "poetry.lock", "Gemfile.lock",
    "composer.lock", ".DS_Store", "Thumbs.db",
}

# Language detection from extension
_LANG_FROM_EXT: dict[str, str] = {
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".java": "java", ".kt": "kotlin", ".scala": "scala",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".c": "c", ".h": "c",
    ".m": "objective-c",
    ".clj": "clojure",
    ".ex": "elixir", ".exs": "elixir",
    ".lua": "lua",
    ".r": "r",
    ".jl": "julia",
    ".zig": "zig",
    ".v": "vlang",
    ".nim": "nim",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".ps1": "powershell",
    ".bat": "batch", ".cmd": "batch",
    ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini", ".cfg": "ini", ".conf": "ini",
    ".sql": "sql",
    ".graphql": "graphql",
    ".proto": "protobuf",
    ".thrift": "thrift",
    ".md": "markdown", ".rst": "rst", ".adoc": "asciidoc",
    ".txt": "text",
    ".tf": "terraform", ".hcl": "hcl",
    ".dockerfile": "dockerfile",
}


# ── Kind classification ─────────────────────────────────────────────────────

def _classify_kind(rel_path: str, ext: str) -> str:
    """Return one of: code | test | config | doc | script."""
    p = "/" + rel_path.lower().replace("\\", "/")

    if ext in {".md", ".rst", ".txt", ".adoc"}:
        return "doc"
    if ext in {".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env",
               ".tf", ".hcl", ".dockerfile"}:
        return "config"
    if ext in {".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd"}:
        return "script"
    if any(x in p for x in ["/test/", "/tests/", "_test.", ".test.", "/spec/", "_spec.", ".spec."]):
        return "test"
    return "code"


# ── Routing ──────────────────────────────────────────────────────────────────

def _scan_large_dirs(
    root: Path,
    top_dirs: list[str],
    threshold: int,
) -> dict[str, list[str]]:
    """
    Return {top_dir: [subdir, ...]} for top-level dirs that have at least
    *threshold* immediate subdirectories (excluding _SKIP_DIRS).
    Called once before the file walk so _route_by_path can use depth-2 rooms.
    """
    result: dict[str, list[str]] = {}
    for top in top_dirs:
        top_path = root / top
        if not top_path.is_dir():
            continue
        subdirs = sorted(
            d.name for d in top_path.iterdir()
            if d.is_dir() and d.name not in _SKIP_DIRS
        )
        if len(subdirs) >= threshold:
            result[top] = subdirs
    return result


def _route_by_path(
    rel_path: str,
    depth2_dirs: dict[str, list[str]] | None = None,
) -> tuple[str, str]:
    """
    Return (wing, room) for a file. Wing is always "code".

    Room assignment priority:
      1. Canonical dir name (tests/, docs/) → stable room name
      2. Top-level dir is large (in depth2_dirs) and file is in a subdir
         → "{top}-{subdir}"
      3. Top-level dir is large and file sits directly in it → "{top}"
      4. Default → slugified top-level dir name
    """
    from core.auto_init.templates import canonical_room, slugify_room as _slug

    parts = Path(rel_path).parts
    if len(parts) <= 1:
        return ("code", "general")

    top = parts[0]

    canon = canonical_room(top)
    if canon:
        return ("code", canon)

    if depth2_dirs and top in depth2_dirs:
        if len(parts) >= 3:
            sub = parts[1]
            return ("code", _slug(f"{top}-{sub}"))
        return ("code", _slug(top))

    return ("code", _slug(top))


# ── Chunking (char-based for now; tree-sitter comes in Phase 2) ──────────────

def _chunks(
    rel_path: str,
    content: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """
    Back-compat wrapper around CharChunker for tests that still use this.
    New code should prefer get_chunker() from miner_chunker.
    """
    from core.auto_init.miner_chunker import CharChunker
    return [c.text for c in CharChunker(chunk_size, chunk_overlap).chunk(rel_path, content)]


# ── Metadata ─────────────────────────────────────────────────────────────────

def _build_metadata(
    rel_path: str,
    ext: str,
    content: str,
    mtime: float,
    size: int,
    chunk_idx: int,
    total_chunks: int,
    top_level_dir: str,
    symbol: str = "",
    chunk_kind: str = "char",
) -> dict:
    """Build the metadata dict attached to every chunk entry."""
    content_hash = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()[:16]
    meta = {
        "source_file": rel_path,
        "language": _LANG_FROM_EXT.get(ext, "unknown"),
        "kind": _classify_kind(rel_path, ext),
        "top_level_dir": top_level_dir,
        "mtime": mtime,
        "size": size,
        "content_hash": content_hash,
        "chunk_index": chunk_idx,
        "total_chunks": total_chunks,
        "chunk_kind": chunk_kind,
    }
    if symbol:
        meta["symbol"] = symbol
    return meta


# ── Result ───────────────────────────────────────────────────────────────────

@dataclass
class MineResult:
    files_processed: int = 0
    chunks_stored: int = 0
    summaries_stored: int = 0
    files_skipped: int = 0
    files_unchanged: int = 0   # incremental mode: files whose hash matched, skipped re-embedding
    files_removed: int = 0     # incremental mode: entries deleted for files no longer on disk
    errors: list[str] = field(default_factory=list)
    # Dry-run extras — populated when dry_run=True. Empty otherwise.
    would_route: dict[str, int] = field(default_factory=dict)  # "wing/room" → count
    skip_reasons: dict[str, int] = field(default_factory=dict)


# ── Per-file parallel task ───────────────────────────────────────────────────

@dataclass
class _FileTask:
    file_path: Path
    rel_path: str
    ext: str
    wing: str
    room: str
    content: str
    mtime: float
    size: int
    top_level_dir: str


@dataclass
class _FileResult:
    rel_path: str
    content_hash: str
    mtime: float
    entry_ids: list[str]
    chunks_stored: int
    summaries_stored: int
    errors: list[str]
    # Dry-run only
    dry_route_key: str = ""
    dry_route_count: int = 0


def _mine_file_task(task: _FileTask, config: "MinerConfig", dry_run: bool) -> _FileResult:
    """
    Process one file: chunk it, build summary, store entries.
    Runs in a worker thread — must not touch shared mutable state.
    """
    from core.palace import add_entry as _add_entry

    ext = task.ext
    chunker = get_chunker(ext, chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap)
    chunk_objs: list[Chunk] = chunker.chunk(task.rel_path, task.content)
    total = len(chunk_objs)

    lang = _LANG_FROM_EXT.get(ext, "unknown")
    file_kind = _classify_kind(task.rel_path, ext)
    summary = build_summary(
        rel_path=task.rel_path,
        content=task.content,
        ext=ext,
        language=lang,
        kind=file_kind,
        top_level_dir=task.top_level_dir,
        size=task.size,
        num_chunks=total,
    )

    res = _FileResult(
        rel_path=task.rel_path,
        content_hash=compute_content_hash(task.content),
        mtime=task.mtime,
        entry_ids=[],
        chunks_stored=0,
        summaries_stored=0,
        errors=[],
    )

    if dry_run:
        res.dry_route_key = f"{task.wing}/{task.room}"
        res.dry_route_count = total + 1  # chunks + summary
        res.chunks_stored = total
        res.summaries_stored = 1
        return res

    # Store chunks and summary
    for idx, chunk in enumerate(chunk_objs, start=1):
        metadata = _build_metadata(
            rel_path=task.rel_path,
            ext=ext,
            content=task.content,
            mtime=task.mtime,
            size=task.size,
            chunk_idx=idx,
            total_chunks=total,
            top_level_dir=task.top_level_dir,
            symbol=chunk.symbol,
            chunk_kind=chunk.kind,
        )
        try:
            entry_result = _add_entry(
                wing=task.wing,
                room=task.room,
                content=chunk.text,
                metadata=metadata,
                source="pneuma-miner",
            )
            if isinstance(entry_result, dict) and entry_result.get("entry_id"):
                res.entry_ids.append(entry_result["entry_id"])
            res.chunks_stored += 1
        except Exception as exc:
            res.errors.append(f"{task.rel_path}: {exc}")

    # Store summary
    summary_meta = _build_metadata(
        rel_path=task.rel_path,
        ext=ext,
        content=task.content,
        mtime=task.mtime,
        size=task.size,
        chunk_idx=0,
        total_chunks=total,
        top_level_dir=task.top_level_dir,
        symbol="",
        chunk_kind="summary",
    )
    summary_meta["kind"] = "summary"
    try:
        summary_result = _add_entry(
            wing=task.wing,
            room=task.room,
            content=summary.text,
            metadata=summary_meta,
            source="pneuma-miner",
        )
        if isinstance(summary_result, dict) and summary_result.get("entry_id"):
            res.entry_ids.append(summary_result["entry_id"])
        res.summaries_stored = 1
    except Exception as exc:
        res.errors.append(f"{task.rel_path} (summary): {exc}")

    return res


# ── Main entry point ─────────────────────────────────────────────────────────

def _discover_files(
    root: Path,
    config: MinerConfig,
    skip_reasons: dict[str, int] | None = None,
) -> list[Path]:
    """
    Walk *root* and return a sorted list of files to mine, applying:
      - _SKIP_DIRS
      - extension filter
      - _SKIP_FILENAMES
      - generated-file patterns (from config)
      - .gitignore / extra_skip patterns (from config)
    Priority-sorted per config.priority.

    If skip_reasons dict is passed, populate it with counts by reason.
    """
    candidates: list[tuple[int, str, Path]] = []

    def _reason(key: str) -> None:
        if skip_reasons is not None:
            skip_reasons[key] = skip_reasons.get(key, 0) + 1

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        # Also prune directories that match skip patterns so we never walk
        # into them — this is both a performance win and ensures seen_rel_paths
        # doesn't contain entries that would confuse incremental cleanup.
        try:
            cur_rel = str(Path(dirpath).relative_to(root)).replace("\\", "/")
        except ValueError:
            cur_rel = ""
        dirnames[:] = [
            d for d in dirnames
            if not config.is_dir_skipped(f"{cur_rel}/{d}" if cur_rel else d)
        ]

        for fname in filenames:
            file_path = Path(dirpath) / fname

            # Skip symlinks — they may point outside the project root
            if file_path.is_symlink():
                _reason("symlink")
                continue

            ext = Path(fname).suffix.lower()

            if fname in _SKIP_FILENAMES:
                _reason("lockfile-or-os")
                continue
            if ext in _BINARY_EXTENSIONS:
                _reason("binary")
                continue
            if ext not in _MINE_EXTENSIONS:
                _reason("unknown-extension")
                continue
            if config.is_generated(fname):
                _reason("generated")
                continue

            try:
                rel_path = str(file_path.relative_to(root)).replace("\\", "/")
            except ValueError:
                continue

            if config.is_skipped(rel_path):
                _reason("gitignore-or-skip-pattern")
                continue

            rank = config.priority_rank(rel_path)
            candidates.append((rank, rel_path, file_path))

    candidates.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in candidates]


def mine_project(
    project_path: str,
    project_slug: str | None = None,
    progress_cb=None,
    config: MinerConfig | None = None,
    dry_run: bool = False,
    incremental: bool = False,
) -> MineResult:
    """
    Walk *project_path*, embed every meaningful source file into the active
    palace, and return a MineResult summary.

    Args:
        project_path: Root directory to mine.
        project_slug: Wing name to route code into. Auto-detected from the
                      project registry if None.
        progress_cb: Optional callable(files_done, chunks_done) for progress
                     reporting — called after each file is stored.
        config: Optional MinerConfig. Loaded from <project>/.pneuma.yaml
                (or .json) if None.
        dry_run: If True, walk and classify everything but do not write.
                 MineResult.would_route gets populated with "wing/room" → count
                 and skip_reasons is populated with reason → count.
        incremental: If True, use the palace's mined_files.sqlite3 state to
                     skip files whose content hash hasn't changed. Also deletes
                     entries for files that have been removed from disk.
                     Ignored when dry_run=True.
    """
    root = Path(project_path).resolve()
    result = MineResult()

    if config is None:
        config = load_config(str(root))

    if project_slug is None:
        from core.registry import get_project
        proj = get_project(str(root))
        project_slug = (proj or {}).get("slug", "project")

    # Open the state DB when running incrementally
    state: MiningState | None = None
    palace_dir: str | None = None
    if incremental and not dry_run:
        from core.registry import get_project
        proj = get_project(str(root))
        if proj:
            palace_dir = proj["palace_dir"]
            state = MiningState(palace_dir)

    files = _discover_files(root, config, skip_reasons=result.skip_reasons)

    # Pre-scan to find large top-level dirs for depth-2 room assignment.
    # Exclude dirs that match skip patterns so their sub-rooms aren't created.
    top_dirs = [
        d.name for d in root.iterdir()
        if d.is_dir() and d.name not in _SKIP_DIRS and not config.is_dir_skipped(d.name)
    ]
    depth2_dirs = _scan_large_dirs(root, top_dirs, config.depth2_threshold)

    if not dry_run:
        from core.palace import delete_entry as _palace_delete
    else:
        _palace_delete = None  # type: ignore

    # Track which rel_paths and rooms we've seen this run.
    seen_rel_paths: set[str] = set()
    seen_rooms: set[str] = set()

    # ── Phase 1: read files, check incremental state, build task list ─────────
    tasks: list[_FileTask] = []

    for file_path in files:
        if len(tasks) + result.files_processed >= config.max_files:
            break

        try:
            stat = file_path.stat()
            if stat.st_size > config.max_file_size:
                result.skip_reasons["over-max-size"] = result.skip_reasons.get("over-max-size", 0) + 1
                continue
            mtime = stat.st_mtime
            size = stat.st_size
        except OSError:
            result.skip_reasons["stat-error"] = result.skip_reasons.get("stat-error", 0) + 1
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception as exc:
            result.errors.append(f"{file_path.name}: {exc}")
            continue

        if not content:
            result.skip_reasons["empty-file"] = result.skip_reasons.get("empty-file", 0) + 1
            continue

        rel_path = str(file_path.relative_to(root))
        rel_path_norm = rel_path.replace("\\", "/")
        seen_rel_paths.add(rel_path_norm)
        ext = file_path.suffix.lower()
        wing, room = _route_by_path(rel_path_norm, depth2_dirs)
        seen_rooms.add(room)
        top_level_dir = Path(rel_path).parts[0] if len(Path(rel_path).parts) > 1 else ""

        # ── Incremental: skip unchanged files ──────────────────────────────
        if state is not None:
            hash_now = compute_content_hash(content)
            rec = state.get(rel_path_norm)
            if rec is not None and rec.content_hash == hash_now:
                result.files_unchanged += 1
                if progress_cb:
                    progress_cb(result.files_processed + result.files_unchanged,
                                result.chunks_stored)
                continue
            # Changed — delete existing entries in main thread before re-mining
            if rec is not None and _palace_delete:
                for eid in rec.entry_ids:
                    try:
                        _palace_delete(eid)
                    except Exception:
                        pass

        tasks.append(_FileTask(
            file_path=file_path,
            rel_path=rel_path_norm,
            ext=ext,
            wing=wing,
            room=room,
            content=content,
            mtime=mtime,
            size=size,
            top_level_dir=top_level_dir,
        ))

    # ── Phase 2: process files in parallel ────────────────────────────────────
    workers = max(1, config.workers)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_task = {
            pool.submit(_mine_file_task, task, config, dry_run): task
            for task in tasks
        }
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                file_result = future.result()
            except Exception as exc:
                result.errors.append(f"{task.rel_path}: {exc}")
                continue

            if dry_run:
                key = file_result.dry_route_key
                result.would_route[key] = result.would_route.get(key, 0) + file_result.dry_route_count

            result.files_processed += 1
            result.chunks_stored += file_result.chunks_stored
            result.summaries_stored += file_result.summaries_stored
            result.errors.extend(file_result.errors)

            # State upsert in main thread (SQLite connection is not thread-safe)
            if state is not None and file_result.entry_ids:
                try:
                    state.upsert(
                        rel_path=file_result.rel_path,
                        content_hash=file_result.content_hash,
                        mtime=file_result.mtime,
                        entry_ids=file_result.entry_ids,
                    )
                except Exception as exc:
                    result.errors.append(f"{task.rel_path} (state): {exc}")

            if progress_cb:
                progress_cb(result.files_processed, result.chunks_stored)

    # ── Cleanup removed files ──────────────────────────────────────────────
    if state is not None and not dry_run:
        for rec in state.all_records():
            if rec.rel_path not in seen_rel_paths:
                if _palace_delete:
                    for eid in rec.entry_ids:
                        try:
                            _palace_delete(eid)
                        except Exception:
                            pass
                state.delete(rec.rel_path)
                result.files_removed += 1
        state.close()

    # ── Remove placeholder entries from rooms that received no mined content ──
    # Placeholder entries are created by init_palace() with source_file="".
    # If a room's directory is now skipped (or was removed), its placeholder
    # lingers. This pass deletes them so "pneuma status" reflects reality.
    if not dry_run:
        _purge_empty_code_rooms(seen_rooms)

    # files_skipped = total of all skip reasons (binary, over-max-size, etc.)
    result.files_skipped = sum(result.skip_reasons.values())

    return result


def _purge_empty_code_rooms(seen_rooms: set[str]) -> None:
    """Delete init-placeholder entries from code-wing rooms that got no content.

    Called after every mine run. Only removes entries with source_file==""
    (written by init_palace) from rooms that received no mined file in this run.
    Rooms that still have real mined content are never touched.
    """
    from core.palace import list_rooms as _list_rooms, list_room_entries as _list_entries, delete_entry as _del

    try:
        code_rooms = _list_rooms("code")
    except Exception:
        return

    for room in code_rooms:
        if room in seen_rooms:
            continue
        try:
            entries = _list_entries("code", room)
        except Exception:
            continue
        for e in entries:
            if e.source_file == "":
                try:
                    _del(e.metadata.get("id", ""))
                except Exception:
                    pass
