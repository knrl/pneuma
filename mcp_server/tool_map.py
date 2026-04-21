"""
Pneuma v1.0 — MCP Tool Map

Documents which tools are exposed through the unified Pneuma MCP
server.  All storage goes through MemPalace — Pneuma never touches
ChromaDB directly.

Recommended usage flow:
  Session start : wake_up → recall (if needed)
  User question : search_memory → answer (or escalate_to_human)
  New knowledge : save_knowledge (auto-dedup, auto-route)
  Reflection    : write_diary

┌──────────────────────────────────────────────────────────────────┐
│  EXPOSED (up to 21 tools — 17 core + 4 chat conditional)        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Memory tools (mcp_server/tools/memory_tools.py) — 9 tools      │
│    wake_up             — load L0+L1 identity/story context      │
│    recall              — L2 on-demand retrieval by wing/room    │
│    search_memory       — semantic search (+ group_by_location)  │
│    save_knowledge      — store with auto-route + auto-dedup     │
│    palace_overview     — status/taxonomy/graph/KG stats         │
│    mine_codebase       — embed source files (incremental)       │
│    optimize_memory     — trigger dedup + stale cleanup          │
│    delete_entry        — delete an entry by ID                  │
│    initialize_project  — one-time post-quickstart setup:        │
│                          inspect palace, write identity.txt     │
│                                                                  │
│  Knowledge Graph (mcp_server/tools/kg_tools.py) — 3 tools       │
│    track_fact          — record a temporal fact/relationship     │
│    query_facts         — look up entity relationships/timeline  │
│    invalidate_fact     — mark a fact as no longer true           │
│    (KG stats → palace_overview(detail="full"))                  │
│                                                                  │
│  Navigation (mcp_server/tools/nav_tools.py) — 2 tools           │
│    explore_palace      — walk the palace graph from a room      │
│    find_bridges        — discover cross-wing bridge rooms       │
│                                                                  │
│  Diary (mcp_server/tools/diary_tools.py) — 2 tools              │
│    write_diary         — agent's personal journal entry         │
│    read_diary          — read recent diary entries              │
│                                                                  │
│  Import (mcp_server/tools/import_tools.py) — 1 tool             │
│    import_content      — import file or pasted text             │
│                                                                  │
│  Chat (mcp_server/tools/chat_unified.py) — 4 tools              │
│    (registered when SLACK_BOT_TOKEN or TEAMS_CLIENT_ID is set;  │
│     each tool takes platform="slack|teams|auto")                │
│                                                                  │
│    check_recent_chat   — search chat history for a topic        │
│    ask_team            — post a question; target is channel ID │
│                          (Slack) or webhook URL (Teams)         │
│    ingest_chat_channel — on-demand channel backfill             │
│    escalate_to_human   — route unanswerable Qs to chat          │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│  PROMPTS (reference material, not tools)                        │
├──────────────────────────────────────────────────────────────────┤
│    memory_dialect      — AAAK compressed memory specification   │
│    capture_guidelines  — when/how to call import_content        │
│                          autonomously (loaded via wake_up hint) │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│  HIDDEN (handled internally, never exposed via MCP)             │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Auto-init    — palace initialization runs via CLI only         │
│  Auto-router  — content routing is automatic on save            │
│  Auto-dedup   — duplicate check runs automatically on save      │
│  Refactor     — dedup/stale runs on-demand via                  │
│                 optimize_memory or CLI `pneuma optimize`        │
│  Palace adapter — core/palace.py wraps MemPalace API            │
│  Platform backends — chat_tools, slack_ingest_tools,            │
│                      teams_chat_tools, teams_ingest_tools,      │
│                      escalation (delegated to by chat_unified)  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
"""

# This module is documentation-only; no runtime code.
