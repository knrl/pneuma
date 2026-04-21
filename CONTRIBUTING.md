# Contributing to Pneuma

Thank you for your interest in contributing! Here's everything you need to know.

---

## Getting Set Up

```bash
git clone https://github.com/knrl/pneuma.git
cd pneuma
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Run the test suite to confirm everything works:

```bash
pytest tests/ -v
```

---

## Workflow

1. **Fork** the repository
2. **Create a branch** off `main`: `git checkout -b feat/your-feature`
3. **Make your changes** and add tests where appropriate
4. **Run the tests**: `pytest tests/ -v`
5. **Open a pull request** against `main` with a clear description of what changed and why

---

## Areas Where Contributions Are Welcome

| Area | Ideas |
|---|---|
| **IDE integrations** | JetBrains, Neovim, Zed |
| **Ingestion sources** | GitHub Discussions, Linear, Notion, Teams |
| **Noise filtering** | Better heuristics for signal vs. noise classification |
| **Project templates** | New `pneuma init` templates for more project types |
| **Test coverage** | More unit and integration tests |
| **Documentation** | Clearer explanations, examples, typo fixes |

---

## Project Structure

```
core/           # Core engine (palace adapter, CLI, auto-init, auto-org, ingestion, RAG)
mcp_server/     # MCP server and 20 tool implementations
chat_bot/       # Slack preprocessing pipeline
tests/          # Test suite
docs/           # Documentation
scripts/        # Utility scripts
```

See [Technical Reference](docs/Technical_Documentation.md) for a full module breakdown.

---

## Code Style

- Python 3.10+
- No external LLM calls inside Pneuma — noise filtering and routing are rule-based
- All storage must go through `core/palace.py` — no direct `mempalace` or `chromadb` imports elsewhere
- PII must be stripped before anything reaches the knowledge base
- Keep the MCP server free of business logic — tools should delegate to `core/`

---

## Reporting Bugs

Open a GitHub issue with:

- Your OS and Python version
- The output of `pneuma doctor`
- Steps to reproduce
- Expected vs. actual behavior

---

## Security Issues

Please do **not** open a public issue for security vulnerabilities. Email the maintainers directly or use GitHub's private vulnerability reporting.
