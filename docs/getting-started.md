# Getting Started with Pneuma

```bash
pip install -e .                         # 1. install
cp .env.example .env  # edit tokens      # 2. configure
pneuma quickstart /path/to/your/project  # 3. everything else
```

---

## Step 1 — Install

Pneuma is a standalone tool — install it once, outside your project.

**macOS / Linux**
```bash
cd ~/tools
git clone https://github.com/knrl/pneuma.git && cd pneuma
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

**Windows (PowerShell)**
```powershell
cd ~\tools
git clone https://github.com/knrl/pneuma.git; cd pneuma
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e .
```

> If PowerShell blocks scripts: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

Then add the venv `bin/` (or `Scripts/`) directory to your PATH so `pneuma` works from any directory.

---

## Step 2 — Configure `.env`

```bash
cp .env.example .env
```

Fill in tokens for the platforms you use. For IDE-only use (no Slack/Teams), the file can stay mostly empty. See [Configuration](configuration.md) for all variables.

---

## Step 3 — Run Quickstart

```bash
pneuma quickstart /path/to/your/project
```

Quickstart will:
1. Scaffold `.pneuma.yaml` and pause so you can tune skip patterns and worker count before mining starts
2. Mine the codebase and create the palace
3. Auto-detect your IDE (VS Code, Cursor, Claude Code) and write the MCP config
4. Run `pneuma doctor` to verify everything

Restart your IDE when done. Pass `-y` to skip the config prompt (CI), or `--ide vscode|cursor|claude-code` to force a specific IDE.

---

## Optional: Initialize Project Identity (Only Once)

On your first session after quickstart. Ask the AI agent to call `initialize_project` in the chat:

The agent will inspect the palace structure, then write a short description of the project to `~/.mempalace/identity.txt`. This description is loaded at the top of every future `wake_up` call so the agent knows what the project is without re-reading everything each session.

---

## Optional: Import Existing Knowledge

```bash
pneuma import docs/architecture.md
pneuma import slack_export.json --type chat-history
pneuma import --text "We use PostgreSQL because of JSONB support"
```

See [On-Demand Import](features/on-demand-import.md) for full options.

---

## Optional: Connect Slack or Teams

- **Slack** — see [Slack Integration](features/slack-integration.md) for app creation, OAuth scopes, and environment variables
- **Teams** — see [Teams Setup](teams-setup.md) for Azure AD app registration and Graph API permissions
