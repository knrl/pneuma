"""
Per-project miner configuration.

Looks for .pneuma.yaml / .pneuma.yml / .pneuma.json at the project root
and merges it with built-in defaults. Also parses .gitignore when
respect_gitignore is enabled.

Example .pneuma.yaml:

  miner:
    chunk_size: 3000
    max_file_size: 200000
    respect_gitignore: true
    skip:
      - "third_party/**"
      - "**/*_generated.*"
    generated:
      - "*.pb.go"
      - "*-bundle.js"
    priority:
      - "README.md"
      - "docs/**"
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


# ── Defaults ─────────────────────────────────────────────────────────────────

# Generated / auto-output file patterns (always skipped unless user opts in)
_DEFAULT_GENERATED_PATTERNS: list[str] = [
    "*.pb.go", "*.pb.py", "*.pb.cc", "*.pb.h",
    "*_pb2.py", "*_pb2_grpc.py",
    "*.min.js", "*.min.css",
    "*.bundle.js", "*.bundle.css",
    "*-bundle.js", "*-bundle.css",
    "*.generated.*", "*_generated.*",
    "*.map",
    "*.d.ts.map",
]


@dataclass
class MinerConfig:
    """Resolved configuration — defaults merged with per-project overrides."""

    # Sizing
    chunk_size: int = 1500
    chunk_overlap: int = 150
    max_file_size: int = 100_000
    max_files: int = 5_000

    # Parallelism — number of files processed concurrently.
    # Higher values speed up large codebases; set to 1 to disable threading.
    workers: int = 4

    # Two-level mirroring threshold — top-level dirs with this many or more
    # immediate subdirs expand into "{top}-{subdir}" rooms instead of one room.
    depth2_threshold: int = 5

    # Skip patterns (gitignore-style globs, matched against rel path)
    extra_skip: list[str] = field(default_factory=list)

    # Generated patterns (filename globs)
    generated_patterns: list[str] = field(
        default_factory=lambda: list(_DEFAULT_GENERATED_PATTERNS)
    )

    # Priority ordering (matched paths mined first)
    priority: list[str] = field(default_factory=list)

    # Gitignore integration
    respect_gitignore: bool = True
    gitignore_patterns: list[str] = field(default_factory=list)

    # ── Matchers ───────────────────────────────────────────────────────────

    def is_skipped(self, rel_path: str) -> bool:
        """Match rel_path against skip patterns and loaded .gitignore patterns."""
        normalized = rel_path.replace("\\", "/")
        for pat in self.extra_skip:
            if _match_gitignore(normalized, pat):
                return True
        for pat in self.gitignore_patterns:
            if _match_gitignore(normalized, pat):
                return True
        return False

    def is_dir_skipped(self, dir_rel: str) -> bool:
        """Return True if the entire directory subtree should be skipped.

        Uses a sentinel path so that patterns like 'include/**' correctly
        match the directory without requiring a real file inside it.
        """
        return self.is_skipped(f"{dir_rel}/.keep")

    def is_generated(self, filename: str) -> bool:
        """Match filename against generated patterns."""
        for pat in self.generated_patterns:
            if fnmatch.fnmatchcase(filename, pat):
                return True
        return False

    def priority_rank(self, rel_path: str) -> int:
        """
        Return priority index (lower = mine earlier). Files not matching any
        priority pattern get a large number so they come last.
        """
        normalized = rel_path.replace("\\", "/")
        for idx, pat in enumerate(self.priority):
            if _match_gitignore(normalized, pat):
                return idx
        return 10_000


# ── Loading ──────────────────────────────────────────────────────────────────

def load_config(project_path: str) -> MinerConfig:
    """
    Load .pneuma.{yaml,yml,json} from the project root if present, merge with
    defaults. Also load .gitignore patterns when respect_gitignore is on.
    """
    root = Path(project_path)
    cfg = MinerConfig()

    raw = _read_config_file(root)
    if raw:
        _apply_overrides(cfg, raw)

    if cfg.respect_gitignore:
        cfg.gitignore_patterns = _read_gitignore(root)

    return cfg


def _read_config_file(root: Path) -> dict | None:
    """Look for .pneuma.yaml / .yml / .json and load it."""
    for name in (".pneuma.yaml", ".pneuma.yml"):
        path = root / name
        if path.exists():
            return _load_yaml_file(path)
    path = root / ".pneuma.json"
    if path.exists():
        return _load_json_file(path)
    return None


def _load_yaml_file(path: Path) -> dict | None:
    try:
        import yaml  # type: ignore
    except ImportError:
        import warnings
        warnings.warn(
            f"\n\n  WARNING: Found '{path.name}' but PyYAML is not installed.\n"
            f"  Your skip patterns and miner settings are being IGNORED.\n"
            f"  Fix: pip install pyyaml\n",
            stacklevel=2,
        )
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _load_json_file(path: Path) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _apply_overrides(cfg: MinerConfig, raw: dict) -> None:
    """Merge raw dict (under optional 'miner' key) into cfg."""
    section = raw.get("miner", raw) if isinstance(raw, dict) else {}
    if not isinstance(section, dict):
        return

    for key in ("chunk_size", "chunk_overlap", "max_file_size", "max_files", "workers", "depth2_threshold"):
        if key in section and isinstance(section[key], int):
            setattr(cfg, key, section[key])

    # Clamp numeric values to safe bounds to prevent resource exhaustion
    cfg.workers = max(1, min(cfg.workers, 32))
    cfg.max_files = max(1, min(cfg.max_files, 100_000))
    cfg.chunk_size = max(256, min(cfg.chunk_size, 50_000))
    cfg.chunk_overlap = max(0, min(cfg.chunk_overlap, cfg.chunk_size // 2))
    cfg.max_file_size = max(1024, min(cfg.max_file_size, 10_000_000))

    if "respect_gitignore" in section:
        cfg.respect_gitignore = bool(section["respect_gitignore"])

    for key in ("skip", "extra_skip"):
        val = section.get(key)
        if isinstance(val, list):
            cfg.extra_skip.extend(str(p) for p in val)

    val = section.get("generated")
    if isinstance(val, list):
        # User-provided list replaces the defaults entirely; they can
        # re-list defaults if they want them kept
        cfg.generated_patterns = [str(p) for p in val]

    val = section.get("priority")
    if isinstance(val, list):
        cfg.priority = [str(p) for p in val]


# ── .gitignore parsing ──────────────────────────────────────────────────────

def _read_gitignore(root: Path) -> list[str]:
    """Read root .gitignore into a list of patterns (negations dropped)."""
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return []
    patterns: list[str] = []
    try:
        for line in gitignore.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("!"):
                # Negations not supported for simplicity — drop
                continue
            patterns.append(line)
    except OSError:
        pass
    return patterns


# ── gitignore-style glob matching ────────────────────────────────────────────

def _match_gitignore(rel_path: str, pattern: str) -> bool:
    """
    Match a forward-slash rel_path against a single gitignore-style pattern.

    Handles:
      - Leading slash anchors to project root
      - Trailing slash matches directories (we treat as prefix match)
      - ** to match any number of segments
      - * to match anything within a segment
      - ? single char
    """
    pat = pattern
    anchored = pat.startswith("/")
    if anchored:
        pat = pat[1:]

    # Trailing-slash directory patterns match path prefix
    if pat.endswith("/"):
        dir_pat = pat.rstrip("/")
        regex = _glob_to_regex(dir_pat, anchored)
        # Match if any path segment matches (or full path starts with it)
        for prefix in _path_prefixes(rel_path):
            if regex.fullmatch(prefix):
                return True
        return False

    regex = _glob_to_regex(pat, anchored)
    if regex.fullmatch(rel_path):
        return True
    # Also match any trailing sub-path (gitignore semantics for `foo/bar`
    # matches `foo/bar/anything`)
    for prefix in _path_prefixes(rel_path):
        if regex.fullmatch(prefix):
            return True
    return False


def _path_prefixes(rel_path: str) -> list[str]:
    """Return [a, a/b, a/b/c] for input 'a/b/c'."""
    parts = rel_path.split("/")
    return ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]


def _glob_to_regex(pattern: str, anchored: bool) -> re.Pattern:
    """Convert a gitignore-style glob to a regex."""
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                parts.append(".*")
                i += 2
                if i < len(pattern) and pattern[i] == "/":
                    i += 1
            else:
                parts.append("[^/]*")
                i += 1
        elif c == "?":
            parts.append("[^/]")
            i += 1
        elif c == ".":
            parts.append(r"\.")
            i += 1
        elif c in "[]":
            parts.append(c)
            i += 1
        else:
            parts.append(re.escape(c))
            i += 1

    body = "".join(parts)
    if not anchored:
        body = "(?:.*/)?" + body
    return re.compile(body)
