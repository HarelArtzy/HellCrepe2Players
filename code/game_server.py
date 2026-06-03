from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
import sys
import warnings

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
warnings.filterwarnings("ignore", message="pkg_resources is deprecated as an API")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from classes.DungeonGameServer import DungeonGameServer
from env_config import MAX_PLAYERS, SERVER_HOST, SERVER_PORT


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        filename=PROJECT_ROOT / "server.log",
        filemode="a",
        force=True,
    )
    logging.captureWarnings(True)
    parser = argparse.ArgumentParser(
        description="HellCrepe multiplayer game server")
    parser.add_argument("--host", default=SERVER_HOST, help="Host/IP to bind")
    parser.add_argument("--port", type=int, default=SERVER_PORT, help="TCP port")
    parser.add_argument("--max-players", type=int, default=MAX_PLAYERS, help="Maximum number of players")
    args = parser.parse_args()

    server = DungeonGameServer(args.host, args.port, max_players=max(1, args.max_players))
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        pass
