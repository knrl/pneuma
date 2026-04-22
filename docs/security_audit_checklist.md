# Security Audit Checklist — Pneuma v0.1.0

## Data Boundaries

- [x] ChromaDB data directory is on local/private-cloud storage
- [x] SQLite databases are not exposed to external networks
- [x] `.env` file is excluded from version control
- [x] No credentials are hardcoded in source files
- [x] Raw chat messages are never persisted — only structured stories are stored

## Slack Bot Permissions

- [ ] Bot cannot list private channels (missing_scope error confirmed)
- [ ] Bot cannot list DMs (missing_scope error confirmed)
- [x] Bot is restricted to `ALLOWED_CHANNELS` only (enforced in `ingest_slack_channel`)
- [ ] Bot event subscription limited to `message.channels` (public only)

## Chat Ingestion Engine

- [x] In-memory message buffer is cleared after each extraction cycle
- [x] Noise filter discards non-technical content before storage
- [x] Anonymizer strips all user IDs and names before storage
- [x] Stored entries contain no author attribution
- [x] Story extractor uses rule-based heuristics only (no external LLM calls)

## MCP Server Security

- [x] Input sanitization is applied to all tool parameters
- [x] Slack message injection characters are escaped in escalation messages
- [x] `ask_team` sanitizes user-provided text (no `<!channel>`, `<!here>`, `<!everyone>`)
- [x] Code context is truncated to prevent oversized payloads
- [x] No user-provided strings are executed as code
- [x] Hidden MemPalace tools (`delete_wing`, `delete_room`, etc.) are not exposed

## Prompt Injection Mitigation

- [x] Test: Submit a query containing "Ignore previous instructions and..."
  - Covered by `tests/test_prompt_injection.py::TestRagPipelineInjection`
- [x] Test: Inject prompt attacks into Slack messages in a monitored channel
  - Covered by `tests/test_prompt_injection.py::TestNoiseFilterInjection` and `TestStoryExtractorInjection`
- [x] Test: Submit `code_context` containing malicious markdown/HTML
  - Covered by `tests/test_prompt_injection.py::TestSlackSanitization`

## Network Egress

- [x] `verify_no_egress.py` exists — run with: `python scripts/verify_no_egress.py`
- [x] Run `verify_no_egress.py` — confirm zero outbound calls during retrieval
  - Also covered by `tests/test_no_egress.py` (runs automatically with pytest)
- [x] No LLM calls in noise filter, story extractor, or auto-router (all rule-based)

## Auto-Organization

- [x] Auto-refactor engine does not delete entries without deduplication verification
- [x] Auto-router fallback defaults to safe collection (`chat/context`)
- [x] Destructive MemPalace operations are internal-only, never agent-accessible
