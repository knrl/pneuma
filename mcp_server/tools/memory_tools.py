"""
MCP Tools: Memory — search, save, explore, optimize, status.

Consolidated tool surface (7 tools):
  wake_up         — L0+L1 identity/story context at session start
  recall          — L2 on-demand retrieval by wing/room
  search_memory   — semantic search with optional location grouping
  save_knowledge  — store with auto-route + auto-dedup
  palace_overview — combined status/taxonomy/topics
  optimize_memory — dedup + stale cleanup
  delete_entry    — remove an entry by ID
"""

from core.rag.retriever import search_memory as _search, RetrievalResult
from core.rag.confidence import assess_confidence
from core.ingestion.pipeline import inject_entry
from core.auto_org.refactor import run_refactor, run_optimize
from core.palace import (
    list_wings,
    list_rooms,
    wake_up as _wake_up,
    recall as _recall,
    check_duplicate as _check_dup,
    delete_entry as _delete,
    get_taxonomy as _taxonomy,
    status as _status,
    aaak_spec as _aaak,
)


# ── Context bootstrap ───────────────────────────────────────────────────────

async def wake_up(wing: str = "") -> str:
    """Load core identity and essential context (~800 tokens).
    Call once at the start of every session before answering questions.
    Returns L0 identity + L1 essential memories.

    Args:
        wing: Optional wing to scope the story to a specific project.
              Leave empty for the full identity context.
    """
    import os
    from pathlib import Path
    from core.background import maybe_mine
    maybe_mine(os.environ.get("PNEUMA_PROJECT", ""))

    text = _wake_up(wing=wing or None)

    # Check whether identity.txt exists
    pneuma_home = Path(os.environ.get("PNEUMA_HOME", Path.home() / ".mempalace"))
    identity_missing = not (pneuma_home / "identity.txt").exists()

    if not text or identity_missing:
        setup_hint = (
            "\n\n---\n"
            "Project not fully initialized. Call initialize_project to complete setup: "
            "it will inspect the palace, write a project identity, and set the context "
            "for future sessions."
        )
    else:
        setup_hint = ""

    base = text or "No identity or story configured yet."
    capture_hint = (
        "\n\n---\n"
        "Capture reminder: if the user pastes a decision, workaround, or architectural "
        "context during this session, call import_content autonomously — don't wait to "
        "be asked. Use the capture_guidelines prompt for the full decision matrix."
    )
    return base + setup_hint + capture_hint


async def recall(wing: str = "", room: str = "", n_results: int = 10) -> str:
    """Retrieve context from a specific wing/room without a search query (L2 on-demand).
    Use after wake_up when you need deeper context from a known location.
    Returns recent/relevant entries from the specified palace location.

    Args:
        wing: Wing to recall from (e.g. "decisions", "code").
              Leave empty for all wings.
        room: Room within the wing (e.g. "architecture", "api").
              Leave empty for all rooms in the wing.
        n_results: Maximum entries to recall (default 10).
    """
    text = _recall(
        wing=wing or None,
        room=room or None,
        n_results=n_results,
    )
    return text or f"No entries found in wing='{wing}' room='{room}'."


# ── Search ───────────────────────────────────────────────────────────────────

async def search_memory(
    query: str,
    top_k: int = 5,
    group_by_location: bool = False,
) -> str:
    """Semantic search across all stored knowledge.
    Use when the user asks a question or you need to find relevant context.
    Returns ranked results with confidence scores; if confidence is low,
    consider using escalate_to_human.

    Args:
        query: Natural-language question or topic to search for.
        top_k: Maximum number of results to return (default 5).
        group_by_location: If true, group results by wing/room instead
                           of a flat ranked list. Useful for exploring
                           how a concept connects across domains.
    """
    results = _search(query, top_k=top_k)

    if not results:
        confidence = assess_confidence([])
        if confidence["recommendation"] == "escalate":
            return (
                "No relevant entries found in the knowledge base. "
                "Consider using escalate_to_human to ask the team."
            )
        return "No results found."

    confidence = assess_confidence(results)
    top_score = confidence["top_score"]

    if group_by_location:
        return _format_grouped(results, confidence)

    # Flat ranked list with inline confidence labels
    lines = [
        f"Found {len(results)} results "
        f"(top confidence: {_confidence_label(top_score)} {top_score:.2f}):\n"
    ]
    for i, r in enumerate(results, 1):
        label = _confidence_label(r.relevance_score)
        lines.append(
            f"--- Result {i} [{r.collection}] "
            f"[{label} {r.relevance_score:.3f}] ---"
        )
        lines.append(r.content)
        lines.append("")

    if confidence["recommendation"] == "escalate":
        lines.append(
            "⚠ Low confidence — consider verifying with the team "
            "or using escalate_to_human."
        )

    return "\n".join(lines)


def _confidence_label(score: float) -> str:
    if score >= 0.80:
        return "HIGH"
    if score >= 0.65:
        return "MED"
    return "LOW"


def _format_grouped(
    results: list[RetrievalResult],
    confidence: dict,
) -> str:
    by_location: dict[str, list[RetrievalResult]] = {}
    for r in results:
        by_location.setdefault(r.collection, []).append(r)

    top_score = confidence["top_score"]
    lines = [
        f"Found {len(results)} results across {len(by_location)} locations "
        f"(top confidence: {_confidence_label(top_score)} {top_score:.2f}):\n"
    ]
    for loc_name, entries in by_location.items():
        lines.append(f"[{loc_name}] ({len(entries)} entries)")
        for e in entries:
            label = _confidence_label(e.relevance_score)
            preview = e.content[:120].replace("\n", " ")
            lines.append(f"  • [{label} {e.relevance_score:.3f}] {preview}…")
        lines.append("")

    if confidence["recommendation"] == "escalate":
        lines.append(
            "⚠ Low confidence — consider verifying with the team "
            "or using escalate_to_human."
        )

    return "\n".join(lines)


# ── Save (with auto-dedup) ───────────────────────────────────────────────────

async def save_knowledge(
    content: str,
    wing: str = "",
    room: str = "",
    tags: str = "",
    source: str = "",
) -> str:
    """Store new knowledge with automatic routing and duplicate detection.
    Provide content only — wing/room are auto-determined from keywords.
    Override routing with explicit wing/room if you know the right location.
    Duplicates are checked automatically before saving.

    Args:
        content: The knowledge to save — a decision, solution, code
                 pattern, workaround, or any useful context.
        wing: Target wing (e.g. "decisions", "code", "chat-knowledge").
              Leave empty for auto-routing.
        room: Target room within the wing. Leave empty for auto-routing.
        tags: Optional comma-separated tags for easier retrieval.
        source: Optional source label (e.g. "slack", "copilot", "manual").
    """
    # Auto-dedup check before saving
    dup_result = _check_dup(content, threshold=0.9)
    if dup_result.get("is_duplicate"):
        matches = dup_result.get("matches", [])
        if matches:
            m = matches[0]
            return (
                f"Not saved — duplicate detected.\n"
                f"  Existing entry: [{m['wing']}/{m['room']}] "
                f"(similarity: {m['similarity']:.3f}, id: {m['id']})\n"
                f"  Content: {m['content'][:120]}…"
            )

    metadata: dict = {}
    if wing and room:
        metadata["wing"] = wing
        metadata["room"] = room
    if tags:
        metadata["tags"] = tags
    if source:
        metadata["source"] = source

    result = inject_entry(content=content, metadata=metadata)
    collection = result["collection"]

    # Parse wing/room from collection for routing feedback
    parts = collection.split("-", 1)
    routed_wing = parts[0] if parts else collection
    routed_room = parts[1] if len(parts) > 1 else ""
    routing = "explicit" if (wing and room) else "auto-routed"
    stype = result.get("semantic_type")
    type_label = f" [{stype}]" if stype else ""

    from core.background import bump_and_maybe_optimize
    bump_and_maybe_optimize()

    return (
        f"Saved to wing='{routed_wing}', room='{routed_room}'{type_label} ({routing}).\n"
        f"Entry ID: {result['entry_id']}\n"
        f"No duplicates found."
    )


# ── Status ───────────────────────────────────────────────────────────────────

async def palace_overview(detail: str = "summary") -> str:
    """Get an overview of the memory palace — what's stored and how it's organized.
    Use to understand the knowledge base before searching or saving.

    Args:
        detail: "summary" for quick stats,
                "full" for complete taxonomy + graph connectivity + KG stats.
    """
    s = _status()
    if "error" in s:
        return f"Palace not initialized: {s['error']}"

    lines = [
        "Palace overview:",
        f"  Total entries : {s.get('total_drawers', 0)}",
        f"  Wings         : {len(s.get('wings', {}))}",
        f"  Rooms         : {len(s.get('rooms', {}))}",
        f"  Path          : {s.get('palace_path', '?')}",
    ]

    if detail == "full":
        tax = _taxonomy()
        if tax:
            lines.append("\nTaxonomy:")
            total = 0
            for wing_name, rooms in sorted(tax.items()):
                wing_total = sum(rooms.values())
                lines.append(f"  [{wing_name}] ({wing_total} entries)")
                for room_name, count in sorted(rooms.items()):
                    lines.append(f"    {room_name:36s} {count:>6}")
                    total += count
            lines.append(f"\n  Total: {total}")

        # Graph connectivity
        try:
            from core.palace import palace_graph_stats
            graph = palace_graph_stats()
            if graph:
                lines.append(f"\nGraph connectivity:")
                lines.append(f"  Tunnel rooms  : {graph.get('tunnel_rooms', 0)}")
                lines.append(f"  Total edges   : {graph.get('total_edges', 0)}")
                rw = graph.get("rooms_per_wing", {})
                if rw:
                    lines.append("  Rooms per wing:")
                    for w, c in rw.items():
                        lines.append(f"    {w:30s} {c:>4}")
        except ImportError:
            pass

        # Knowledge graph stats (previously the separate knowledge_stats tool)
        try:
            from core.palace import kg_stats as _kg_stats
            kg = _kg_stats()
            if kg:
                predicates = kg.get("relationship_types", [])
                lines.append("\nKnowledge graph:")
                lines.append(f"  Entities       : {kg.get('entities', 0)}")
                lines.append(f"  Total facts    : {kg.get('triples', 0)}")
                lines.append(f"  Current facts  : {kg.get('current_facts', 0)}")
                lines.append(f"  Expired facts  : {kg.get('expired_facts', 0)}")
                if predicates:
                    lines.append(f"  Relationship types: {', '.join(predicates)}")
        except Exception:
            pass

    return "\n".join(lines)


# ── Codebase mining ──────────────────────────────────────────────────────────

async def mine_codebase(
    project_path: str = "",
    dry_run: bool = False,
    full: bool = False,
) -> str:
    """Mine the project codebase into the palace.
    Incremental by default — only re-embeds files whose content changed since
    the last mine, and deletes entries for files removed from disk.

    Args:
        project_path: Absolute path to the project root to mine.
                      Defaults to the active project configured at startup.
        dry_run: If true, report what would be mined without writing entries.
                 Useful for estimating scope and checking routing.
        full: If true, force a complete re-mine (ignore state tracking).
              Use this after major codebase changes or when state DB is suspect.
    """
    import os
    from core.auto_init.miner import mine_project

    path = project_path or os.environ.get("PNEUMA_PROJECT", "")
    if not path:
        return (
            "No project path provided and PNEUMA_PROJECT is not set. "
            "Pass an explicit project_path or configure PNEUMA_PROJECT."
        )

    from pathlib import Path
    if not Path(path).is_dir():
        return f"Directory not found: {path}"

    incremental = not full and not dry_run
    result = mine_project(path, dry_run=dry_run, incremental=incremental)

    verb = "Would mine" if dry_run else "Mined"
    store_verb = "Would store" if dry_run else "Stored"
    mode_label = "[DRY RUN] " if dry_run else ("[FULL] " if full else "[INCREMENTAL] ")

    lines = [
        f"{mode_label}{verb} codebase: {path}",
        f"  Files processed : {result.files_processed}",
        f"  {store_verb} chunks: {result.chunks_stored}",
        f"  Summaries       : {result.summaries_stored}",
        f"  Files skipped   : {result.files_skipped}",
    ]

    if incremental:
        lines.append(f"  Unchanged       : {result.files_unchanged} (hash match)")
        if result.files_removed:
            lines.append(f"  Removed         : {result.files_removed} (deleted from disk)")

    if result.skip_reasons:
        lines.append("  Skip reasons:")
        for reason, count in sorted(result.skip_reasons.items(), key=lambda x: -x[1]):
            lines.append(f"    {reason:<30} {count}")

    if dry_run and result.would_route:
        lines.append("  Would route (wing/room → chunks):")
        for loc, count in sorted(result.would_route.items(), key=lambda x: -x[1]):
            lines.append(f"    {loc:<40} {count}")

    if result.errors:
        lines.append(f"  Errors          : {len(result.errors)}")
        for err in result.errors[:5]:
            lines.append(f"    - {err}")

    # Bump auto-optimize counter by chunks stored (skip dry-runs)
    if not dry_run and result.chunks_stored > 0:
        from core.background import bump_and_maybe_optimize
        bump_and_maybe_optimize(n=result.chunks_stored + result.summaries_stored)

    return "\n".join(lines)


# ── Maintenance ──────────────────────────────────────────────────────────────

async def optimize_memory(dry_run: bool = False, level: str = "standard") -> str:
    """Deduplicate, clean stale entries, check index health, detect contradictions.
    Run after bulk imports or when search results feel noisy.
    Not needed every session — once a week or after major ingestion events.

    Args:
        dry_run: If true, report what would change without writing.
                 Useful before running destructive cleanup.
        level: "standard" (dedup + stale + index health + fact check + indexing status)
               or "deep" (adds AAAK compression, index rebuild, migration, cache clear).
               "deep" is forced to dry_run=True via MCP — use CLI for destructive deep runs.

    Returns:
        Summary of all optimization stages.
    """
    # Guard: deep level via MCP is always dry-run to prevent agents from
    # autonomously triggering destructive operations (index rebuild, migration).
    # Use `pneuma optimize --level deep` from CLI for actual deep runs.
    if level == "deep" and not dry_run:
        dry_run = True
        forced_dry = True
    else:
        forced_dry = False

    report = run_optimize(dry_run=dry_run, level=level)
    prefix = "[DRY RUN] " if dry_run else ""
    mode = f"[{level.upper()}] " if level != "standard" else ""

    lines = [f"{prefix}{mode}Optimization complete:"]

    # Stage 1: Dedup
    merge_label = "Would merge" if dry_run else "Duplicates merged"
    lines.append(f"  {merge_label:<22}: {report.duplicates_merged}")

    # Stage 2: Stale
    stale_label = "Would delete (stale)" if dry_run else "Stale entries deleted"
    lines.append(f"  {stale_label:<22}: {report.stale_removed}")

    lines.append(f"  Collections scanned  : {report.collections_scanned}")

    # Stage 3: Index health
    if report.index_corrupt_found > 0:
        if dry_run:
            lines.append(f"  Corrupt IDs found    : {report.index_corrupt_found} (would prune)")
        else:
            lines.append(f"  Corrupt IDs pruned   : {report.index_corrupt_pruned}")
    else:
        lines.append(f"  Index health         : clean")

    # Stage 4: Contradictions
    if report.contradictions:
        lines.append(f"  Contradictions       : {len(report.contradictions)} found")
        for c in report.contradictions[:5]:
            lines.append(f"    [{c['type']}] {c.get('detail', '')}")
    else:
        lines.append(f"  Contradictions       : none")

    # Stage 5: Indexing status
    pct = round(report.indexing_progress * 100)
    lines.append(f"  Indexing status      : {pct}% ({report.unindexed_ops} unindexed)")

    # Deep stages
    if level == "deep":
        lines.append(f"  Entries compressed   : {report.entries_compressed}")
        lines.append(f"  Index rebuilt        : {'yes' if report.index_rebuilt else 'no (dry-run)' if dry_run else 'no'}")
        lines.append(f"  Migration needed     : {'yes' if report.migration_needed else 'no'}")
        if report.migration_needed:
            lines.append(f"  Migration done       : {'yes' if report.migration_done else 'no (dry-run)' if dry_run else 'no'}")

    # Dry-run details
    if dry_run and report.would_merge:
        lines.append("  Proposed merges:")
        for m in report.would_merge[:5]:
            lines.append(f"    source={m['source']}, drop {m['drop_count']} duplicates")

    if dry_run and report.would_archive:
        lines.append("  Stale to delete:")
        for s in report.would_archive[:5]:
            lines.append(f"    [{s['wing']}/{s['room']}] {s['drawer_id']} ({s['age_days']}d old)")

    if dry_run and report.would_prune:
        lines.append(f"  Corrupt IDs to prune : {len(report.would_prune)}")

    if report.errors:
        lines.append(f"  Errors               : {len(report.errors)}")
        for err in report.errors[:5]:
            lines.append(f"    - {err}")

    if dry_run:
        lines.append("\n  [DRY RUN] Nothing was written.")
        if forced_dry:
            lines.append(
                "  Note: deep optimization is restricted to dry-run via MCP. "
                "Use `pneuma optimize --level deep` from CLI to apply."
            )

    return "\n".join(lines)


async def delete_entry(entry_id: str) -> str:
    """Delete a specific entry from the knowledge base by its ID.
    Use to remove incorrect, outdated, or duplicate entries.

    Args:
        entry_id: The ID of the entry to delete (shown in search results
                  and save confirmations).
    """
    result = _delete(entry_id)
    if result.get("success"):
        return f"Deleted entry: {entry_id}"
    return f"Failed to delete: {result.get('error', 'unknown error')}"


# ── Project initialization ───────────────────────────────────────────────────

async def initialize_project(identity: str = "") -> str:
    """One-time setup after pneuma quickstart: write a project identity and confirm palace structure.
    Call this once at the start of the first session, when wake_up reports no identity configured.
    The agent inspects the palace overview, then writes a concise identity description.

    If you call this without the identity argument first, the tool returns a summary of the
    palace structure so you can compose an appropriate identity description, then call again
    with the identity argument to write it.

    Args:
        identity: A short description of the project and the agent's role (2-5 sentences).
                  Example: "I am the coding assistant for the iclbase project. The codebase
                  is a C++ database connectivity library with drivers for PostgreSQL, ODBC,
                  OCI, SAP, and RabbitMQ. Conventions: snake_case, no exceptions across
                  module boundaries, all public APIs documented."
                  Leave empty to first inspect the palace and get a summary to base the
                  identity on.
    """
    import os
    from pathlib import Path

    pneuma_home = Path(os.environ.get("PNEUMA_HOME", Path.home() / ".mempalace"))
    identity_path = pneuma_home / "identity.txt"

    # Phase 1: no identity provided — return palace overview for the agent to inspect
    if not identity.strip():
        s = _status()
        if "error" in s:
            return (
                "Palace not initialized yet. Run `pneuma quickstart` first, "
                "then call initialize_project again."
            )

        tax = _taxonomy()
        lines = [
            "Palace is ready. Here is its structure — use this to write a project identity:",
            f"  Total entries : {s.get('total_drawers', 0)}",
            f"  Wings         : {len(s.get('wings', {}))}",
            f"  Path          : {s.get('palace_path', '?')}",
        ]
        if tax:
            lines.append("\nWings and rooms:")
            for wing_name, rooms in sorted(tax.items()):
                wing_total = sum(rooms.values())
                lines.append(f"  [{wing_name}] ({wing_total} entries)")
                for room_name, count in sorted(rooms.items()):
                    if count > 0:
                        lines.append(f"    {room_name:36s} {count:>6} entries")

        already = ""
        if identity_path.exists():
            already = f"\n\nCurrent identity.txt:\n{identity_path.read_text(encoding='utf-8').strip()}"

        lines.append(
            "\n---"
            "\nNow call initialize_project(identity=\"...\") with a 2-5 sentence description of:"
            "\n  - What the project is"
            "\n  - Primary language(s) and any key frameworks"
            "\n  - Coding conventions the agent should follow"
            "\n  - Your role as the AI assistant for this project"
        )
        return "\n".join(lines) + already

    # Phase 2: identity provided — write it
    try:
        pneuma_home.mkdir(parents=True, exist_ok=True)
        identity_path.write_text(identity.strip() + "\n", encoding="utf-8")
    except OSError as exc:
        return f"Failed to write identity file: {exc}"

    return (
        f"Identity written to {identity_path}\n"
        f"\nContent:\n{identity.strip()}\n"
        f"\nThis will be loaded at the start of every future session via wake_up. "
        f"Run wake_up now to verify."
    )
