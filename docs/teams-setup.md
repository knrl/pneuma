# Microsoft Teams Setup

This guide sets up Pneuma's Teams integration. Once configured, Teams works through the **same four MCP tools** as Slack, behind a unified platform-agnostic surface:

| Tool | Call for Teams |
|---|---|
| `ingest_chat_channel` | `platform="teams"` — fetch channel history via Graph API |
| `check_recent_chat` | `platform="teams"` — search recent channel messages |
| `ask_team` | `platform="teams"` — post via incoming webhook |
| `escalate_to_human` | `platform="teams"` — route via escalation webhook |

When `platform="auto"`, Pneuma uses whichever backend is configured (Slack preferred if both are set).

---

## Overview

Teams integration uses two separate mechanisms:

| Feature | Mechanism | Credentials needed |
|---|---|---|
| Reading messages (ingestion + search) | Microsoft Graph API (app-only) | Azure AD app: `CLIENT_ID`, `CLIENT_SECRET`, `TENANT_ID` |
| Posting messages (ask + escalate) | Incoming Webhook URL | Webhook URL created per-channel in Teams |

---

## Part 1 — Azure AD App (for reading)

### Step 1a. Register an app

1. Go to [portal.azure.com](https://portal.azure.com) → **Azure Active Directory → App registrations → New registration**
2. Name: `Pneuma` (or any name)
3. Supported account types: **Accounts in this organizational directory only**
4. Redirect URI: leave blank
5. Click **Register**

Copy the **Application (client) ID** and **Directory (tenant) ID** — you'll need both.

### Step 1b. Create a client secret

1. In your app → **Certificates & secrets → New client secret**
2. Description: `Pneuma`, expiry: 24 months
3. Click **Add** — copy the **Value** immediately (it won't be shown again)

### Step 1c. Configure API permissions

1. In your app → **API permissions → Add a permission → Microsoft Graph → Application permissions**
2. Add: `ChannelMessage.Read.All`
3. Click **Grant admin consent** (requires Global Admin or Teams Admin role)

> `ChannelMessage.Read.All` is a privileged permission that requires admin consent. It allows the app to read all channel messages in the tenant without a signed-in user.

### Step 1d. Find your Team ID and Channel IDs

**Team ID** — from Teams admin center or the channel URL:
```
https://teams.microsoft.com/l/channel/{channel-id}/...?groupId={team-id}
```
The `groupId` parameter is the team ID.

**Channel IDs** — from the same URL (the `{channel-id}` path segment).

Or query the Graph API directly after setting up credentials:
```bash
# List teams you have access to
curl -H "Authorization: Bearer <token>" \
  "https://graph.microsoft.com/v1.0/teams"

# List channels in a team
curl -H "Authorization: Bearer <token>" \
  "https://graph.microsoft.com/v1.0/teams/{team-id}/channels"
```

### Step 1e. Set environment variables

```bash
TEAMS_CLIENT_ID=your-app-client-id
TEAMS_CLIENT_SECRET=your-client-secret-value
TEAMS_TENANT_ID=your-tenant-id
TEAMS_TEAM_ID=your-team-id
TEAMS_ALLOWED_CHANNEL_IDS=channel-id-1,channel-id-2
```

---

## Part 2 — Incoming Webhooks (for posting)

Incoming webhooks let Pneuma post messages to a Teams channel without user interaction.

### Step 2a. Create a webhook in a channel

1. In Teams, go to the target channel
2. Click **...** (More options) → **Connectors**
3. Find **Incoming Webhook** → **Configure**
4. Name it `Pneuma`, optionally upload a logo
5. Click **Create** — copy the webhook URL

Repeat for any additional channels (e.g. a separate escalation channel).

### Step 2b. Set environment variables

```bash
TEAMS_DEFAULT_WEBHOOK_URL=https://your-org.webhook.office.com/webhookb2/...
TEAMS_ESCALATION_WEBHOOK_URL=https://your-org.webhook.office.com/webhookb2/...
```

> The escalation webhook can point to the same channel as the default, or a dedicated escalation channel.

---

## Verify

Run `pneuma doctor` — it will check that your Teams credentials are reachable and the configuration is complete.

---

## What Pneuma will NOT do

- Access private channels or group chats (only channels in `TEAMS_ALLOWED_CHANNEL_IDS`)
- Read direct messages
- Access channels in other teams not specified by `TEAMS_TEAM_ID`
- Store raw messages — only anonymized, noise-filtered problem/solution pairs
