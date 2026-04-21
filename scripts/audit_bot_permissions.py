"""
Verify the Slack bot cannot access DMs or private channels.
Run this after app installation to confirm scope boundaries.
"""

import os
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()

client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN", ""))


def audit_permissions():
    print("=" * 50)
    print("SLACK BOT PERMISSION AUDIT")
    print("=" * 50)

    # --- Check 1: List granted scopes ---
    try:
        auth = client.auth_test()
        print(f"\nBot User: {auth['user']}")
        print(f"Team: {auth['team']}")
    except SlackApiError as e:
        print(f"\nCould not authenticate: {e}")
        print("Ensure SLACK_BOT_TOKEN is set correctly in .env")
        return

    # --- Check 2: Attempt to list private channels (should fail) ---
    print("\n[Test] Attempting to list private channels...")
    try:
        client.conversations_list(types="private_channel", limit=1)
        print("  FAIL: Bot CAN list private channels! Revoke 'groups:read' scope.")
    except SlackApiError as e:
        if "missing_scope" in str(e):
            print("  PASS: Bot cannot list private channels (missing_scope).")
        else:
            print(f"  WARN: Unexpected error: {e}")

    # --- Check 3: Attempt to list DM conversations (should fail) ---
    print("\n[Test] Attempting to list DM conversations...")
    try:
        client.conversations_list(types="im", limit=1)
        print("  FAIL: Bot CAN list DMs! Revoke 'im:read' scope.")
    except SlackApiError as e:
        if "missing_scope" in str(e):
            print("  PASS: Bot cannot list DMs (missing_scope).")
        else:
            print(f"  WARN: Unexpected error: {e}")

    # --- Check 4: Verify search:read scope (needed for check_recent_chat) ---
    print("\n[Test] Checking search:read scope (Slack search API)...")
    try:
        client.api_call("search.messages", params={"query": "test", "count": 1})
        print("  PASS: Bot has search:read scope.")
    except SlackApiError as e:
        if "missing_scope" in str(e):
            print("  WARN: Bot lacks search:read scope. check_recent_chat will not work.")
            print("         Add 'search:read' in the Slack app OAuth settings.")
        else:
            print(f"  WARN: Unexpected error: {e}")

    # --- Check 5: List accessible public channels ---
    print("\n[Test] Listing accessible public channels...")
    try:
        channels = client.conversations_list(types="public_channel", limit=100)
        accessible = [ch["name"] for ch in channels.get("channels", [])]
        print(f"  Accessible public channels: {len(accessible)}")
        for ch in accessible[:10]:
            print(f"    #{ch}")
        if len(accessible) > 10:
            print(f"    ... and {len(accessible) - 10} more")
    except SlackApiError as e:
        print(f"  Could not list channels: {e}")

    print("\n" + "=" * 50)
    print("AUDIT COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    audit_permissions()
