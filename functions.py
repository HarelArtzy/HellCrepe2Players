import json
from pathlib import Path

import pygame

from classes import EnemySprite, TcpJsonConnection
from settings import BASE_H, BASE_W, MAP_DICT


def calc_view(base_w, base_h, target_w=1920, target_h=1080):
    s = min(target_w / base_w, target_h / base_h)
    scaled_w = max(1, int(base_w * s))
    scaled_h = max(1, int(base_h * s))
    off_x = (target_w - scaled_w) // 2
    off_y = (target_h - scaled_h) // 2
    return s, off_x, off_y, scaled_w, scaled_h


def build_collision_rects(tmx, layer_name: str):
    tile_w = tmx.tilewidth
    tile_h = tmx.tileheight
    layer = tmx.get_layer_by_name(layer_name)
    solids = []
    for x, y, gid in layer:
        if gid != 0:
            solids.append(pygame.Rect(x * tile_w, y * tile_h, tile_w, tile_h))
    return solids


def draw_tmx(screen, tmx):
    for layer in tmx.visible_layers:
        if getattr(layer, "name", "") == "Collision":
            continue
        if hasattr(layer, "data"):
            for x, y, gid in layer:
                tile = tmx.get_tile_image_by_gid(gid)
                if tile:
                    screen.blit(tile, (x * tmx.tilewidth, y * tmx.tileheight))


def load_level(path):
    from pytmx.util_pygame import load_pygame

    tmx = load_pygame(path)
    solids = build_collision_rects(tmx, "Collision")
    return tmx, solids


def level_key(level: int) -> str:
    return f"lvl{level}"


def apply_network_message(msg: dict, net_state: dict) -> None:
    msg_type = msg.get("type")
    if msg_type == "welcome":
        net_state["player_id"] = msg.get("player_id")
    elif msg_type == "state":
        net_state["latest_state"] = msg
    elif msg_type == "error":
        net_state["error"] = msg.get("message", "Server error.")


def poll_network_messages(conn: TcpJsonConnection, net_state: dict) -> None:
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


def make_enemy_sprite(enemy_type: str, x: int, y: int):
    return EnemySprite(enemy_type, x, y)


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


def build_amrany_levels() -> set[int]:
    return {
        int(str(level_name)[3:])
        for level_name, cfg in MAP_DICT.items()
        if str(level_name).startswith("lvl")
        and any(str(enemy_name) == "Amrany" for enemy_name, _ in cfg.get("enemies", []))
    }
