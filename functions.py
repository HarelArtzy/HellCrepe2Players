import json
import socket
import time
from pathlib import Path

import pygame

from classes import Amrany, Cookie, Pancake, TcpJsonConnection, Waffle
from settings import BASE_H, BASE_W, MAP_DICT


def calc_view(base_w, base_h, target_w=1920, target_h=1080):
    """Compute scale and letterbox offsets to fit a base surface into a target window while preserving aspect ratio."""
    s = min(target_w / base_w, target_h / base_h)
    scaled_w = max(1, int(base_w * s))
    scaled_h = max(1, int(base_h * s))
    off_x = (target_w - scaled_w) // 2
    off_y = (target_h - scaled_h) // 2
    return s, off_x, off_y, scaled_w, scaled_h


def build_collision_rects(tmx, layer_name: str):
    """Build pygame collision rectangles from non-empty tiles in a named TMX layer."""
    tile_w = tmx.tilewidth
    tile_h = tmx.tileheight
    layer = tmx.get_layer_by_name(layer_name)

    solids = []
    for x, y, gid in layer:
        if gid != 0:
            solids.append(pygame.Rect(x * tile_w, y * tile_h, tile_w, tile_h))
    return solids


def draw_tmx(screen, tmx):
    """Render all visible non-collision TMX layers to the provided surface."""
    for layer in tmx.visible_layers:
        if getattr(layer, "name", "") == "Collision":
            continue
        if hasattr(layer, "data"):
            for x, y, gid in layer:
                tile = tmx.get_tile_image_by_gid(gid)
                if tile:
                    screen.blit(tile, (x * tmx.tilewidth, y * tmx.tileheight))


def load_level(path):
    """Load a TMX map and return both the map object and collision rectangles."""
    from pytmx.util_pygame import load_pygame

    tmx = load_pygame(path)
    solids = build_collision_rects(tmx, "Collision")
    return tmx, solids


def level_key(level: int) -> str:
    """Convert a numeric level index to the MAP_DICT key format."""
    return f"lvl{level}"


def apply_network_message(msg: dict, net_state: dict) -> None:
    """Apply a single server JSON message to the client network state cache."""
    msg_type = msg.get("type")
    if msg_type == "welcome":
        net_state["player_id"] = msg.get("player_id")
        net_state["session_id"] = msg.get("session_id")
    elif msg_type == "state":
        net_state["latest_state"] = msg
    elif msg_type == "error":
        net_state["error"] = msg.get("message", "Server error.")


def poll_network_messages(conn: TcpJsonConnection, net_state: dict) -> None:
    """Read pending socket messages, decode JSON, and update client network state."""
    try:
        lines = conn.poll_messages()
    except ConnectionError:
        net_state["error"] = "Disconnected from server."
        return

    for line in lines:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        apply_network_message(msg, net_state)

    if conn.closed and net_state.get("error") is None:
        net_state["error"] = "Disconnected from server."


def load_visual_level(level: int, cache: dict[int, tuple]) -> tuple | None:
    """Load and cache level TMX plus its configured render dimensions."""
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
    """Render multiline text centered on a surface with consistent line spacing."""
    lines = message.splitlines() or [message]
    rendered = [font.render(line, True, color) for line in lines]
    line_h = font.get_linesize()
    total_h = line_h * len(rendered)
    y = (surface.get_height() - total_h) // 2
    for text_surface in rendered:
        x = (surface.get_width() - text_surface.get_width()) // 2
        surface.blit(text_surface, (x, y))
        y += line_h


def present_scaled(window: pygame.Surface, surface: pygame.Surface, target_w: int = 1920, target_h: int = 1080) -> None:
    """Scale a source surface to target dimensions and present it with letterboxing."""
    scale, off_x, off_y, scaled_w, scaled_h = calc_view(
        surface.get_width(),
        surface.get_height(),
        target_w,
        target_h,
    )
    del scale
    window.fill((0, 0, 0))
    window.blit(pygame.transform.scale(surface, (scaled_w, scaled_h)), (off_x, off_y))
    pygame.display.flip()


def show_connection_error_screen(
    window: pygame.Surface,
    title_font: pygame.font.Font,
    body_font: pygame.font.Font,
    host: str,
    port: int,
    reason: str,
    ui_w: int = 1280,
    ui_h: int = 720,
    target_w: int = 1920,
    target_h: int = 1080,
) -> None:
    """Display a blocking connection-error screen until the user dismisses it."""
    clock = pygame.time.Clock()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                return

        surface = pygame.Surface((ui_w, ui_h))
        surface.fill((15, 15, 20))

        title = title_font.render("Can't connect to server", True, (255, 130, 130))
        endpoint = body_font.render(f"{host}:{port}", True, (230, 230, 230))
        details = body_font.render(reason[:120], True, (200, 200, 210))
        hint = body_font.render("Press Esc or Enter to close", True, (170, 170, 185))

        surface.blit(title, title.get_rect(center=(ui_w // 2, ui_h // 2 - 90)))
        surface.blit(endpoint, endpoint.get_rect(center=(ui_w // 2, ui_h // 2 - 30)))
        surface.blit(details, details.get_rect(center=(ui_w // 2, ui_h // 2 + 20)))
        surface.blit(hint, hint.get_rect(center=(ui_w // 2, ui_h // 2 + 80)))

        present_scaled(window, surface, target_w=target_w, target_h=target_h)
        clock.tick(60)


def connect_with_feedback(
    window: pygame.Surface,
    title_font: pygame.font.Font,
    body_font: pygame.font.Font,
    host: str,
    port: int,
    timeout_s: float = 8.0,
    ui_w: int = 1280,
    ui_h: int = 720,
    target_w: int = 1920,
    target_h: int = 1080,
) -> tuple[TcpJsonConnection | None, str | None]:
    """Attempt TCP connection with timeout while rendering live progress feedback."""
    endpoint = f"{host}:{port}"
    started = time.perf_counter()
    last_error: OSError | None = None
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None, "Connection cancelled by user."

        elapsed = time.perf_counter() - started
        if elapsed >= timeout_s:
            if last_error is None:
                return None, f"{endpoint} | Timeout after {timeout_s:.1f}s"
            return None, f"{endpoint} | {last_error.__class__.__name__}: {last_error}"

        try:
            sock = socket.create_connection((host, port), timeout=0.35)
            return TcpJsonConnection(sock), None
        except OSError as exc:
            last_error = exc

        dots = "." * (int(elapsed * 3) % 4)
        surface = pygame.Surface((ui_w, ui_h))
        surface.fill((15, 15, 20))
        render_center_text(surface, title_font, f"Connecting to {endpoint}{dots}", (235, 235, 235))
        elapsed_text = body_font.render(f"Elapsed: {elapsed:.1f}s", True, (180, 180, 195))
        surface.blit(elapsed_text, elapsed_text.get_rect(center=(ui_w // 2, ui_h // 2 + 62)))
        present_scaled(window, surface, target_w=target_w, target_h=target_h)
        pygame.time.wait(50)


def make_enemy_sprite(enemy_type: str, x: int, y: int):
    """Instantiate a client enemy sprite object from a server enemy type string."""
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
    """Trim and bound a username, falling back to a default if empty."""
    cleaned = raw.strip()
    return cleaned[:20] if cleaned else fallback


def load_player_preview(
    skin_name: str,
    preview_cache: dict[tuple[str, int], pygame.Surface],
    preview_size: int = 96,
) -> pygame.Surface:
    """Load, scale, cache, and return a skin preview sprite for lobby rendering."""
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


def build_amrany_levels() -> set[int]:
    """Return all configured level indices that spawn Amrany."""
    return {
        int(str(level_name)[3:])
        for level_name, cfg in MAP_DICT.items()
        if str(level_name).startswith("lvl")
        and any(str(enemy_name) == "Amrany" for enemy_name, _ in cfg.get("enemies", []))
    }

