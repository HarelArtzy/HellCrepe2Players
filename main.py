# main.py
# /// script
# dependencies = [
#   "pygame-ce",
#   "pytmx",
#   "websockets",
# ]
# ///

import argparse
import asyncio
import json
import sys
from contextlib import suppress
from pathlib import Path

import pygame

from classes import Amrany, Cookie, Pancake, Player, Waffle
from functions import calc_view, draw_tmx, load_level
from settings import BASE_H, BASE_W, FPS, MAP_DICT, STARTING_LVL


WINDOW_W = 1920
WINDOW_H = 1080
UI_W = 1280
UI_H = 720


def level_key(level: int) -> str:
    return f"lvl{level}"


def is_web_runtime() -> bool:
    return sys.platform in ("emscripten", "wasi")


def get_browser_location() -> tuple[str, str] | None:
    try:
        import js  # type: ignore
        protocol = str(js.window.location.protocol)
        hostname = str(js.window.location.hostname)
        return protocol, hostname
    except Exception:
        pass
    try:
        from platform import window  # type: ignore
        protocol = str(window.location.protocol)
        hostname = str(window.location.hostname)
        return protocol, hostname
    except Exception:
        return None


def build_ws_url(host: str, port: int, ws_path: str) -> str:
    path = ws_path if ws_path.startswith("/") else f"/{ws_path}"

    if host.startswith("ws://") or host.startswith("wss://"):
        return host if host.endswith(path) else f"{host}{path}"

    scheme = "ws"
    ws_host = host
    if is_web_runtime():
        loc = get_browser_location()
        if loc is not None:
            protocol, browser_host = loc
            scheme = "wss" if protocol == "https:" else "ws"
            if host in ("127.0.0.1", "0.0.0.0", "localhost", ""):
                ws_host = browser_host

    return f"{scheme}://{ws_host}:{port}{path}"


def _decode_ws_payload(payload: object) -> str:
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    return str(payload)


class BrowserWebSocketClient:
    def __init__(self, url: str):
        self.url = url
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.open_event = asyncio.Event()
        self.close_event = asyncio.Event()
        self.error: str | None = None
        self.closed = False
        self._proxies: list[object] = []

        ws_ctor = None
        try:
            import js  # type: ignore
            ws_ctor = js.WebSocket
        except Exception:
            try:
                from platform import window  # type: ignore
                ws_ctor = window.WebSocket
            except Exception:
                ws_ctor = None

        if ws_ctor is None:
            raise RuntimeError("Browser WebSocket API not available.")

        self.ws = None
        ctor_errors: list[str] = []

        # 1) Direct `.new(...)` on explicit browser globals.
        try:
            import js  # type: ignore
            try:
                self.ws = js.WebSocket.new(url)
            except Exception as exc:
                ctor_errors.append(f"js.WebSocket.new: {exc}")
            if self.ws is None:
                try:
                    self.ws = js.window.WebSocket.new(url)
                except Exception as exc:
                    ctor_errors.append(f"js.window.WebSocket.new: {exc}")
            if self.ws is None:
                try:
                    self.ws = js.Reflect.construct(js.WebSocket, js.Array.new(url))
                except Exception as exc:
                    ctor_errors.append(f"Reflect.construct(js.WebSocket,...): {exc}")
            if self.ws is None:
                try:
                    self.ws = js.window.eval(f"new WebSocket({json.dumps(url)})")
                except Exception as exc:
                    ctor_errors.append(f"js.window.eval(new WebSocket): {exc}")
        except Exception as exc:
            ctor_errors.append(f"import js: {exc}")

        # 2) platform.window variants used by some pygbag builds.
        if self.ws is None:
            try:
                from platform import window  # type: ignore
                try:
                    self.ws = window.WebSocket.new(url)
                except Exception as exc:
                    ctor_errors.append(f"window.WebSocket.new: {exc}")
                if self.ws is None:
                    try:
                        self.ws = window.eval(f"new WebSocket({json.dumps(url)})")
                    except Exception as exc:
                        ctor_errors.append(f"window.eval(new WebSocket): {exc}")
            except Exception as exc:
                ctor_errors.append(f"import platform.window: {exc}")

        # 3) Legacy fallback from constructor reference (may still fail on strict wrappers).
        if self.ws is None:
            try:
                self.ws = ws_ctor.new(url)
            except Exception as exc:
                ctor_errors.append(f"ws_ctor.new: {exc}")
                try:
                    self.ws = ws_ctor(url)
                except Exception as exc2:
                    ctor_errors.append(f"ws_ctor(...): {exc2}")

        if self.ws is None:
            summary = "; ".join(ctor_errors[-4:])
            raise RuntimeError(f"WebSocket constructor failed: {summary}")

        def wrap_callback(cb):
            try:
                from pyodide.ffi import create_proxy  # type: ignore
                proxy = create_proxy(cb)
                self._proxies.append(proxy)
                return proxy
            except Exception:
                return cb

        def on_open(_evt=None):
            self.open_event.set()

        def on_message(evt):
            data = getattr(evt, "data", "")
            try:
                data = data.to_py()
            except Exception:
                pass
            self.queue.put_nowait(str(data))

        def on_error(_evt=None):
            self.error = "WebSocket connection error."
            self.open_event.set()

        def on_close(_evt=None):
            self.closed = True
            self.close_event.set()
            self.open_event.set()

        open_cb = wrap_callback(on_open)
        message_cb = wrap_callback(on_message)
        error_cb = wrap_callback(on_error)
        close_cb = wrap_callback(on_close)

        try:
            self.ws.addEventListener("open", open_cb)
            self.ws.addEventListener("message", message_cb)
            self.ws.addEventListener("error", error_cb)
            self.ws.addEventListener("close", close_cb)
        except Exception:
            self.ws.onopen = open_cb
            self.ws.onmessage = message_cb
            self.ws.onerror = error_cb
            self.ws.onclose = close_cb

    async def wait_open(self, timeout_s: float) -> str | None:
        try:
            await asyncio.wait_for(self.open_event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return f"Timeout after {timeout_s:.1f}s"

        ready_state = int(getattr(self.ws, "readyState", -1))
        if ready_state == 1:
            return None
        return self.error or "WebSocket did not open."

    async def recv(self) -> str | None:
        while True:
            if self.closed and self.queue.empty():
                return None
            try:
                return await asyncio.wait_for(self.queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                await asyncio.sleep(0)

    async def send(self, text: str) -> None:
        if self.closed:
            raise ConnectionError("WebSocket is closed")
        self.ws.send(text)

    async def close(self) -> None:
        if self.closed:
            return
        with suppress(Exception):
            self.ws.close()
        self.closed = True

    async def wait_closed(self) -> None:
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self.close_event.wait(), timeout=1.0)


async def send_json(conn: object, payload: dict) -> None:
    raw = json.dumps(payload, separators=(",", ":"))
    if isinstance(conn, asyncio.StreamWriter):
        conn.write((raw + "\n").encode("utf-8"))
        await conn.drain()
        return
    await conn.send(raw)


async def read_network_messages(reader: asyncio.StreamReader, net_state: dict) -> None:
    while True:
        line = await reader.readline()
        if not line:
            net_state["error"] = "Disconnected from server."
            return
        try:
            msg = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            continue

        msg_type = msg.get("type")
        if msg_type == "welcome":
            net_state["player_id"] = msg.get("player_id")
        elif msg_type == "state":
            net_state["latest_state"] = msg
        elif msg_type == "error":
            net_state["error"] = msg.get("message", "Server error.")


async def read_network_messages_ws(ws_conn: object, net_state: dict) -> None:
    while True:
        try:
            payload = await ws_conn.recv()
        except Exception:
            net_state["error"] = "Disconnected from server."
            return

        if payload is None:
            net_state["error"] = "Disconnected from server."
            return

        try:
            msg = json.loads(_decode_ws_payload(payload))
        except json.JSONDecodeError:
            continue

        msg_type = msg.get("type")
        if msg_type == "welcome":
            net_state["player_id"] = msg.get("player_id")
        elif msg_type == "state":
            net_state["latest_state"] = msg
        elif msg_type == "error":
            net_state["error"] = msg.get("message", "Server error.")


def load_visual_level(level: int, cache: dict[int, tuple]) -> tuple | None:
    if level in cache:
        return cache[level]

    key = level_key(level)
    if key not in MAP_DICT:
        return None

    cfg = MAP_DICT[key]
    base_w, base_h = cfg.get("window", (BASE_W, BASE_H))
    tmx, _ = load_level(cfg["map"] + ".tmx")
    cache[level] = (tmx, base_w, base_h)
    return cache[level]


def render_center_text(surface: pygame.Surface, font: pygame.font.Font, message: str, color: tuple[int, int, int]) -> None:
    lines = message.splitlines() or [message]
    rendered = [font.render(line, True, color) for line in lines]
    line_h = font.get_linesize()
    total_h = line_h * len(rendered)
    y = (surface.get_height() - total_h) // 2
    for text_surface in rendered:
        x = (surface.get_width() - text_surface.get_width()) // 2
        surface.blit(text_surface, (x, y))
        y += line_h


def present_scaled(window: pygame.Surface, surface: pygame.Surface) -> None:
    scale, off_x, off_y, scaled_w, scaled_h = calc_view(
        surface.get_width(),
        surface.get_height(),
        WINDOW_W,
        WINDOW_H,
    )
    window.fill((0, 0, 0))
    window.blit(pygame.transform.scale(surface, (scaled_w, scaled_h)), (off_x, off_y))
    pygame.display.flip()


async def show_connection_error_screen(
    window: pygame.Surface,
    title_font: pygame.font.Font,
    body_font: pygame.font.Font,
    host: str,
    port: int,
    reason: str,
) -> None:
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                return

        surface = pygame.Surface((UI_W, UI_H))
        surface.fill((15, 15, 20))

        title = title_font.render("Can't connect to server", True, (255, 130, 130))
        endpoint = body_font.render(f"{host}:{port}", True, (230, 230, 230))
        details = body_font.render(reason[:120], True, (200, 200, 210))
        hint = body_font.render("Press Esc or Enter to close", True, (170, 170, 185))

        surface.blit(title, title.get_rect(center=(UI_W // 2, UI_H // 2 - 90)))
        surface.blit(endpoint, endpoint.get_rect(center=(UI_W // 2, UI_H // 2 - 30)))
        surface.blit(details, details.get_rect(center=(UI_W // 2, UI_H // 2 + 20)))
        surface.blit(hint, hint.get_rect(center=(UI_W // 2, UI_H // 2 + 80)))

        present_scaled(window, surface)
        await asyncio.sleep(0)


async def connect_with_feedback(
    window: pygame.Surface,
    title_font: pygame.font.Font,
    body_font: pygame.font.Font,
    host: str,
    port: int,
    transport: str,
    ws_path: str,
    timeout_s: float = 8.0,
) -> tuple[object | None, object | None, str | None, str]:
    loop = asyncio.get_running_loop()
    if transport == "ws":
        endpoint = build_ws_url(host, port, ws_path)
        if is_web_runtime():
            try:
                browser_ws = BrowserWebSocketClient(endpoint)
            except Exception as exc:
                return None, None, f"{endpoint} | {exc.__class__.__name__}: {exc}", "ws"
            connect_task = asyncio.create_task(browser_ws.wait_open(timeout_s))
        else:
            try:
                import websockets
            except Exception as exc:
                return None, None, f"{endpoint} | websockets import failed: {exc}", "ws"
            connect_task = asyncio.create_task(websockets.connect(endpoint))
    else:
        endpoint = f"{host}:{port}"
        connect_task = asyncio.create_task(asyncio.open_connection(host, port))
    started = loop.time()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                connect_task.cancel()
                with suppress(asyncio.CancelledError):
                    await connect_task
                return None, None, "Connection cancelled by user.", transport

        if connect_task.done():
            try:
                if transport == "ws":
                    if is_web_runtime():
                        err = connect_task.result()
                        if err is not None:
                            return None, None, f"{endpoint} | {err}", "ws"
                        return None, browser_ws, None, "ws"
                    ws_conn = connect_task.result()
                    return None, ws_conn, None, "ws"
                reader, writer = connect_task.result()
                return reader, writer, None, "tcp"
            except Exception as exc:
                return None, None, f"{endpoint} | {exc.__class__.__name__}: {exc}", transport

        elapsed = loop.time() - started
        if elapsed >= timeout_s:
            connect_task.cancel()
            with suppress(asyncio.CancelledError):
                await connect_task
            return None, None, f"{endpoint} | Timeout after {timeout_s:.1f}s", transport

        dots = "." * (int(elapsed * 3) % 4)
        surface = pygame.Surface((UI_W, UI_H))
        surface.fill((15, 15, 20))
        render_center_text(surface, title_font, f"Connecting to {endpoint}{dots}", (235, 235, 235))
        elapsed_text = body_font.render(f"Elapsed: {elapsed:.1f}s", True, (180, 180, 195))
        surface.blit(elapsed_text, elapsed_text.get_rect(center=(UI_W // 2, UI_H // 2 + 62)))
        present_scaled(window, surface)
        await asyncio.sleep(0.05)


def make_enemy_sprite(enemy_type: str, x: int, y: int):
    if enemy_type == "Pancake":
        return Pancake(x, y)
    if enemy_type == "Waffle":
        return Waffle(x, y)
    if enemy_type == "Cookie":
        return Cookie(x, y)
    if enemy_type == "Amrany":
        return Amrany(x, y)
    return None


def normalize_username(raw: str, fallback: str) -> str:
    cleaned = raw.strip()
    return cleaned[:20] if cleaned else fallback


def load_player_preview(
    skin_name: str,
    preview_cache: dict[tuple[str, int], pygame.Surface],
    preview_size: int = 96,
) -> pygame.Surface:
    cache_key = (skin_name, preview_size)
    cached = preview_cache.get(cache_key)
    if cached is not None:
        return cached

    root = Path(__file__).resolve().parent
    if skin_name != "default":
        frame_path = root / "assets" / "player" / skin_name / "player_frame1.png"
    else:
        frame_path = root / "assets" / "player" / "player_frame1.png"

    if not frame_path.exists():
        frame_path = root / "assets" / "player" / "player_frame1.png"

    image = pygame.image.load(str(frame_path)).convert_alpha()
    scaled = pygame.transform.scale(image, (preview_size, preview_size))
    preview_cache[cache_key] = scaled
    return scaled


async def main(host: str, port: int, transport: str, ws_path: str) -> None:
    pygame.init()
    window = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("HellCrepe Multiplayer Client")
    clock = pygame.time.Clock()

    full_heart_img = pygame.image.load("assets/ui/full_heart.png").convert_alpha()
    broken_heart_img = pygame.image.load("assets/ui/broken_heart.png").convert_alpha()

    info_font = pygame.font.SysFont("arial", 18)
    overlay_font = pygame.font.SysFont("arial", 28, bold=True)
    boss_font = pygame.font.SysFont("arial", 12, bold=True)
    lobby_title_font = pygame.font.SysFont("arial", 44, bold=True)
    lobby_body_font = pygame.font.SysFont("arial", 28)
    lobby_small_font = pygame.font.SysFont("arial", 22)
    lobby_arrow_font = pygame.font.SysFont("arial", 56, bold=True)

    selected_transport = transport.lower()
    if selected_transport == "auto":
        selected_transport = "ws" if is_web_runtime() else "ws"

    reader, writer, connect_error, active_transport = await connect_with_feedback(
        window,
        overlay_font,
        info_font,
        host,
        port,
        selected_transport,
        ws_path,
        timeout_s=8.0,
    )
    if writer is None:
        await show_connection_error_screen(
            window,
            overlay_font,
            info_font,
            host,
            port,
            connect_error or "Unknown connection error.",
        )
        pygame.quit()
        return

    net_state = {"player_id": None, "latest_state": None, "error": None}
    if active_transport == "ws":
        read_task = asyncio.create_task(read_network_messages_ws(writer, net_state))
    else:
        read_task = asyncio.create_task(read_network_messages(reader, net_state))

    visual_cache: dict[int, tuple] = {}
    current_level = STARTING_LVL
    current_visual = load_visual_level(current_level, visual_cache)
    if current_visual is None:
        current_visual = (None, BASE_W, BASE_H)

    tmx, base_w, base_h = current_visual
    screen = pygame.Surface((base_w, base_h))
    scale, off_x, off_y, scaled_w, scaled_h = calc_view(base_w, base_h, WINDOW_W, WINDOW_H)

    player_sprites: dict[int, Player] = {}
    enemy_sprites: dict[int, object] = {}
    preview_cache: dict[tuple[str, int], pygame.Surface] = {}
    last_chest_event_id = 0
    chest_overlay_messages: list[str] = []
    chest_overlay_index = 0
    chest_overlay_wait_release = True
    session_phase = "waiting"
    connected_players = 0
    required_players = 2

    available_skins = ["default"]
    lobby_username = ""
    lobby_skin_index = 0
    lobby_ready = False
    lobby_initialized = False
    lobby_owner_id = None
    pause_menu_open = False
    pause_menu_index = 0
    pause_menu_options = ["Resume", "Restart Session", "Quit"]
    running = True

    while running:
        dt = clock.tick(FPS) / 1000.0
        restart_requested = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if session_phase == "playing":
                    if pause_menu_open:
                        if event.key in (pygame.K_UP, pygame.K_w):
                            pause_menu_index = (pause_menu_index - 1) % len(pause_menu_options)
                        elif event.key in (pygame.K_DOWN, pygame.K_s):
                            pause_menu_index = (pause_menu_index + 1) % len(pause_menu_options)
                        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                            selected = pause_menu_options[pause_menu_index]
                            if selected == "Resume":
                                pause_menu_open = False
                            elif selected == "Restart Session":
                                restart_requested = True
                                pause_menu_open = False
                            elif selected == "Quit":
                                running = False
                        elif event.key == pygame.K_ESCAPE:
                            pause_menu_open = False
                        continue
                    if event.key == pygame.K_ESCAPE:
                        pause_menu_open = True
                        pause_menu_index = 0
                        continue

                if session_phase == "lobby":
                    if event.key == pygame.K_RETURN:
                        lobby_ready = not lobby_ready
                    elif not lobby_ready:
                        if event.key == pygame.K_LEFT:
                            lobby_skin_index = (lobby_skin_index - 1) % max(1, len(available_skins))
                        elif event.key == pygame.K_RIGHT:
                            lobby_skin_index = (lobby_skin_index + 1) % max(1, len(available_skins))
                        elif event.key == pygame.K_BACKSPACE:
                            lobby_username = lobby_username[:-1]
                        elif event.unicode and event.unicode.isprintable() and len(lobby_username) < 20:
                            lobby_username += event.unicode

        latest_state = net_state.get("latest_state")
        local_player = None
        world = {}
        players: list[dict] = []
        player_id = net_state.get("player_id")
        session: dict = {}
        spectating_player_id = None

        if latest_state is not None:
            players = latest_state.get("players", [])
            session = latest_state.get("session", {})
            spectating_player_id = latest_state.get("spectating_player_id")
            if player_id is None:
                player_id = latest_state.get("you")
                net_state["player_id"] = player_id
            local_player = next((p for p in players if p.get("id") == player_id), None)
            connected_players = int(session.get("connected_players", len(players)))
            required_players = int(session.get("required_players", 2))

            session_phase = str(session.get("phase", "waiting"))
            maybe_skins = session.get("available_skins", available_skins)
            if isinstance(maybe_skins, list):
                parsed_skins = [str(s) for s in maybe_skins if str(s).strip()]
                if parsed_skins:
                    available_skins = parsed_skins
                    lobby_skin_index %= len(available_skins)

            if local_player is not None:
                if lobby_owner_id != player_id:
                    lobby_owner_id = player_id
                    lobby_initialized = False

                server_username = str(local_player.get("username", f"Player {player_id}"))
                server_skin = str(local_player.get("skin", available_skins[0]))
                server_ready = bool(local_player.get("ready", False))

                if (not lobby_initialized) or session_phase == "waiting":
                    lobby_username = server_username
                    lobby_ready = server_ready
                    if server_skin in available_skins:
                        lobby_skin_index = available_skins.index(server_skin)
                    else:
                        lobby_skin_index = 0
                    lobby_initialized = True
                elif session_phase != "lobby":
                    # Keep local controls inactive outside lobby.
                    lobby_ready = server_ready

                world = latest_state.get("world", {})
                render_level = int(world.get("current_level", local_player.get("current_level", STARTING_LVL)))
                if render_level != current_level:
                    maybe_visual = load_visual_level(render_level, visual_cache)
                    if maybe_visual is not None:
                        tmx, base_w, base_h = maybe_visual
                        screen = pygame.Surface((base_w, base_h))
                        scale, off_x, off_y, scaled_w, scaled_h = calc_view(base_w, base_h, WINDOW_W, WINDOW_H)
                        current_level = render_level

                chest_event_id = int(local_player.get("chest_event_id", 0))
                if chest_event_id > last_chest_event_id:
                    chest_event_level = int(local_player.get("chest_event_level", local_player.get("current_level", STARTING_LVL)))
                    cfg = MAP_DICT.get(level_key(chest_event_level), {})
                    msgs = [str(msg) for msg in cfg.get("chest_msg", []) if str(msg).strip()]
                    if msgs:
                        chest_overlay_messages = msgs
                        chest_overlay_index = 0
                        chest_overlay_wait_release = True
                    last_chest_event_id = chest_event_id

        if session_phase != "playing":
            chest_overlay_messages = []
            chest_overlay_index = 0
            chest_overlay_wait_release = True
            pause_menu_open = False

        target_w, target_h = (base_w, base_h) if session_phase == "playing" else (UI_W, UI_H)
        if screen.get_width() != target_w or screen.get_height() != target_h:
            screen = pygame.Surface((target_w, target_h))
            scale, off_x, off_y, scaled_w, scaled_h = calc_view(target_w, target_h, WINDOW_W, WINDOW_H)

        keys = pygame.key.get_pressed()
        mouse_buttons = pygame.mouse.get_pressed()
        mx, my = pygame.mouse.get_pos()

        chest_overlay_active = chest_overlay_index < len(chest_overlay_messages)
        if chest_overlay_active:
            space_down = bool(keys[pygame.K_SPACE])
            if chest_overlay_wait_release:
                if not space_down:
                    chest_overlay_wait_release = False
            elif space_down:
                chest_overlay_index += 1
                chest_overlay_wait_release = True
                chest_overlay_active = chest_overlay_index < len(chest_overlay_messages)

        aim_x = int((mx - off_x) / scale) if scale else 0
        aim_y = int((my - off_y) / scale) if scale else 0
        if screen.get_width() > 0:
            aim_x = max(0, min(screen.get_width() - 1, aim_x))
        if screen.get_height() > 0:
            aim_y = max(0, min(screen.get_height() - 1, aim_y))

        if net_state.get("error") is None:
            try:
                if session_phase == "lobby" and local_player is not None:
                    fallback_name = f"Player {player_id}" if player_id is not None else "Player"
                    username_to_send = normalize_username(lobby_username, fallback_name)
                    chosen_skin = available_skins[lobby_skin_index] if available_skins else "default"
                    await send_json(
                        writer,
                        {
                            "type": "lobby",
                            "username": username_to_send,
                            "skin": chosen_skin,
                            "ready": bool(lobby_ready),
                        },
                    )
                else:
                    input_locked = (session_phase != "playing") or chest_overlay_active or pause_menu_open
                    input_payload = {
                        "type": "input",
                        "left": bool(keys[pygame.K_a] or keys[pygame.K_LEFT]) and (not input_locked),
                        "right": bool(keys[pygame.K_d] or keys[pygame.K_RIGHT]) and (not input_locked),
                        "jump": bool(keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP]) and (not input_locked),
                        "shoot": bool(mouse_buttons[0]) and (not input_locked),
                        "aim_x": aim_x,
                        "aim_y": aim_y,
                        "restart": restart_requested,
                    }
                    await send_json(writer, input_payload)
            except Exception:
                net_state["error"] = "Disconnected from server."

        screen.fill((15, 15, 20))
        if tmx is not None:
            draw_tmx(screen, tmx)

        if local_player is not None and session_phase == "playing":
            chest = world.get("chest", {})

            for p_data in players:
                if int(p_data.get("current_level", -1)) != current_level:
                    continue
                color = (255, 220, 120) if p_data.get("id") == player_id else (120, 220, 255)
                for projectile in p_data.get("projectiles", []):
                    pygame.draw.circle(
                        screen,
                        color,
                        (int(projectile.get("x", 0)), int(projectile.get("y", 0))),
                        int(projectile.get("radius", 3)),
                    )

            for projectile in world.get("enemy_projectiles", []):
                pygame.draw.circle(
                    screen,
                    (255, 100, 100),
                    (int(projectile.get("x", 0)), int(projectile.get("y", 0))),
                    int(projectile.get("radius", 3)),
                )

            boss_enemy = None
            visible_enemy_ids: set[int] = set()
            for enemy in world.get("enemies", []):
                enemy_id = int(enemy.get("id", -1))
                enemy_type = str(enemy.get("type", ""))
                ex = int(enemy.get("x", 0))
                ey = int(enemy.get("y", 0))
                ew = int(enemy.get("w", 32))
                eh = int(enemy.get("h", 32))
                evx = float(enemy.get("vx", 0.0))

                sprite = enemy_sprites.get(enemy_id)
                if sprite is None or sprite.__class__.__name__ != enemy_type:
                    sprite = make_enemy_sprite(enemy_type, ex, ey)
                    if sprite is None:
                        fallback_rect = pygame.Rect(ex, ey, ew, eh)
                        pygame.draw.rect(screen, (220, 80, 80), fallback_rect)
                        continue
                    enemy_sprites[enemy_id] = sprite

                sprite.rect.x = ex
                sprite.rect.y = ey
                sprite.vx = evx
                if hasattr(sprite, "update_animation"):
                    sprite.update_animation(dt)
                sprite.draw(screen)
                visible_enemy_ids.add(enemy_id)

                if enemy_type == "Amrany":
                    boss_enemy = enemy

            stale_enemy_ids = [enemy_id for enemy_id in enemy_sprites if enemy_id not in visible_enemy_ids]
            for enemy_id in stale_enemy_ids:
                enemy_sprites.pop(enemy_id, None)

            if boss_enemy is not None:
                bar_w = 220
                bar_h = 10
                x = (base_w - bar_w) // 2
                y = 6

                ratio = 0.0
                max_hp = max(1, int(boss_enemy.get("max_hp", 1)))
                hp = int(boss_enemy.get("hp", 0))
                ratio = max(0.0, min(1.0, hp / max_hp))

                pygame.draw.rect(screen, (0, 0, 0), (x - 2, y - 2, bar_w + 4, bar_h + 4))
                pygame.draw.rect(screen, (60, 60, 60), (x, y, bar_w, bar_h))
                pygame.draw.rect(screen, (220, 60, 60), (x, y, int(bar_w * ratio), bar_h))

                hp_text = boss_font.render(f"{hp}/{max_hp}", True, (255, 255, 255))
                screen.blit(hp_text, hp_text.get_rect(center=(x + bar_w // 2, y + bar_h // 2)))

            for p_data in players:
                if int(p_data.get("current_level", -1)) != current_level:
                    continue
                pid = int(p_data.get("id", -1))
                px = int(p_data.get("x", 0))
                py = int(p_data.get("y", 0))
                skin_name = str(p_data.get("skin", "default"))

                sprite = player_sprites.get(pid)
                if sprite is None or getattr(sprite, "skin_name", "default") != skin_name:
                    sprite = Player(px, py, skin_name=skin_name)
                    player_sprites[pid] = sprite

                sprite.hitbox.x = px
                sprite.hitbox.y = py
                sprite.vx = float(p_data.get("vx", 0.0))
                sprite.update_animation(dt)
                screen.blit(sprite.image, sprite.draw_pos)

                if pid != player_id:
                    pname = normalize_username(str(p_data.get("username", "")), f"P{pid}")
                    label = info_font.render(pname, True, (220, 235, 255))
                    screen.blit(label, (sprite.hitbox.x - 2, sprite.hitbox.y - 15))

            hp = max(0, int(local_player.get("hp", 0)))
            max_hp = max(1, int(local_player.get("max_hp", 1)))
            for i in range(max_hp):
                hx = 8 + i * 20
                hy = 8
                if i < hp:
                    screen.blit(full_heart_img, (hx, hy))
                else:
                    screen.blit(broken_heart_img, (hx, hy))

            other_lines: list[str] = []
            for p_data in players:
                pid = int(p_data.get("id", -1))
                if pid == player_id:
                    continue
                pname = normalize_username(str(p_data.get("username", "")), f"P{pid}")
                other_lines.append(
                    f"{pname} | L{int(p_data.get('current_level', 0))} | HP {int(p_data.get('hp', 0))}/{int(p_data.get('max_hp', 0))}"
                )
            for idx, line in enumerate(other_lines):
                text = info_font.render(line, True, (220, 220, 220))
                screen.blit(text, (base_w - text.get_width() - 8, 8 + idx * 16))

            if local_player.get("dead", False):
                if local_player.get("won", False):
                    msg = "You Won."
                else:
                    spectating_name = "teammate"
                    if spectating_player_id is not None:
                        target = next((p for p in players if int(p.get("id", -1)) == int(spectating_player_id)), None)
                        if target is not None:
                            spectating_name = normalize_username(str(target.get("username", "")), f"P{spectating_player_id}")
                    msg = f"You Died.\nSpectating {spectating_name}.\nWaiting for other player to die."
                render_center_text(screen, overlay_font, msg, (255, 255, 255))

            if pause_menu_open:
                shade = pygame.Surface((base_w, base_h), pygame.SRCALPHA)
                shade.fill((0, 0, 0, 170))
                screen.blit(shade, (0, 0))

                menu_w = min(420, base_w - 40)
                menu_h = 220
                menu_x = (base_w - menu_w) // 2
                menu_y = (base_h - menu_h) // 2
                panel = pygame.Rect(menu_x, menu_y, menu_w, menu_h)
                pygame.draw.rect(screen, (25, 25, 35), panel, border_radius=10)
                pygame.draw.rect(screen, (100, 100, 140), panel, 2, border_radius=10)

                title = overlay_font.render("Paused", True, (240, 240, 250))
                screen.blit(title, title.get_rect(center=(base_w // 2, menu_y + 34)))

                for idx, option in enumerate(pause_menu_options):
                    color = (255, 220, 140) if idx == pause_menu_index else (220, 220, 230)
                    text = info_font.render(option, True, color)
                    screen.blit(text, text.get_rect(center=(base_w // 2, menu_y + 86 + idx * 34)))

            if chest_overlay_active:
                shade = pygame.Surface((base_w, base_h), pygame.SRCALPHA)
                shade.fill((0, 0, 0, 155))
                screen.blit(shade, (0, 0))
                render_center_text(screen, overlay_font, chest_overlay_messages[chest_overlay_index], (245, 245, 245))
        elif local_player is not None and session_phase == "lobby":
            screen.fill((12, 12, 18))
            sw, sh = screen.get_width(), screen.get_height()

            fallback_name = f"Player {player_id}" if player_id is not None else "Player"
            your_name = normalize_username(lobby_username, fallback_name)
            selected_skin = available_skins[lobby_skin_index] if available_skins else "default"

            card_w = min(sw - 120, 900)
            card_h = min(sh - 100, 560)
            card = pygame.Rect((sw - card_w) // 2, (sh - card_h) // 2, card_w, card_h)
            pygame.draw.rect(screen, (20, 20, 30), card, border_radius=14)
            pygame.draw.rect(screen, (90, 90, 125), card, 2, border_radius=14)

            other_player = next((p for p in players if p.get("id") != player_id), None)
            if other_player is None:
                top_line = "Waiting for other player..."
                top_color = (220, 220, 220)
            else:
                other_name = normalize_username(str(other_player.get("username", "")), f"P{other_player.get('id', '?')}")
                other_ready = bool(other_player.get("ready", False))
                top_line = f"{other_name} is {'READY' if other_ready else 'NOT READY'}"
                top_color = (130, 240, 160) if other_ready else (240, 170, 130)

            top_surface = lobby_title_font.render(top_line, True, top_color)
            screen.blit(top_surface, ((sw - top_surface.get_width()) // 2, card.y + 24))

            username_label = lobby_small_font.render("Username", True, (230, 230, 230))
            username_box = pygame.Rect(card.x + 110, card.y + 100, card.w - 220, 52)
            pygame.draw.rect(screen, (30, 30, 42), username_box, border_radius=6)
            pygame.draw.rect(screen, (160, 160, 190), username_box, 2, border_radius=6)
            username_text = lobby_body_font.render(your_name, True, (250, 250, 250))
            screen.blit(username_label, (username_box.x, username_box.y - 20))
            screen.blit(username_text, (username_box.x + 12, username_box.y + 12))

            preview = load_player_preview(selected_skin, preview_cache, preview_size=144)
            preview_rect = preview.get_rect(center=(sw // 2, card.y + 285))
            screen.blit(preview, preview_rect)

            left_arrow = lobby_arrow_font.render("<", True, (230, 230, 230))
            right_arrow = lobby_arrow_font.render(">", True, (230, 230, 230))
            screen.blit(left_arrow, left_arrow.get_rect(center=(preview_rect.left - 48, preview_rect.centery)))
            screen.blit(right_arrow, right_arrow.get_rect(center=(preview_rect.right + 48, preview_rect.centery)))

            skin_text = lobby_body_font.render(f"Skin: {selected_skin}", True, (220, 220, 230))
            screen.blit(skin_text, skin_text.get_rect(center=(sw // 2, preview_rect.bottom + 32)))

            ready_state = "READY" if lobby_ready else "NOT READY"
            ready_color = (120, 240, 140) if lobby_ready else (255, 205, 120)
            ready_text = lobby_body_font.render(f"You are {ready_state}", True, ready_color)
            screen.blit(ready_text, ready_text.get_rect(center=(sw // 2, card.bottom - 64)))

            controls_text = lobby_small_font.render("Type username  |  Left/Right: skin  |  Enter: ready", True, (190, 190, 205))
            screen.blit(controls_text, controls_text.get_rect(center=(sw // 2, card.bottom - 28)))
        else:
            wait_msg = "Waiting for server state..."
            if net_state.get("error"):
                wait_msg = net_state["error"]
            elif local_player is not None and session_phase == "waiting":
                wait_msg = f"Waiting for Player 2 to join... ({connected_players}/{required_players})"
            render_center_text(screen, overlay_font, wait_msg, (235, 235, 235))

        window.fill((0, 0, 0))
        scaled = pygame.transform.scale(screen, (scaled_w, scaled_h))
        window.blit(scaled, (off_x, off_y))
        pygame.display.flip()
        await asyncio.sleep(0)

    read_task.cancel()
    with suppress(asyncio.CancelledError):
        await read_task
    with suppress(Exception):
        if active_transport == "tcp":
            writer.close()
            await writer.wait_closed()
        else:
            await writer.close()
            wait_closed = getattr(writer, "wait_closed", None)
            if callable(wait_closed):
                await wait_closed()
    pygame.quit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HellCrepe multiplayer client")
    parser.add_argument("--host", default="127.0.0.1", help="Server host/IP")
    parser.add_argument("--port", type=int, default=9000, help="Server port")
    parser.add_argument("--transport", choices=["auto", "tcp", "ws"], default="ws", help="Network transport")
    parser.add_argument("--ws-path", default="/ws", help="WebSocket path")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.host, args.port, args.transport, args.ws_path))
