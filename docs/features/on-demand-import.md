# On-Demand Document & Chat History Import

Import Markdown files, plain text, Slack JSON exports, and chat logs into the knowledge base. Supports auto type-detection, PII anonymization, duplicate skipping, and automatic routing.

---

## How It Works

Pneuma provides two import paths — CLI for humans, MCP tools for AI agents — both backed by the same document parser.

```
File / Text
    │
    ▼
Auto-detect type (decision, chat-history, general)
    │
    ▼
Parse into sections
    │
    ▼
┌─── chat-history? ──────────────────────┐
│   YES                     NO            │
│   ▼                       ▼             │
│   Filter noise         Check duplicates │
│   Anonymize PII        (threshold 0.9)  │
│   Extract stories                       │
│   ▼                       ▼             │
│   Inject stories       Route & store    │
└─────────────────────────────────────────┘
```

### Document Type Detection

If you don't specify the type, Pneuma auto-detects:

| Detection Signal | Classified As |
|-----------------|---------------|
| JSON array of `{user, text, ts}` objects | `chat-history` (Slack export) |
| 3+ lines matching `[timestamp] user: message` | `chat-history` (chat log) |
| Keywords: "ADR", "architecture decision", "decision record" | `decision` |
| Markdown with `## Decision` or `## Context` headings | `decision` |
| Everything else | `general` |

### Parsing Strategies

| Type | How It's Split |
|------|---------------|
| Markdown | By `##` headings — each section becomes a separate entry |
| Plain text | By double newlines (paragraphs). Short paragraphs (< 50 chars) are merged |
| Slack JSON | Parsed into `BufferedMessage` objects, run through full preprocessing pipeline |
| Chat logs | Regex-matched into messages, then preprocessed like Slack messages |

### Chat-Type Processing

Chat exports and chat logs go through the same pipeline as live Slack messages:

1. **Noise filter** — drops greetings, reactions, social chatter
2. **Anonymizer** — strips PII (user mentions → pseudonyms, emails/IPs → `[REDACTED]`)
3. **Story extractor** — converts into structured Problem/Solution pairs
4. **Injector** — stores via content router into the correct wing/room

### Decision & General Processing

Decision docs and general imports:

1. **Duplicate check** — each section is compared against existing entries (cosine similarity > 0.9 = skip)
2. **Route** — content classifier determines target wing/room (or you can override)
3. **Store** — via palace adapter with metadata (source, type, import timestamp)

## Usage

### CLI

```bash
# Import a markdown file (auto-detected as decision doc)
pneuma import architecture-decisions.md

# Import with explicit type
pneuma import decisions.md --type decision

# Import Slack JSON export
pneuma import slack_export.json --type chat-history

# Target a specific wing/room
pneuma import architecture-notes.md --wing chat --room decisions

# Import raw text directly
pneuma import --text "We decided to use PostgreSQL for the billing service"

# Import from stdin (pipe from another tool)
cat meeting-notes.txt | pneuma import --text -
```

### MCP Tools (AI Agent)

Your AI agent has one unified import tool:

**`import_content`** — Import a file or pasted text:
```
Tool: import_content
  file_path: "/path/to/decisions.md"   # provide file_path OR content
  content: ""
  doc_type: "auto"        # auto | decision | chat-history | general
  wing: ""                 # optional override
  room: ""                 # optional override
```

Or for pasted text:
```
Tool: import_content
  file_path: ""
  content: "We decided to use JWT tokens because..."
  doc_type: "decision"
  title: "Auth Token Decision"
  wing: "chat"
  room: "decisions"
```

**Agent-to-human suggestion pattern**

An AI agent in your IDE can call `import_content` directly when you paste a decision or context into the chat. For bulk file imports, use the CLI:

```bash
pneuma import architecture-decisions.md
pneuma import --text "We decided to use PostgreSQL because of JSONB support"
```

### Example Output

```
Imported: architecture-decisions.md
  Type: decision (auto-detected)
  Sections parsed: 8
  Entries stored: 7
  Duplicates skipped: 1
  Target: chat/decisions
```

## Supported Formats

| Format | Extension | Notes |
|--------|-----------|-------|
| Markdown | `.md` | Split by `##` headings |
| Plain text | `.txt` | Split by paragraphs |
| Slack JSON export | `.json` | Array of message objects |
| Chat logs | `.txt`, `.log` | `[timestamp] user: message` or `user: message` format |

## Compared to raw MemPalace

MemPalace stores drawers in wings/rooms — but it doesn't understand document formats. Without Pneuma:
- No auto-detection of document type
- No markdown section splitting
- No Slack JSON parsing
- No PII anonymization on imported content
- No duplicate detection during import
- No chat-to-story conversion for historical exports
