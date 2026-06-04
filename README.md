# HellCrepe 2 Players

HellCrepe is a two-player multiplayer dungeon fighter built with Python and
pygame. Two clients connect to one game server, choose names and skins in a
lobby, ready up, and then play through dungeon levels together.

The server owns the real game state. Clients send their current input, and the
server simulates players, enemies, projectiles, levels, health, win/restart
state, and sends each client a snapshot of the world.

## Project Overview

- `code/main.py` - pygame client entrypoint.
- `code/game_server.py` - multiplayer server entrypoint.
- `code/functions.py` - client rendering, input, lobby, networking helpers.
- `classes/DungeonGameServer.py` - main server state and game simulation.
- `classes/Protocol.py` - custom TCP protocol using `len#pickle(dict)`.
- `classes/Player.py` - client-side player sprite animation.
- `classes/SimPlayer.py` - server-side player state.
- `classes/EnemyState.py` / `classes/EnemySprite.py` - enemy state and visuals.
- `settings.py` - gameplay constants and level configuration.
- `env_config.py` - loads `.env` and exposes shared config/path constants.
- `assets/` - maps, sprites, UI images, tilesets, and music.

## Networking

The project uses TCP with a small custom protocol.

Each message is a Python dictionary serialized with `pickle`, then sent as:

```text
length#pickled_data
```

The receiver reads characters until `#`, converts the header to an integer,
then reads exactly that many bytes and restores the dictionary with
`pickle.loads`.

Clients send input/lobby messages. The server stores the latest input per
player, updates the world each tick, and sends state snapshots back to each
client.

## Setup

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

Create or edit `.env` in the project root. You can copy from `.env.example`.

Important settings:

```text
SERVER_HOST=0.0.0.0
SERVER_PORT=9000
MAX_PLAYERS=2

CLIENT_SERVER_HOST=127.0.0.1
CLIENT_SERVER_PORT=9000

OLLAMA_MODEL=llama3.1:8b
```

`SERVER_PORT` is the port the server listens on. `CLIENT_SERVER_PORT` is the
port the client connects to. For local play, keep them the same.

## Running

Start the server first:

```powershell
python code\game_server.py
```

Then start two clients in two separate terminals:

```powershell
python code\main.py
```

You can override host/port from the command line:

```powershell
python code\game_server.py --host 0.0.0.0 --port 9000
python code\main.py --host 127.0.0.1 --port 9000
```

## Lobby Controls

- Type to edit player name.
- Left / Right arrows change skin.
- `R` asks a local Ollama model to generate a name.
- Enter toggles ready.

## Gameplay Controls

- `A` / Left arrow - move left.
- `D` / Right arrow - move right.
- `W` / Up arrow / Space - jump.
- Mouse - aim.
- Left mouse button - shoot.
- Escape - pause menu.

## Ollama Name Generation

The lobby can generate a player name with a local Ollama model. Make sure
Ollama is installed, running, and that the configured model exists locally.

Example:

```powershell
ollama pull llama3.1:8b
```

If Ollama is unavailable, the game falls back to a default name.

## Logs

Runtime logs are written to files instead of the console:

- `server.log`
- `client.log`

