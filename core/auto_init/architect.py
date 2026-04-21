"""
Architect — ties analysis + templates together to auto-initialize
a MemPalace for a project.
"""

import json
import os
from pathlib import Path

from core.auto_init.analyzer import analyze_project, ProjectProfile
from core.auto_init.templates import build_template, PalaceTemplate
from core.auto_init.miner import mine_project, MineResult, _scan_large_dirs
from core.auto_init.miner_config import load_config
from core.palace import init_palace, configure
from core.registry import register_project


def auto_initialize(project_path: str, progress_cb=None) -> dict:
    """
    One-shot palace initialization:
      1. Register the project and create its isolated palace directory.
      2. Scan project to build a ProjectProfile (languages, top-level dirs).
      3. Build a PalaceTemplate with a dynamic project wing (rooms = dirs).
      4. Provision wings/rooms in the project's MemPalace.
      5. Persist a manifest so we can inspect / reorganize later.
      6. Mine all source files into the project wing.

    Args:
        project_path: Root of the project to initialize.
        progress_cb: Optional callable(files_done, chunks_done) forwarded
                     to the miner for live progress reporting.

    Returns a summary dict.
    """
    proj = register_project(project_path)
    configure(project_path)

    profile = analyze_project(project_path)
    config = load_config(project_path)
    # Exclude top-level dirs that are wholly covered by skip patterns so we
    # don't create placeholder rooms (and show 0-content entries) for them.
    active_dirs = [d for d in profile.top_level_dirs if not config.is_dir_skipped(d)]
    depth2_dirs = _scan_large_dirs(
        Path(project_path).resolve(),
        active_dirs,
        config.depth2_threshold,
    )
    template = build_template(
        complexity=profile.complexity,
        project_slug=proj["slug"],
        top_level_dirs=active_dirs,
        depth2_dirs=depth2_dirs,
    )
    rooms_created = _provision_palace(template)
    _save_manifest(profile, template, proj["palace_dir"], project_slug=proj["slug"])

    mine_result = mine_project(
        project_path,
        project_slug=proj["slug"],
        progress_cb=progress_cb,
    )

    return {
        "project": profile.root,
        "project_slug": proj["slug"],
        "complexity": profile.complexity,
        "languages": profile.languages,
        "frameworks": profile.frameworks,
        "total_files": profile.total_files,
        "top_level_dirs": profile.top_level_dirs,
        "template": template.label,
        "collections_created": rooms_created,
        "palace_dir": proj["palace_dir"],
        "mine": {
            "files_processed": mine_result.files_processed,
            "chunks_stored": mine_result.chunks_stored,
            "summaries_stored": mine_result.summaries_stored,
            "files_skipped": mine_result.files_skipped,
            "errors": mine_result.errors[:10],
        },
    }


def _provision_palace(template: PalaceTemplate) -> list[str]:
    """Create wings/rooms in the MemPalace."""
    wings_data = [
        {
            "name": wing.name,
            "rooms": [{"name": room.name, "description": room.description} for room in wing.rooms],
        }
        for wing in template.wings
    ]
    return init_palace(wings=wings_data)


def _save_manifest(
    profile: ProjectProfile,
    template: PalaceTemplate,
    palace_dir: str,
    project_slug: str,
) -> None:
    """Write a JSON manifest describing the initialized palace."""
    meta_dir = Path(palace_dir)
    meta_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "project_root": profile.root,
        "project_slug": project_slug,
        "complexity": profile.complexity,
        "languages": profile.languages,
        "frameworks": profile.frameworks,
        "top_level_dirs": profile.top_level_dirs,
        "template": template.label,
        "layout_version": 2,  # v1 = semantic rooms; v2 = directory rooms
        "wings": [
            {
                "name": w.name,
                "rooms": [{"name": r.name, "description": r.description} for r in w.rooms],
            }
            for w in template.wings
        ],
    }

    manifest_path = meta_dir / "palace_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
