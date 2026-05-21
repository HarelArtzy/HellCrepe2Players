from __future__ import annotations

import argparse
import asyncio

from classes import DungeonGameServer


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HellCrepe multiplayer game server")
    parser.add_argument("--host", default="0.0.0.0", help="Host/IP to bind")
    parser.add_argument("--port", type=int, default=9000, help="TCP port")
    args = parser.parse_args()

    server = DungeonGameServer(args.host, args.port, max_players=2)
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        pass

