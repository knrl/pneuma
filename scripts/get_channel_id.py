import os
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()

client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN", ""))

def get_channel_id_by_name(channel_name: str) -> str | None:
    """Return the channel ID for a given Slack channel name (public channels only)."""
    try:
        cursor = None
        while True:
            response = client.conversations_list(types="public_channel", limit=100, cursor=cursor)
            for ch in response.get("channels", []):
                if ch["name"] == channel_name:
                    return ch["id"]
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    except SlackApiError as e:
        print(f"Error fetching channels: {e}")
    return None

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python get_channel_id.py <channel-name>")
        sys.exit(1)
    channel_name = sys.argv[1].lstrip('#')
    channel_id = get_channel_id_by_name(channel_name)
    if channel_id:
        print(f"Channel ID for #{channel_name}: {channel_id}")
    else:
        print(f"Channel '{channel_name}' not found or not accessible.")
