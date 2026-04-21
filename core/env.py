"""
Centralised environment loader.

Imported once at process start by cli.py and mcp_server/server.py.
All other modules read os.environ directly — they must NOT call
load_dotenv() themselves.

The .env file is resolved relative to the Pneuma install root so the
path is always explicit, regardless of the working directory.
"""

from pathlib import Path

from dotenv import load_dotenv

# core/env.py → core/ → pneuma root
_PNEUMA_ROOT = Path(__file__).resolve().parents[1]
_DOTENV_PATH = _PNEUMA_ROOT / ".env"

load_dotenv(dotenv_path=_DOTENV_PATH)
