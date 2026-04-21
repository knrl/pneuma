# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 1.0.x   | ✅        |
| < 1.0   | ❌        |

## Reporting a Vulnerability

If you discover a security vulnerability in Pneuma, please report it privately — **do not open a public GitHub issue**.

**Preferred channel:** [GitHub Security Advisories](https://github.com/knrl/pneuma/security/advisories/new) (private).

**Alternate channel:** email the maintainer at `kaanerol299@gmail.com` with subject line `[pneuma-security] <short summary>`.

Please include:

- A description of the issue and its potential impact.
- Steps to reproduce (proof-of-concept, affected version/commit, configuration).
- Any suggested remediation, if known.

### What to expect

- **Acknowledgement** within 72 hours.
- **Initial triage** (severity + scope) within 7 days.
- **Fix timeline** — communicated after triage; critical issues prioritized.
- **Coordinated disclosure** — we'll agree on a disclosure date with the reporter once a fix is ready.

We will credit reporters in release notes unless they prefer to remain anonymous.

## Scope

In scope:

- The Pneuma MCP server and its exposed tools (`mcp_server/`).
- The ingestion pipeline, RAG retriever, and auto-organization engine (`core/`).
- Chat integrations (Slack, Teams) and their preprocessing (`chat_bot/`).
- Prompt-injection and data-exfiltration vectors in any component that processes untrusted input.
- Credential handling and `.env` / config loading.

Out of scope:

- Vulnerabilities in third-party dependencies (report upstream — we'll bump versions once patched).
- Issues requiring privileged local access the attacker already has (e.g. reading files owned by the user running Pneuma).
- Social-engineering or physical attacks.

## Hardening Checklist

Operators deploying Pneuma should review [docs/security_audit_checklist.md](docs/security_audit_checklist.md), which covers:

- Data boundaries (local storage, `.env` hygiene, no raw-message persistence).
- Slack/Teams bot scopes and channel allowlists.
- MCP input sanitization and hidden-tool gating.
- Prompt-injection test coverage.
- Network-egress verification (`scripts/verify_no_egress.py`).
- Auto-organization safety (no destructive operations exposed to agents).

## Secrets & Configuration

- Never commit `.env`, credentials, or tokens. See [.env.example](.env.example) and [.pneuma.yaml.example](.pneuma.yaml.example) for the expected shape.
- Rotate any secret that has been pasted into a chat, log, or public issue.
- Pneuma does not transmit user data to external LLMs during ingestion or retrieval unless the operator explicitly configures it.
