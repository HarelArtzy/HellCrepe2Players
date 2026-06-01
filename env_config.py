from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
ASSETS_DIR = PROJECT_ROOT / "assets"
load_dotenv(PROJECT_ROOT / ".env")


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0").strip() or "0.0.0.0"
SERVER_PORT = _get_int("SERVER_PORT", 9000)
MAX_PLAYERS = max(1, _get_int("MAX_PLAYERS", 2))

CLIENT_SERVER_HOST = (
    os.getenv("CLIENT_SERVER_HOST", "127.0.0.1").strip() or "127.0.0.1"
)
CLIENT_SERVER_PORT = _get_int("CLIENT_SERVER_PORT", SERVER_PORT)

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b").strip() or "llama3.1:8b"
