"""
Project registry — maps project paths to isolated palace directories.

Layout:
    ~/.pneuma/
    ├── registry.json          # {project_path: {slug, palace_dir, created_at}}
    └── palaces/
        ├── my-app/            # Per-project palace data
        │   ├── palace/        # ChromaDB  (MEMPALACE_PALACE_PATH)
        │   ├── knowledge_graph.sqlite3
        │   └── palace_manifest.json
        └── other-project/
            └── ...
"""

import json
import os
import re
import time
from pathlib import Path

PNEUMA_HOME = Path(os.environ.get("PNEUMA_HOME", os.path.expanduser("~/.pneuma")))
REGISTRY_FILE = PNEUMA_HOME / "registry.json"
PALACES_DIR = PNEUMA_HOME / "palaces"


def _load_registry() -> dict:
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE) as f:
            return json.load(f)
    return {}


def _save_registry(reg: dict) -> None:
    PNEUMA_HOME.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_FILE, "w") as f:
        json.dump(reg, f, indent=2)


def _slugify(project_path: str) -> str:
    """Derive a filesystem-safe slug from the project directory name."""
    name = Path(project_path).resolve().name
    slug = re.sub(r"[^a-zA-Z0-9_-]", "-", name).strip("-").lower()
    return slug or "default"


def _unique_slug(slug: str, registry: dict) -> str:
    """Ensure slug is unique across registered projects."""
    existing_slugs = {v["slug"] for v in registry.values()}
    if slug not in existing_slugs:
        return slug
    counter = 2
    while f"{slug}-{counter}" in existing_slugs:
        counter += 1
    return f"{slug}-{counter}"


def register_project(project_path: str) -> dict:
    """
    Register a project and create its isolated palace directory.

    Returns dict with slug, palace_dir, palace_path, kg_path.
    If the project is already registered, returns its existing entry.
    """
    canonical = str(Path(project_path).resolve())
    reg = _load_registry()

    if canonical in reg:
        entry = reg[canonical]
        palace_dir = Path(entry["palace_dir"])
        palace_dir.mkdir(parents=True, exist_ok=True)
        (palace_dir / "palace").mkdir(parents=True, exist_ok=True)
        return {
            "slug": entry["slug"],
            "palace_dir": str(palace_dir),
            "palace_path": str(palace_dir / "palace"),
            "kg_path": str(palace_dir / "knowledge_graph.sqlite3"),
        }

    slug = _unique_slug(_slugify(project_path), reg)
    palace_dir = PALACES_DIR / slug
    palace_dir.mkdir(parents=True, exist_ok=True)
    (palace_dir / "palace").mkdir(parents=True, exist_ok=True)

    reg[canonical] = {
        "slug": slug,
        "palace_dir": str(palace_dir),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _save_registry(reg)

    return {
        "slug": slug,
        "palace_dir": str(palace_dir),
        "palace_path": str(palace_dir / "palace"),
        "kg_path": str(palace_dir / "knowledge_graph.sqlite3"),
    }


def get_project(project_path: str) -> dict | None:
    """Look up a registered project by its exact path."""
    canonical = str(Path(project_path).resolve())
    reg = _load_registry()
    entry = reg.get(canonical)
    if not entry:
        return None
    palace_dir = Path(entry["palace_dir"])
    return {
        "project_path": canonical,
        "slug": entry["slug"],
        "palace_dir": str(palace_dir),
        "palace_path": str(palace_dir / "palace"),
        "kg_path": str(palace_dir / "knowledge_graph.sqlite3"),
    }


def resolve_project(cwd: str = None) -> dict | None:
    """
    Auto-detect which project the user is working in by walking up from cwd.
    Returns the project entry or None if cwd is not inside any registered project.
    """
    cwd = Path(cwd or os.getcwd()).resolve()
    reg = _load_registry()

    # Check cwd and all parents against registered project paths
    registered_paths = {Path(p).resolve(): v for p, v in reg.items()}
    check = cwd
    while True:
        if check in registered_paths:
            entry = registered_paths[check]
            palace_dir = Path(entry["palace_dir"])
            return {
                "project_path": str(check),
                "slug": entry["slug"],
                "palace_dir": str(palace_dir),
                "palace_path": str(palace_dir / "palace"),
                "kg_path": str(palace_dir / "knowledge_graph.sqlite3"),
            }
        parent = check.parent
        if parent == check:
            break
        check = parent

    return None


def list_projects() -> list[dict]:
    """Return all registered projects."""
    reg = _load_registry()
    result = []
    for path, entry in reg.items():
        palace_dir = Path(entry["palace_dir"])
        result.append({
            "project_path": path,
            "slug": entry["slug"],
            "palace_dir": str(palace_dir),
            "palace_path": str(palace_dir / "palace"),
            "kg_path": str(palace_dir / "knowledge_graph.sqlite3"),
            "created_at": entry.get("created_at", ""),
        })
    return result
