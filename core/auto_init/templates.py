"""
Palace layout templates — wing/room structures generated dynamically
from a ProjectProfile.

Layout:
  - One `code` wing per project with rooms derived from directory structure.
  - One `chat` wing for team knowledge from Slack/Teams ingestion.

Rooms under `code` follow two rules:
  1. Canonical dirs (tests/, docs/) always get a stable room name.
  2. Large top-level dirs (>= depth2_threshold subdirs) expand into
     "{top}-{subdir}" rooms; everything else mirrors the top-level dir name.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass
class RoomTemplate:
    """A room within a palace wing."""
    name: str
    description: str


@dataclass
class WingTemplate:
    """A logical grouping of rooms."""
    name: str
    rooms: list[RoomTemplate] = field(default_factory=list)


@dataclass
class PalaceTemplate:
    """Full palace layout ready for provisioning."""
    label: str
    wings: list[WingTemplate] = field(default_factory=list)


# ── Canonical room names ─────────────────────────────────────────

_CANONICAL_ROOMS: dict[str, str] = {
    "test": "tests", "tests": "tests", "spec": "tests",
    "__tests__": "tests", "testing": "tests",
    "doc": "docs", "docs": "docs", "documentation": "docs",
}


def canonical_room(dirname: str) -> str | None:
    """Return the canonical room name for dirname, or None if not canonical."""
    return _CANONICAL_ROOMS.get(dirname.lower())


# ── Shared chat wing ─────────────────────────────────────────────

_CHAT_WING = WingTemplate(
    name="chat",
    rooms=[
        RoomTemplate("decisions",    "Architecture and technical decisions"),
        RoomTemplate("conventions",  "Coding conventions and style agreements"),
        RoomTemplate("solutions",    "Q&A pairs extracted from team chat"),
        RoomTemplate("workarounds",  "Temporary fixes and workarounds"),
        RoomTemplate("escalations",  "Questions escalated to humans"),
        RoomTemplate("context",      "General context and background discussions"),
    ],
)


# ── Room name slugification ──────────────────────────────────────

_SLUG_RE = re.compile(r"[^a-z0-9_-]+")


def slugify_room(name: str) -> str:
    """
    Normalize a directory name into a room-safe slug.
    Keeps lowercase letters, digits, underscores, hyphens.
    Other characters (spaces, dots) become hyphens.
    """
    s = name.lower().replace(" ", "-").replace(".", "-")
    s = _SLUG_RE.sub("-", s)
    s = s.strip("-")
    return s or "general"


# ── Dynamic code wing ────────────────────────────────────────────

def _build_code_wing(
    top_level_dirs: list[str],
    depth2_dirs: dict[str, list[str]] | None = None,
) -> WingTemplate:
    """
    Create the `code` wing with rooms derived from directory structure.

    - Canonical dirs (tests, docs) get stable names.
    - Dirs in depth2_dirs expand into "{top}-{sub}" rooms plus a "{top}"
      room for files sitting directly in the top-level dir.
    - All other dirs mirror as slugified top-level dir name.
    """
    rooms: list[RoomTemplate] = []
    seen: set[str] = set()

    def _add(name: str, desc: str) -> None:
        if name not in seen:
            seen.add(name)
            rooms.append(RoomTemplate(name=name, description=desc))

    for dirname in top_level_dirs:
        canon = canonical_room(dirname)
        if canon:
            _add(canon, f"Files from {dirname}/")
            continue

        slug = slugify_room(dirname)

        if depth2_dirs and dirname in depth2_dirs:
            # Root files of this large dir get their own room
            _add(slug, f"Files directly in {dirname}/")
            for subdir in depth2_dirs[dirname]:
                sub_slug = slugify_room(f"{dirname}-{subdir}")
                _add(sub_slug, f"Files from {dirname}/{subdir}/")
        else:
            _add(slug, f"Files from {dirname}/")

    _add("general", "Files at the project root or not otherwise placed")

    return WingTemplate(name="code", rooms=rooms)


# ── Entry point ──────────────────────────────────────────────────

def build_template(
    complexity: str = "small",
    project_slug: str = "project",
    top_level_dirs: list[str] | None = None,
    depth2_dirs: dict[str, list[str]] | None = None,
) -> PalaceTemplate:
    """
    Return a PalaceTemplate for the project.

    Args:
        complexity:     small | medium | large — used only for the label.
        project_slug:   Kept for backwards-compatibility; no longer used as
                        a wing name (wing is always "code").
        top_level_dirs: Top-level directory names from the project.
        depth2_dirs:    {top_dir: [subdir, ...]} for dirs above the depth-2
                        threshold — produced by miner._scan_large_dirs().
    """
    code_wing = _build_code_wing(top_level_dirs or [], depth2_dirs)

    return PalaceTemplate(
        label=f"auto-{complexity}",
        wings=[code_wing, _CHAT_WING],
    )
