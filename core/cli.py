"""
Pneuma CLI.
Usage:
    pneuma quickstart [path]  — First-time setup: scaffold config, init, IDE setup, doctor.
    pneuma init [path]       — Auto-initialize a palace for the project at *path*.
    pneuma status            — Show palace status and collection stats.
    pneuma wakeup [wing]     — Load identity & essential story from the palace.
    pneuma search <query>    — Search the knowledge base.
    pneuma import <file>     — Import a document or chat history into the palace.
    pneuma diary [read|write]— Read or write agent diary entries.
    pneuma timeline [entity] — Chronological timeline of facts.
    pneuma optimize          — Run dedup + stale cleanup.
    pneuma facts <entity>    — Look up what's known about an entity.    pneuma setup <ide>       — Generate MCP config for your IDE (vscode or cursor).
    pneuma doctor            — Verify installation and configuration."""

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path

import core.env  # noqa: F401 — loads .env from Pneuma install root


def _auto_configure():
    """Auto-detect and configure the active project from CWD."""
    from core.palace import configure
    proj = configure(os.environ.get("PNEUMA_PROJECT"))
    return proj


def main():
    parser = argparse.ArgumentParser(
        prog="pneuma",
        description="Pneuma — Zero-Friction AI Memory Bridge",
    )
    sub = parser.add_subparsers(dest="command")

    # pneuma init
    init_p = sub.add_parser("init", help="Auto-initialize a palace for a project")
    init_p.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root to scan (default: current directory)",
    )
    init_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be mined without writing any entries",
    )

    # pneuma mine — re-mine an already-initialized project (incremental by default)
    mine_p = sub.add_parser("mine", help="Mine the codebase into the palace")
    mine_p.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root to mine (default: current directory)",
    )
    mine_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be mined without writing any entries",
    )
    mine_p.add_argument(
        "--full",
        action="store_true",
        help="Full re-mine (ignore state DB; re-embed every file)",
    )

    # pneuma status
    status_p = sub.add_parser("status", help="Show palace status and collection stats")
    status_p.add_argument(
        "-v", "--detail",
        action="store_true",
        help="Show sample entries for each room",
    )

    # pneuma wakeup
    wakeup_p = sub.add_parser("wakeup", help="Load identity & essential story")
    wakeup_p.add_argument(
        "wing",
        nargs="?",
        default="",
        help="Optional wing to scope the story to (default: all)",
    )

    # pneuma search
    search_p = sub.add_parser("search", help="Search the knowledge base")
    search_p.add_argument("query", help="Natural-language search query")
    search_p.add_argument(
        "-n", "--top-k", type=int, default=5,
        help="Max results (default: 5)",
    )
    search_p.add_argument(
        "-w", "--wing", default=None,
        help="Filter by wing",
    )
    search_p.add_argument(
        "-r", "--room", default=None,
        help="Filter by room",
    )

    # pneuma diary
    diary_p = sub.add_parser("diary", help="Read or write agent diary entries")
    diary_sub = diary_p.add_subparsers(dest="diary_action")
    diary_read_p = diary_sub.add_parser("read", help="Read recent diary entries")
    diary_read_p.add_argument(
        "-a", "--agent", default="pneuma",
        help="Agent name (default: pneuma)",
    )
    diary_read_p.add_argument(
        "-n", "--last-n", type=int, default=10,
        help="Number of entries to read (default: 10)",
    )
    diary_write_p = diary_sub.add_parser("write", help="Write a diary entry")
    diary_write_p.add_argument("entry", help="Diary entry text")
    diary_write_p.add_argument(
        "-a", "--agent", default="pneuma",
        help="Agent name (default: pneuma)",
    )
    diary_write_p.add_argument(
        "-t", "--topic", default="general",
        help="Topic tag (default: general)",
    )

    # pneuma timeline
    timeline_p = sub.add_parser("timeline", help="Chronological timeline of facts")
    timeline_p.add_argument(
        "entity", nargs="?", default="",
        help="Entity to show timeline for (default: all)",
    )

    # pneuma optimize
    optimize_p = sub.add_parser("optimize", help="Run dedup + stale entry cleanup")
    optimize_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be merged/archived without writing",
    )
    optimize_p.add_argument(
        "--level",
        choices=["standard", "deep"],
        default="standard",
        help="standard: dedup+stale+health+facts; deep: adds compression, rebuild, migration",
    )

    # pneuma import
    import_p = sub.add_parser("import", help="Import a document or chat history")
    import_p.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Path to the file to import (markdown, text, or Slack JSON)",
    )
    import_p.add_argument(
        "--text",
        default=None,
        help="Raw text to import (instead of a file path)",
    )
    import_p.add_argument(
        "--type",
        dest="doc_type",
        default="auto",
        choices=["auto", "decision", "chat-history", "general"],
        help="Document type (default: auto-detect)",
    )
    import_p.add_argument(
        "--wing", default="",
        help="Target wing override (default: auto-route)",
    )
    import_p.add_argument(
        "--room", default="",
        help="Target room override (default: auto-route)",
    )

    # pneuma facts
    facts_p = sub.add_parser("facts", help="Look up what's known about an entity")
    facts_p.add_argument("entity", help="Entity to query")
    facts_p.add_argument(
        "--as-of", default="",
        help="Date filter (ISO format, e.g. 2026-01-15)",
    )

    # pneuma explore
    explore_p = sub.add_parser("explore", help="Walk the palace graph from a room")
    explore_p.add_argument(
        "room",
        nargs="?",
        default="",
        help="Room to start from (e.g. 'api', 'architecture'). Omit to list all rooms.",
    )
    explore_p.add_argument(
        "-n", "--hops",
        type=int,
        default=2,
        help="Max hops to traverse (default: 2)",
    )

    # pneuma bridges
    bridges_p = sub.add_parser("bridges", help="Find rooms that bridge two wings")
    bridges_p.add_argument("wing_a", nargs="?", default="", help="First wing (optional)")
    bridges_p.add_argument("wing_b", nargs="?", default="", help="Second wing (optional)")

    # pneuma quickstart — init + ide setup + doctor in one shot
    qs_p = sub.add_parser(
        "quickstart",
        help="Init, connect IDE, and verify in one command (recommended for new installs)",
    )
    qs_p.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root to initialize (default: current directory)",
    )
    qs_p.add_argument(
        "--ide",
        choices=["vscode", "cursor", "claude-code", "auto"],
        default="auto",
        help="IDE to configure (default: auto-detect)",
    )
    qs_p.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip the .pneuma.yaml edit prompt and proceed with defaults (useful for CI)",
    )

    # pneuma setup
    setup_p = sub.add_parser("setup", help="Generate MCP config for your IDE")
    setup_p.add_argument(
        "ide",
        choices=["vscode", "cursor", "claude-code"],
        help="IDE to configure (vscode, cursor, or claude-code)",
    )

    # pneuma doctor
    sub.add_parser("doctor", help="Verify installation and configuration")

    # pneuma info — show active palace, config sources, what's loaded
    sub.add_parser("info", help="Show active palace, config, and environment info")

    # pneuma show <entry_id> — view a specific entry fully
    show_p = sub.add_parser("show", help="Show the full content of a specific entry")
    show_p.add_argument("entry_id", help="Entry ID (from search or save output)")

    # pneuma recent — last N entries ingested
    recent_p = sub.add_parser("recent", help="Show recently ingested entries")
    recent_p.add_argument(
        "-n", "--last-n", type=int, default=20,
        help="Number of entries to show (default: 20)",
    )
    recent_p.add_argument(
        "-w", "--wing", default="",
        help="Filter to a specific wing",
    )

    # pneuma reset — delete a palace entirely (with confirmation)
    reset_p = sub.add_parser("reset", help="Delete a project's palace completely")
    reset_p.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root whose palace to reset (default: current directory)",
    )
    reset_p.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt",
    )

    # pneuma config — view / scaffold .pneuma.yaml
    config_p = sub.add_parser("config", help="View or scaffold per-project .pneuma config")
    config_sub = config_p.add_subparsers(dest="config_action")
    config_sub.add_parser("show", help="Print the effective miner config")
    config_init_p = config_sub.add_parser("init", help="Scaffold a .pneuma.yaml in the project root")
    config_init_p.add_argument(
        "--format",
        choices=["yaml", "json"],
        default="yaml",
        help="Config format (default: yaml if PyYAML available, else json)",
    )

    # pneuma test-slack / test-teams — verify live integration end-to-end
    test_slack_p = sub.add_parser("test-slack", help="Verify Slack integration end-to-end")
    test_teams_p = sub.add_parser("test-teams", help="Verify Teams integration end-to-end")

    # pneuma logs — tail MCP server logs
    logs_p = sub.add_parser("logs", help="Tail the MCP server log file")
    logs_p.add_argument(
        "-n", "--lines", type=int, default=50,
        help="Number of lines to show (default: 50)",
    )
    logs_p.add_argument(
        "-f", "--follow",
        action="store_true",
        help="Follow the log (like tail -f)",
    )

    args = parser.parse_args()

    # Auto-configure project context (except for init, which does its own)
    # Commands that don't need an active project
    _no_project_needed = {
        "setup", "doctor", "info", "reset",
        "test-slack", "test-teams", "logs", "quickstart",
    }

    if args.command and args.command != "init":
        proj = _auto_configure()
        if not proj and args.command not in _no_project_needed:
            print("No project found. Run `pneuma init /path/to/project` first,")
            print("or run this command from inside a registered project directory.")
            sys.exit(1)

    if args.command == "init":
        _cmd_init(args.path, dry_run=getattr(args, "dry_run", False))
    elif args.command == "quickstart":
        _cmd_quickstart(args.path, ide=args.ide, yes=getattr(args, "yes", False))
    elif args.command == "mine":
        _cmd_mine(
            args.path,
            dry_run=getattr(args, "dry_run", False),
            full=getattr(args, "full", False),
        )
    elif args.command == "status":
        _cmd_status(detail=getattr(args, "detail", False))
    elif args.command == "wakeup":
        _cmd_wakeup(args.wing)
    elif args.command == "search":
        _cmd_search(args.query, args.top_k, args.wing, args.room)
    elif args.command == "diary":
        _cmd_diary(args)
    elif args.command == "timeline":
        _cmd_timeline(args.entity)
    elif args.command == "import":
        _cmd_import(args)
    elif args.command == "optimize":
        _cmd_optimize(
            dry_run=getattr(args, "dry_run", False),
            level=getattr(args, "level", "standard"),
        )
    elif args.command == "facts":
        _cmd_facts(args.entity, args.as_of)
    elif args.command == "explore":
        _cmd_explore(args.room, args.hops)
    elif args.command == "bridges":
        _cmd_bridges(args.wing_a, args.wing_b)
    elif args.command == "setup":
        _cmd_setup(args.ide)
    elif args.command == "doctor":
        _cmd_doctor()
    elif args.command == "info":
        _cmd_info()
    elif args.command == "show":
        _cmd_show(args.entry_id)
    elif args.command == "recent":
        _cmd_recent(args.last_n, args.wing or None)
    elif args.command == "reset":
        _cmd_reset(args.path, confirm=not args.yes)
    elif args.command == "config":
        _cmd_config(args)
    elif args.command == "test-slack":
        _cmd_test_slack()
    elif args.command == "test-teams":
        _cmd_test_teams()
    elif args.command == "logs":
        _cmd_logs(args.lines, args.follow)
    else:
        parser.print_help()
        sys.exit(1)


def _embedding_model_cached() -> bool:
    """
    Detect whether the sentence-transformers embedding model appears to be
    cached locally. Returns True if yes, False if we'll likely download on first use.

    This isn't exhaustive — it looks at the standard HuggingFace cache paths.
    """
    from pathlib import Path
    candidate_roots: list[Path] = []

    for env_var in ("HF_HOME", "HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE"):
        val = os.environ.get(env_var)
        if val:
            candidate_roots.append(Path(val))

    candidate_roots.append(Path.home() / ".cache" / "huggingface")

    for root in candidate_roots:
        if not root.exists():
            continue
        # Look for any sentence-transformers model under hub/
        hub = root / "hub" if (root / "hub").exists() else root
        for p in hub.glob("models--sentence-transformers--*"):
            if p.is_dir():
                return True
    return False


def _cmd_init(path: str, dry_run: bool = False) -> None:
    from core.auto_init.architect import auto_initialize

    path = os.path.abspath(path)

    # First-run hint: the embedding model (~90MB) downloads on first use.
    # Without this notice, users will think `pneuma init` has hung.
    if not dry_run and not _embedding_model_cached():
        print("First-run notice")
        print("----------------")
        print("  Pneuma needs a local embedding model (~90MB) to turn text into vectors.")
        print("  On first run it will download via sentence-transformers. This is a")
        print("  ONE-TIME download; subsequent runs are instant.")
        print("  Expect 30-90 seconds of silent download on typical broadband.")
        print()

    if dry_run:
        print(f"[DRY RUN] Scanning project: {path}")
        # Dry-run path: analyze + build template + mine in dry_run mode,
        # but do not register or provision the palace.
        from core.auto_init.analyzer import analyze_project
        from core.auto_init.templates import build_template
        from core.auto_init.miner import mine_project

        profile = analyze_project(path)
        template = build_template(
            complexity=profile.complexity,
            project_slug=Path(path).name.lower().replace(" ", "-") or "project",
            top_level_dirs=profile.top_level_dirs,
        )
        mine_result = mine_project(path, dry_run=True)

        print(f"\nComplexity     : {profile.complexity}")
        print(f"Languages      : {', '.join(profile.languages) or 'none'}")
        print(f"Top-level dirs : {', '.join(profile.top_level_dirs) or 'none'}")
        print(f"Wings would be : {', '.join(w.name for w in template.wings)}")

        _print_mine_summary(mine_result, dry_run=True)
        print("\n[DRY RUN] No entries written, no palace created.")
        return

    print(f"Scanning project: {path}")

    def _progress(files_done: int, chunks_done: int) -> None:
        print(f"\r  Mining codebase — {files_done} files, {chunks_done} chunks stored...", end="", flush=True)

    result = auto_initialize(path, progress_cb=_progress)
    print()  # clear progress line

    print(f"\nComplexity : {result['complexity']}")
    print(f"Languages  : {', '.join(result['languages']) or 'none detected'}")
    print(f"Frameworks : {', '.join(result['frameworks']) or 'none detected'}")
    print(f"Template   : {result['template']}")
    print(f"Palace dir : {result['palace_dir']}")
    print(f"Code wing  : code  (project: {result.get('project_slug', '?')})")
    print(f"Top-level dirs: {', '.join(result.get('top_level_dirs', [])) or 'none'}")
    print(f"Collections: {len(result['collections_created'])}")
    for name in result["collections_created"]:
        print(f"  - {name}")

    mine = result.get("mine", {})
    print(f"\nCodebase mined:")
    print(f"  Files processed : {mine.get('files_processed', 0)}")
    print(f"  Chunks stored   : {mine.get('chunks_stored', 0)}")
    print(f"  Summaries stored: {mine.get('summaries_stored', 0)}")
    print(f"  Files skipped   : {mine.get('files_skipped', 0)}")
    # Show whether a .pneuma.yaml was found and loaded
    from core.auto_init.miner_config import _read_config_file as _peek_cfg
    cfg_file = _peek_cfg(Path(path))
    if cfg_file is not None:
        cfg_names = [n for n in (".pneuma.yaml", ".pneuma.yml", ".pneuma.json") if (Path(path) / n).exists()]
        print(f"  Config loaded   : {cfg_names[0] if cfg_names else '(found)'}")
    else:
        for n in (".pneuma.yaml", ".pneuma.yml"):
            if (Path(path) / n).exists():
                print(f"  Config          : {n} found but NOT loaded (run: pip install pyyaml)")
                break
        else:
            print(f"  Config          : none (.pneuma.yaml not present — using defaults)")
    if mine.get("errors"):
        print(f"  Errors          : {len(mine['errors'])}")
        for err in mine["errors"][:3]:
            print(f"    - {err}")

    print("\nPalace initialized successfully.")


def _cmd_mine(path: str, dry_run: bool = False, full: bool = False) -> None:
    """Re-mine the codebase into an already-initialized palace.

    Incremental by default — only re-embeds files whose content hash changed
    since the last mine, and deletes entries for files that have been removed
    from disk. Pass --full to force a complete re-mine.
    """
    from core.auto_init.miner import mine_project
    from core.palace import configure
    from core.registry import resolve_project, get_project

    path = os.path.abspath(path)
    proj = get_project(path) or resolve_project(path)
    if not proj:
        print(f"No palace registered for {path}. Run `pneuma init` first.")
        sys.exit(1)

    if not dry_run:
        configure(path)

    incremental = not full and not dry_run
    mode = "[DRY RUN] " if dry_run else ("[FULL] " if full else "[INCREMENTAL] ")
    print(f"{mode}Mining codebase: {path}")

    def _progress(files_done: int, chunks_done: int) -> None:
        marker = "would store" if dry_run else "stored"
        print(f"\r  {mode}{files_done} files, {chunks_done} chunks {marker}...", end="", flush=True)

    result = mine_project(
        path,
        project_slug=proj["slug"],
        progress_cb=_progress,
        dry_run=dry_run,
        incremental=incremental,
    )
    print()

    _print_mine_summary(result, dry_run=dry_run, incremental=incremental)


def _print_mine_summary(result, dry_run: bool = False, incremental: bool = False) -> None:
    """Pretty-print a MineResult (shared by init and mine commands)."""
    verb = "Would process" if dry_run else "Processed"
    store_verb = "Would store" if dry_run else "Stored"

    print(f"\n{verb.rjust(16)} : {result.files_processed} files")
    print(f"{store_verb.rjust(16)} : {result.chunks_stored} chunks")
    print(f"{store_verb.rjust(16)} : {result.summaries_stored} summaries")
    print(f"{'Skipped'.rjust(16)} : {result.files_skipped} files")

    if incremental:
        print(f"{'Unchanged'.rjust(16)} : {result.files_unchanged} files (hash match, skipped)")
        if result.files_removed:
            print(f"{'Removed'.rjust(16)} : {result.files_removed} files (deleted from disk)")

    if getattr(result, "skip_reasons", None):
        print("\nSkip breakdown:")
        for reason, count in sorted(result.skip_reasons.items(), key=lambda x: -x[1]):
            print(f"  {reason:<30} {count:>6}")

    if dry_run and getattr(result, "would_route", None):
        print("\nRoute breakdown (wing/room → chunks):")
        for loc, count in sorted(result.would_route.items(), key=lambda x: -x[1]):
            print(f"  {loc:<40} {count:>6}")

    if result.errors:
        print(f"\nErrors: {len(result.errors)}")
        for err in result.errors[:5]:
            print(f"  - {err}")


def _cmd_status(detail: bool = False) -> None:
    from core.palace import list_wings, list_rooms, palace_path, search, _active_project
    from core.registry import resolve_project

    proj = _active_project or resolve_project()
    if proj:
        manifest_path = os.path.join(proj["palace_dir"], "palace_manifest.json")
        if os.path.exists(manifest_path):
            with open(manifest_path) as f:
                manifest = json.load(f)
            print(f"Project    : {manifest.get('project_root', 'unknown')}")
            print(f"Complexity : {manifest.get('complexity', 'unknown')}")
            print(f"Template   : {manifest.get('template', 'unknown')}")
        else:
            print("No palace manifest found.\n")
    else:
        print("No project found. Run `pneuma init /path/to/project` first.\n")

    print(f"Palace path: {palace_path()}")

    wings = list_wings()
    if not wings:
        print("No entries in the palace.")
        return

    total = 0
    print(f"\nWings ({len(wings)}):")
    for wing_name, wing_count in sorted(wings.items()):
        print(f"\n  {wing_name} ({wing_count} entries)")
        rooms = list_rooms(wing=wing_name)
        for room_name, room_count in sorted(rooms.items()):
            print(f"    {room_name:40s} {room_count:>6} entries")
            total += room_count

            if detail and room_count > 0:
                try:
                    hits = search("", wing=wing_name, room=room_name, top_k=3)
                    for hit in hits:
                        # First line of content (skip "File: ..." header if present)
                        lines = [l for l in hit.content.splitlines() if l.strip()]
                        preview = lines[0] if lines else ""
                        if preview.startswith("File:"):
                            # Show the path cleanly
                            print(f"      {preview}")
                        else:
                            print(f"      · {preview[:80]}")
                except Exception:
                    pass

    print(f"\n  {'TOTAL':42s} {total:>6} entries")
    if not detail:
        print("\n  Tip: run `pneuma status -v` to preview entries in each room.")


def _cmd_explore(room: str, max_hops: int) -> None:
    from core.palace import traverse_palace, list_wings, list_rooms

    if not room:
        # No room given — list all wings and rooms as a map
        wings = list_wings()
        if not wings:
            print("Palace is empty. Run `pneuma init` first.")
            return
        print("\nPalace map:\n")
        for wing_name, wing_count in sorted(wings.items()):
            print(f"  [{wing_name}]  ({wing_count} entries)")
            rooms = list_rooms(wing=wing_name)
            for room_name, room_count in sorted(rooms.items()):
                print(f"    └─ {room_name:<36} {room_count:>6} entries")
        print(f"\n  Tip: pneuma explore <room>   — walk connections from that room")
        return

    max_hops = min(max_hops, 5)
    results = traverse_palace(room, max_hops=max_hops)

    if not results or isinstance(results, dict):
        err = ""
        if isinstance(results, dict):
            err = f" ({results.get('error', '')})"
        print(f"No connections found from room '{room}'.{err}")
        return

    print(f"\nGraph traversal from '{room}' (max {max_hops} hops):\n")
    for node in results:
        hop = node.get("hop", 0)
        node_room = node.get("room", "?")
        node_wings = ", ".join(node.get("wings", []))
        count = node.get("count", 0)
        indent = "  " + ("  " * hop) + "└─ " if hop > 0 else "  ● "
        print(f"{indent}{node_room}   [{node_wings}]  {count} entries")


def _cmd_bridges(wing_a: str, wing_b: str) -> None:
    from core.palace import find_palace_tunnels

    results = find_palace_tunnels(
        wing_a=wing_a or None,
        wing_b=wing_b or None,
    )

    if not results:
        filters = " and ".join(w for w in [wing_a, wing_b] if w)
        where = f" between {filters}" if filters else ""
        print(f"No cross-wing bridges found{where}.")
        return

    desc = ""
    if wing_a or wing_b:
        desc = " between " + " and ".join(w for w in [wing_a, wing_b] if w)
    print(f"\nCross-wing bridges{desc} ({len(results)} found):\n")
    for tunnel in results:
        room_name = tunnel.get("room", "?")
        bridges = ", ".join(tunnel.get("wings", []))
        count = tunnel.get("count", 0)
        print(f"  {room_name:<36} bridges: {bridges}  ({count} entries)")


def _cmd_wakeup(wing: str) -> None:
    from core.palace import wake_up

    text = wake_up(wing=wing or None)
    if text:
        print(text)
    else:
        print("No identity or story configured yet. Add drawers to the palace first.")


def _cmd_search(query: str, top_k: int, wing: str | None, room: str | None) -> None:
    from core.palace import search

    results = search(query, wing=wing, room=room, top_k=top_k)
    if not results:
        print("No results found.")
        return

    print(f"Found {len(results)} results:\n")
    for i, r in enumerate(results, 1):
        print(f"--- Result {i} [{r.wing}/{r.room}] (similarity: {r.similarity:.3f}) ---")
        print(r.content)
        print()


def _cmd_diary(args) -> None:
    from core.palace import diary_read, diary_write

    if args.diary_action == "read":
        result = diary_read(agent_name=args.agent, last_n=args.last_n)
        entries = result.get("entries", [])
        if not entries:
            print(f"No diary entries for '{args.agent}'.")
            return
        print(f"Diary for '{args.agent}' ({len(entries)} entries):\n")
        for e in entries:
            print(f"  [{e.get('timestamp', '?')}] ({e.get('topic', 'general')})")
            print(f"    {e.get('entry', '')}\n")

    elif args.diary_action == "write":
        result = diary_write(
            agent_name=args.agent,
            entry=args.entry,
            topic=args.topic,
        )
        print(f"Diary entry saved. (id: {result.get('id', '?')})")

    else:
        print("Usage: pneuma diary {read|write}")
        sys.exit(1)


def _cmd_timeline(entity: str) -> None:
    from core.palace import get_kg

    kg = get_kg()
    timeline = kg.timeline(entity_name=entity or None)

    if not timeline:
        label = f" for '{entity}'" if entity else ""
        print(f"No timeline data{label}.")
        return

    label = f" for '{entity}'" if entity else ""
    print(f"Timeline{label} ({len(timeline)} facts):\n")
    for entry in timeline:
        status = "current" if entry.get("current") else "expired"
        valid_to = entry.get("valid_to", "present")
        print(
            f"  [{status}] {entry.get('subject', '?')} → "
            f"{entry.get('predicate', '?')} → {entry.get('object', '?')}"
        )
        print(f"      {entry.get('valid_from', '?')} → {valid_to}")


def _cmd_optimize(dry_run: bool = False, level: str = "standard") -> None:
    from core.auto_org.refactor import run_optimize

    prefix = "[DRY RUN] " if dry_run else ""
    mode = f"[{level.upper()}] " if level != "standard" else ""
    print(f"{prefix}{mode}Running optimization...")
    report = run_optimize(dry_run=dry_run, level=level)

    # Stage 1: Dedup
    merge_label = "Would merge" if dry_run else "Duplicates merged"
    print(f"\n{merge_label:<22} : {report.duplicates_merged}")

    # Stage 2: Stale
    stale_label = "Would delete (stale)" if dry_run else "Stale entries deleted"
    print(f"{stale_label:<22} : {report.stale_removed}")

    print(f"Collections scanned    : {report.collections_scanned}")

    # Stage 3: Index health
    if report.index_corrupt_found > 0:
        if dry_run:
            print(f"Corrupt IDs found      : {report.index_corrupt_found} (would prune)")
        else:
            print(f"Corrupt IDs pruned     : {report.index_corrupt_pruned}")
    else:
        print(f"Index health           : clean")

    # Stage 4: Contradictions
    if report.contradictions:
        print(f"Contradictions         : {len(report.contradictions)} found")
        for c in report.contradictions[:10]:
            print(f"  [{c['type']}] {c.get('detail', '')}")
    else:
        print(f"Contradictions         : none")

    # Stage 5: Indexing status
    pct = round(report.indexing_progress * 100)
    print(f"Indexing status        : {pct}% ({report.unindexed_ops} unindexed)")

    # Deep stages
    if level == "deep":
        print(f"Entries compressed     : {report.entries_compressed}")
        rebuilt = "yes" if report.index_rebuilt else ("no (dry-run)" if dry_run else "no")
        print(f"Index rebuilt          : {rebuilt}")
        print(f"Migration needed       : {'yes' if report.migration_needed else 'no'}")
        if report.migration_needed:
            done = "yes" if report.migration_done else ("no (dry-run)" if dry_run else "no")
            print(f"Migration done         : {done}")

    # Dry-run details
    if dry_run and report.would_merge:
        print(f"\nProposed merges (showing first 10):")
        for m in report.would_merge[:10]:
            print(f"  source={m['source']}, drop {m['drop_count']} duplicates")

    if dry_run and report.would_archive:
        print(f"\nStale entries to delete (showing first 10):")
        for s in report.would_archive[:10]:
            print(f"  [{s['wing']}/{s['room']}]  {s['drawer_id']}  ({s['age_days']}d old)")
            print(f"    preview: {s['preview'][:80]}")

    if dry_run and report.would_prune:
        print(f"\nCorrupt IDs to prune   : {len(report.would_prune)}")

    if report.errors:
        print(f"\nErrors                 : {len(report.errors)}")
        for err in report.errors:
            print(f"  - {err}")
    else:
        if dry_run:
            print("\n[DRY RUN] Nothing was written. Re-run without --dry-run to apply.")
        else:
            print("\nOptimization complete — no errors.")


def _cmd_import(args) -> None:
    import sys as _sys

    from core.ingestion.doc_parser import import_file, import_content

    if args.file and args.text:
        print("Error: specify either a file path or --text, not both.")
        _sys.exit(1)

    if args.text:
        # Read from stdin if text is "-"
        if args.text == "-":
            content = _sys.stdin.read()
        else:
            content = args.text

        result = import_content(
            content=content,
            doc_type=args.doc_type,
            wing=args.wing,
            room=args.room,
        )
        source = "stdin" if args.text == "-" else "pasted text"
    elif args.file:
        try:
            result = import_file(
                path=args.file,
                doc_type=args.doc_type,
                wing=args.wing,
                room=args.room,
            )
        except FileNotFoundError:
            print(f"Error: file not found: {args.file}")
            _sys.exit(1)
        source = args.file
    else:
        print("Error: provide a file path or --text.")
        _sys.exit(1)

    print(f"\nImport complete — {source}")
    print(f"  Document type      : {result.get('doc_type', 'unknown')}")
    print(f"  Entries stored     : {result.get('entries_stored', 0)}")

    skipped = result.get("duplicates_skipped", 0)
    if skipped:
        print(f"  Duplicates skipped : {skipped}")

    if result.get("messages_parsed") is not None:
        print(f"  Messages parsed    : {result['messages_parsed']}")
    if result.get("messages_after_filter") is not None:
        print(f"  After noise filter : {result['messages_after_filter']}")
    if result.get("stories_extracted") is not None:
        print(f"  Stories extracted   : {result['stories_extracted']}")

    errors = result.get("errors", [])
    if errors:
        print(f"  Errors             : {len(errors)}")
        for err in errors[:5]:
            print(f"    - {str(err)[:120]}")


def _cmd_facts(entity: str, as_of: str) -> None:
    from core.palace import get_kg

    kg = get_kg()
    facts = kg.query_entity(name=entity, as_of=as_of or None)

    if not facts:
        print(f"No facts found for '{entity}'.")
        return

    print(f"Facts about '{entity}' ({len(facts)} total):\n")
    for f in facts:
        arrow = "→" if f.get("direction") == "outgoing" else "←"
        current = "✓" if f.get("current") else "✗"
        print(
            f"  [{current}] {f.get('subject', '?')} {arrow} "
            f"{f.get('predicate', '?')} {arrow} {f.get('object', '?')}"
        )
        if f.get("valid_from"):
            print(f"      valid: {f['valid_from']} → {f.get('valid_to', 'present')}")


def _cmd_quickstart(path: str, ide: str = "auto", yes: bool = False) -> None:
    """Combined first-time setup: configure → init → IDE config → doctor."""
    from core.setup import detect_ides, run_setup, _scaffold_pneuma_yaml

    abs_path = os.path.abspath(path)

    print("=" * 60)
    print("Pneuma quickstart")
    print("=" * 60)

    # Step 0: scaffold .pneuma.yaml so the user can tune it before mining
    print("\n[0/3] Creating .pneuma.yaml in project directory...")
    _scaffold_pneuma_yaml(abs_path)
    config_file = next(
        (abs_path + "/" + n for n in (".pneuma.yaml", ".pneuma.yml", ".pneuma.json")
         if Path(abs_path, n).exists()),
        None,
    )
    if config_file and not yes:
        print()
        print(f"  Open {config_file} to adjust workers, skip patterns,")
        print(f"  priority files, or chunk sizes before the first mine.")
        print()
        try:
            input("  Press Enter when ready to start mining (Ctrl+C to abort)... ")
        except KeyboardInterrupt:
            print("\nAborted. Edit .pneuma.yaml and re-run `pneuma quickstart`.")
            sys.exit(0)

    # Step 1: init (mine picks up .pneuma.yaml automatically)
    print("\n[1/3] Initializing palace...")
    _cmd_init(abs_path)

    # Step 2: IDE setup
    print("\n[2/3] Configuring IDE...")
    if ide == "auto":
        ides = detect_ides()
        print(f"  Auto-detected IDE(s): {', '.join(ides)}")
    else:
        ides = [ide]

    os.chdir(abs_path)
    for detected_ide in ides:
        run_setup(detected_ide)

    # Step 3: doctor
    print("\n[3/3] Running health checks...")
    from core.doctor import run_doctor
    ok = run_doctor()

    print("\n" + "=" * 60)
    if ok:
        print("Quickstart complete. Your AI assistant can now access Pneuma.")
        print(f"Restart your IDE, then ask: \"What do you know about this project?\"")
    else:
        print("Quickstart finished with warnings. Fix any [FAIL] items above,")
        print("then run `pneuma doctor` again to verify.")
    print("=" * 60)

    if not ok:
        sys.exit(1)


def _cmd_setup(ide: str) -> None:
    from core.setup import run_setup
    run_setup(ide)


def _cmd_doctor() -> None:
    from core.doctor import run_doctor

    ok = run_doctor()
    sys.exit(0 if ok else 1)


# ── info ─────────────────────────────────────────────────────────────────────

def _cmd_info() -> None:
    """Show active palace, project registration, config sources."""
    from core.registry import resolve_project, PNEUMA_HOME, REGISTRY_FILE, PALACES_DIR
    from core.auto_init.miner_config import load_config
    from pathlib import Path

    print("\nPneuma")
    print("------")

    # Installation
    import core
    pneuma_root = Path(core.__file__).resolve().parent.parent
    print(f"  Install root : {pneuma_root}")
    print(f"  Python       : {sys.executable}")

    # Pneuma home
    print(f"\n  ~/.pneuma    : {PNEUMA_HOME}")
    print(f"  registry.json: {'exists' if REGISTRY_FILE.exists() else 'missing'}")
    print(f"  palaces/     : {PALACES_DIR if PALACES_DIR.exists() else '(not created yet)'}")

    # Active project
    proj = resolve_project()
    cwd = os.getcwd()
    print(f"\nActive project (resolved from {cwd}):")
    if not proj:
        print("  (none) — run `pneuma init` to register this directory")
        print_env = False
    else:
        print(f"  Project path : {proj['project_path']}")
        print(f"  Slug (wing)  : {proj['slug']}")
        print(f"  Palace dir   : {proj['palace_dir']}")
        print(f"  Palace path  : {proj['palace_path']}")
        print(f"  KG path      : {proj['kg_path']}")

        # Manifest
        manifest_path = Path(proj["palace_dir"]) / "palace_manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
                print(f"  Layout ver.  : v{manifest.get('layout_version', 1)}")
                print(f"  Complexity   : {manifest.get('complexity', '?')}")
                print(f"  Wings        : {', '.join(w['name'] for w in manifest.get('wings', []))}")
            except Exception:
                pass

        # State DB
        state_db = Path(proj["palace_dir"]) / "mined_files.sqlite3"
        print(f"  Mine state   : {'exists' if state_db.exists() else 'none (full mine on next run)'}")

    # Env / MCP
    print("\nEnvironment:")
    pneuma_project = os.environ.get("PNEUMA_PROJECT", "")
    print(f"  PNEUMA_PROJECT : {pneuma_project or '(not set)'}")
    print(f"  SLACK enabled  : {'yes' if os.environ.get('SLACK_BOT_TOKEN') else 'no'}")
    print(f"  TEAMS enabled  : {'yes' if os.environ.get('TEAMS_CLIENT_ID') else 'no'}")

    # Miner config
    if proj:
        cfg = load_config(proj["project_path"])
        cfg_file = None
        for name in (".pneuma.yaml", ".pneuma.yml", ".pneuma.json"):
            p = Path(proj["project_path"]) / name
            if p.exists():
                cfg_file = p
                break
        print(f"\nMiner config:")
        print(f"  Source          : {cfg_file or 'defaults (no .pneuma config file)'}")
        print(f"  chunk_size      : {cfg.chunk_size}")
        print(f"  chunk_overlap   : {cfg.chunk_overlap}")
        print(f"  max_file_size   : {cfg.max_file_size:,}")
        print(f"  respect_gitignore: {cfg.respect_gitignore}")
        print(f"  extra_skip rules : {len(cfg.extra_skip)}")
        print(f"  priority rules   : {len(cfg.priority)}")

    print()


# ── show ─────────────────────────────────────────────────────────────────────

def _cmd_show(entry_id: str) -> None:
    """Print the full content + metadata of a specific entry by ID."""
    from core.palace import list_wings, list_rooms
    from mempalace.searcher import search_memories
    from core.palace import _get_config

    wings = list_wings()
    if not wings:
        print("Palace is empty.")
        return

    # Walk every room looking for the drawer ID. MemPalace doesn't expose a
    # direct "get by ID" in the tools we use, so we scan a few results per
    # room using a broad query.
    found = None
    for wing_name in wings:
        rooms = list_rooms(wing=wing_name)
        for room_name in rooms:
            try:
                results = search_memories(
                    "",  # empty query → ChromaDB returns any results ordered however it likes
                    palace_path=_get_config().palace_path,
                    wing=wing_name,
                    room=room_name,
                    n_results=100,
                )
            except Exception:
                continue
            for hit in (results or {}).get("results", []):
                hit_id = hit.get("drawer_id") or hit.get("id") or hit.get("entry_id")
                if hit_id == entry_id:
                    found = (wing_name, room_name, hit)
                    break
            if found:
                break
        if found:
            break

    if not found:
        print(f"Entry not found: {entry_id}")
        print("Tip: search for the content first, then use the ID shown in results.")
        sys.exit(1)

    wing, room, hit = found
    print(f"\n┌─ Entry: {entry_id}")
    print(f"│  Wing/Room: {wing}/{room}")
    meta = {k: v for k, v in hit.items() if k not in {"text", "content", "drawer_id"}}
    if meta:
        print("│  Metadata:")
        for k, v in meta.items():
            if isinstance(v, (str, int, float, bool)):
                print(f"│    {k}: {v}")
    print("└─\n")
    content = hit.get("text") or hit.get("content") or "(empty)"
    print(content)
    print()


# ── recent ───────────────────────────────────────────────────────────────────

def _cmd_recent(last_n: int, wing_filter: str | None) -> None:
    """List recently-ingested entries across the palace."""
    from core.palace import list_wings, list_rooms, recall

    wings = list_wings()
    if not wings:
        print("Palace is empty.")
        return

    targets = [wing_filter] if wing_filter else list(wings.keys())

    print(f"\nRecent entries{' in ' + wing_filter if wing_filter else ''} (up to {last_n}):\n")
    shown = 0
    for wing_name in targets:
        if wing_name not in wings:
            continue
        rooms = list_rooms(wing=wing_name)
        for room_name in rooms:
            if shown >= last_n:
                break
            try:
                text = recall(wing=wing_name, room=room_name, n_results=max(1, (last_n - shown) // max(1, len(rooms))))
            except Exception:
                continue
            if text and text.strip():
                preview = text.strip().splitlines()[:3]
                preview_text = " / ".join(p[:80] for p in preview if p.strip())
                print(f"  [{wing_name}/{room_name}]  {preview_text[:150]}")
                shown += 1
        if shown >= last_n:
            break

    if shown == 0:
        print("  (no content found)")
    print()


# ── reset ────────────────────────────────────────────────────────────────────

def _cmd_reset(path: str, confirm: bool = True) -> None:
    """Delete a project's palace completely (with confirmation)."""
    import shutil
    from core.registry import get_project, resolve_project, REGISTRY_FILE, _load_registry, _save_registry

    path = os.path.abspath(path)
    proj = get_project(path) or resolve_project(path)

    if not proj:
        print(f"No palace registered for: {path}")
        sys.exit(1)

    palace_dir = proj["palace_dir"]
    project_path = proj["project_path"]

    print(f"\nThis will permanently delete:")
    print(f"  Project  : {project_path}")
    print(f"  Palace   : {palace_dir}")
    print(f"  (all embeddings, knowledge graph, diary, mine state)\n")

    if confirm:
        answer = input("Type the project slug to confirm: ").strip()
        if answer != proj["slug"]:
            print("Confirmation did not match. Aborted.")
            sys.exit(1)

    # Delete palace directory
    try:
        shutil.rmtree(palace_dir, ignore_errors=True)
    except Exception as exc:
        print(f"Warning: could not fully remove {palace_dir}: {exc}")

    # Remove from registry
    reg = _load_registry()
    reg.pop(project_path, None)
    _save_registry(reg)

    print(f"\nPalace deleted. Run `pneuma init {project_path}` to start over.\n")


# ── config ───────────────────────────────────────────────────────────────────

def _cmd_config(args) -> None:
    """Handle config subcommands."""
    action = getattr(args, "config_action", None)
    if action == "show":
        _cmd_config_show()
    elif action == "init":
        _cmd_config_init(args.format)
    else:
        print("Usage: pneuma config {show|init}")
        sys.exit(1)


def _cmd_config_show() -> None:
    from core.auto_init.miner_config import load_config
    from core.registry import resolve_project

    proj = resolve_project()
    project_path = proj["project_path"] if proj else os.getcwd()
    cfg = load_config(project_path)

    # Find which config file (if any) was used
    from pathlib import Path
    source = "(defaults only — no .pneuma.yaml/.json found)"
    for name in (".pneuma.yaml", ".pneuma.yml", ".pneuma.json"):
        p = Path(project_path) / name
        if p.exists():
            source = str(p)
            break

    print(f"\nEffective miner config for: {project_path}")
    print(f"Source: {source}\n")
    print(f"  workers            : {cfg.workers}")
    print(f"  chunk_size         : {cfg.chunk_size}")
    print(f"  chunk_overlap      : {cfg.chunk_overlap}")
    print(f"  max_file_size      : {cfg.max_file_size:,}")
    print(f"  max_files          : {cfg.max_files:,}")
    print(f"  respect_gitignore  : {cfg.respect_gitignore}")
    print(f"  gitignore patterns : {len(cfg.gitignore_patterns)}")
    print(f"  extra_skip         : {cfg.extra_skip or '(none)'}")
    print(f"  priority           : {cfg.priority or '(none)'}")
    print(f"  generated patterns : {len(cfg.generated_patterns)} (first 5: {cfg.generated_patterns[:5]})")
    print()


def _cmd_config_init(fmt: str) -> None:
    from pathlib import Path

    # Determine target file
    if fmt == "yaml":
        try:
            import yaml  # noqa: F401
        except ImportError:
            print("PyYAML not installed — falling back to .pneuma.json.")
            print("Install with: pip install -e .[yaml]\n")
            fmt = "json"

    target = Path(".pneuma.yaml" if fmt == "yaml" else ".pneuma.json")
    if target.exists():
        print(f"{target} already exists. Refusing to overwrite.")
        sys.exit(1)

    if fmt == "yaml":
        content = """\
# .pneuma.yaml — miner configuration for this project
# Edit the values below, then run `pneuma config show` to verify.
# Full reference: docs/mining.md

miner:
  # ── Parallelism ────────────────────────────────────────────────────────────
  # Raise for large codebases to speed up the first mine.
  workers: 4

  # ── Chunking (char-based fallback only) ────────────────────────────────────
  chunk_size: 1500
  chunk_overlap: 150

  # ── File limits ────────────────────────────────────────────────────────────
  max_file_size: 100000
  max_files: 5000

  # ── Gitignore integration ──────────────────────────────────────────────────
  respect_gitignore: true

  # ── Skip patterns (gitignore-style globs) ─────────────────────────────────
  # skip:
  #   - "third_party/**"
  #   - "vendor/**"
  #   - "**/*_generated.*"

  # ── Generated-file patterns (replaces built-in list if set) ───────────────
  # generated:
  #   - "*.pb.go"
  #   - "*-bundle.js"

  # ── Priority — matching files are mined first ──────────────────────────────
  # priority:
  #   - "README.md"
  #   - "docs/**"
"""
    else:
        content = json.dumps({
            "miner": {
                "workers": 4,
                "chunk_size": 1500,
                "chunk_overlap": 150,
                "max_file_size": 100000,
                "max_files": 5000,
                "respect_gitignore": True,
                "skip": [],
                "priority": [],
            }
        }, indent=2)

    target.write_text(content, encoding="utf-8")
    print(f"Created {target.resolve()}")
    print("Edit it to customize chunking, skip patterns, and priority ordering.")
    print("Run `pneuma config show` to see the effective resolved config.")


# ── test-slack ───────────────────────────────────────────────────────────────

def _cmd_test_slack() -> None:
    """End-to-end verify the Slack integration."""
    import os as _os
    token = _os.getenv("SLACK_BOT_TOKEN", "")
    user_token = _os.getenv("SLACK_USER_TOKEN", "")
    allowed = _os.getenv("ALLOWED_CHANNELS", "")
    default_channel = _os.getenv("SLACK_DEFAULT_CHANNEL", "")

    print("\nSlack integration test\n---")

    if not token:
        print("  FAIL: SLACK_BOT_TOKEN is not set")
        print("        Configure in .env — see docs/getting-started.md step 5")
        sys.exit(1)
    print(f"  OK  : SLACK_BOT_TOKEN is set")

    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
    except ImportError:
        print("  FAIL: slack-sdk not installed (run `pip install -e .`)")
        sys.exit(1)

    client = WebClient(token=token)
    try:
        auth = client.auth_test()
        print(f"  OK  : auth OK — bot '{auth['user']}' in team '{auth['team']}'")
    except SlackApiError as e:
        print(f"  FAIL: auth_test failed: {e.response.get('error')}")
        sys.exit(1)

    # Check scopes by attempting restricted operations
    try:
        client.conversations_list(types="private_channel", limit=1)
        print(f"  WARN: bot CAN list private channels — revoke 'groups:read' scope")
    except SlackApiError as e:
        if "missing_scope" in str(e):
            print(f"  OK  : bot cannot access private channels")

    # Test user token if set (needed for check_recent_chat)
    if user_token:
        try:
            user_client = WebClient(token=user_token)
            user_client.search_messages(query="test", count=1)
            print(f"  OK  : SLACK_USER_TOKEN valid (search.messages works)")
        except SlackApiError as e:
            print(f"  FAIL: user token search failed: {e.response.get('error')}")
    else:
        print(f"  WARN: SLACK_USER_TOKEN not set — `check_recent_chat` will be unavailable")

    # Try posting to default channel
    if default_channel:
        try:
            resp = client.chat_postMessage(
                channel=default_channel,
                text="_Pneuma test message — safe to delete._",
            )
            if resp.get("ok"):
                print(f"  OK  : posted test message to channel {default_channel}")
                # Try to delete it so we don't pollute the channel
                try:
                    client.chat_delete(channel=default_channel, ts=resp["ts"])
                    print(f"  OK  : test message deleted")
                except Exception:
                    print(f"        (could not auto-delete — please remove it manually)")
            else:
                print(f"  FAIL: post failed: {resp.get('error')}")
        except SlackApiError as e:
            print(f"  FAIL: chat_postMessage failed: {e.response.get('error')}")
            if "not_in_channel" in str(e):
                print(f"        Invite the bot: /invite @YourBot in the channel")
    else:
        print(f"  WARN: SLACK_DEFAULT_CHANNEL not set — `ask_team` will require explicit channel")

    # Check allowed channels
    if not allowed:
        print(f"  WARN: ALLOWED_CHANNELS not set — `ingest_slack_channel` will reject all channels")
    else:
        count = len([c for c in allowed.split(",") if c.strip()])
        print(f"  OK  : ALLOWED_CHANNELS has {count} channel(s) configured")

    print("\nSlack integration looks good.\n")


# ── test-teams ───────────────────────────────────────────────────────────────

def _cmd_test_teams() -> None:
    """End-to-end verify the Teams integration."""
    import os as _os
    import json as _json
    import urllib.parse
    import urllib.request

    client_id = _os.getenv("TEAMS_CLIENT_ID", "")
    client_secret = _os.getenv("TEAMS_CLIENT_SECRET", "")
    tenant_id = _os.getenv("TEAMS_TENANT_ID", "")
    team_id = _os.getenv("TEAMS_TEAM_ID", "")
    allowed = _os.getenv("TEAMS_ALLOWED_CHANNEL_IDS", "")
    default_webhook = _os.getenv("TEAMS_DEFAULT_WEBHOOK_URL", "")
    escalation_webhook = _os.getenv("TEAMS_ESCALATION_WEBHOOK_URL", "")

    print("\nMicrosoft Teams integration test\n---")

    if not client_id:
        print("  FAIL: TEAMS_CLIENT_ID is not set")
        print("        Configure in .env — see docs/teams-setup.md")
        sys.exit(1)
    print(f"  OK  : TEAMS_CLIENT_ID is set")

    missing = [v for v in ("TEAMS_CLIENT_SECRET", "TEAMS_TENANT_ID") if not _os.getenv(v, "")]
    if missing:
        print(f"  FAIL: missing: {', '.join(missing)}")
        sys.exit(1)
    print(f"  OK  : TEAMS_CLIENT_SECRET + TEAMS_TENANT_ID set")

    # Try to acquire a token
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }).encode()
    req = urllib.request.Request(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            token_resp = _json.loads(resp.read())
    except Exception as exc:
        print(f"  FAIL: could not reach Azure AD token endpoint: {exc}")
        sys.exit(1)

    token = token_resp.get("access_token")
    if not token:
        print(f"  FAIL: token request rejected: {token_resp.get('error_description', token_resp.get('error', 'unknown'))}")
        sys.exit(1)
    print(f"  OK  : acquired Graph API access token")

    # Test reading a channel if team_id + at least one allowed channel is set
    if team_id and allowed:
        first_channel = allowed.split(",")[0].strip()
        req = urllib.request.Request(
            f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels/{first_channel}/messages?$top=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                _json.loads(resp.read())
            print(f"  OK  : can read channel {first_channel}")
        except Exception as exc:
            print(f"  FAIL: reading channel {first_channel} failed: {exc}")
            print(f"        Check ChannelMessage.Read.All scope has admin consent")
    elif not team_id:
        print(f"  WARN: TEAMS_TEAM_ID not set — ingestion won't have a default team")
    else:
        print(f"  WARN: TEAMS_ALLOWED_CHANNEL_IDS empty — ingest tool will reject all channels")

    # Test webhooks
    for label, url in (("default", default_webhook), ("escalation", escalation_webhook)):
        if not url:
            print(f"  WARN: TEAMS_{label.upper()}_WEBHOOK_URL not set")
            continue
        try:
            payload = {
                "@type": "MessageCard",
                "@context": "https://schema.org/extensions",
                "text": f"_Pneuma test ({label} webhook) — safe to delete._",
            }
            req = urllib.request.Request(
                url,
                data=_json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode().strip()
            if body == "1":
                print(f"  OK  : {label} webhook posts successfully")
            else:
                print(f"  WARN: {label} webhook returned '{body}' (expected '1')")
        except Exception as exc:
            print(f"  FAIL: {label} webhook post failed: {exc}")

    print("\nTeams integration looks good.\n")


# ── logs ─────────────────────────────────────────────────────────────────────

def _log_file_path() -> "Path":
    from core.registry import PNEUMA_HOME
    from pathlib import Path as _Path
    return _Path(PNEUMA_HOME) / "mcp-server.log"


def _cmd_logs(lines: int, follow: bool) -> None:
    from pathlib import Path
    import time

    log_path = _log_file_path()
    if not log_path.exists():
        print(f"No log file yet at: {log_path}")
        print("The MCP server writes to this file when it runs under your IDE.")
        return

    # Show last N lines
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        tail = all_lines[-lines:] if lines > 0 else all_lines
        sys.stdout.write("".join(tail))
    except Exception as exc:
        print(f"Could not read log: {exc}")
        sys.exit(1)

    if not follow:
        return

    # Follow
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)  # end
            print("\n(following — Ctrl+C to stop)")
            while True:
                line = f.readline()
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                else:
                    time.sleep(0.5)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
