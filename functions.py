# functions.py
import asyncio
import pygame

from settings import *

if not hasattr(pygame, "Vector2"):
    try:
        pygame.Vector2 = pygame.math.Vector2
    except Exception:
        class Vector2(tuple):
            __slots__ = ()
            def __new__(cls, x=0, y=0):
                return tuple.__new__(cls, (x, y))
        pygame.Vector2 = Vector2


def calc_view(base_w, base_h, target_w=1920, target_h=1080):
    s = min(target_w / base_w, target_h / base_h)
    scaled_w = max(1, int(base_w * s))
    scaled_h = max(1, int(base_h * s))
    off_x = (target_w - scaled_w) // 2
    off_y = (target_h - scaled_h) // 2
    return s, off_x, off_y, scaled_w, scaled_h


def move_and_collide(rect: pygame.Rect, vx: float, vy: float, solids: list[pygame.Rect], dt: float, allow_step: bool):
    dx = int(vx * dt)
    rect.x += dx

    if dx != 0:
        hit = None
        for s in solids:
            if rect.colliderect(s):
                hit = s
                break

        if hit is not None:
            if allow_step:
                original_y = rect.y
                stepped = False
                for step in range(1, MAX_STEP_HEIGHT + 1):
                    rect.y = original_y - step
                    blocked = False
                    for s2 in solids:
                        if rect.colliderect(s2):
                            blocked = True
                            break
                    if not blocked:
                        stepped = True
                        break

                if not stepped:
                    rect.y = original_y
                    if dx > 0:
                        rect.right = hit.left
                    else:
                        rect.left = hit.right
            else:
                if dx > 0:
                    rect.right = hit.left
                else:
                    rect.left = hit.right

    on_ground = False

    rect.y += int(vy * dt)
    for s in solids:
        if rect.colliderect(s):
            if vy > 0:
                rect.bottom = s.top
                vy = 0.0
                on_ground = True
            elif vy < 0:
                rect.top = s.bottom
                vy = 0.0

    return vy, on_ground


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


def shoot(projectiles: list, player, scale, off_x, off_y):
    mx, my = pygame.mouse.get_pos()
    mx = int((mx - off_x) / scale)
    my = int((my - off_y) / scale)

    sx, sy = player.hitbox.centerx, player.hitbox.centery
    dx = mx - sx
    dy = my - sy

    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return

    dx /= length
    dy /= length

    vx = dx * BULLET_SPEED
    vy = dy * BULLET_SPEED

    from classes import Projectile
    projectiles.append(Projectile(sx, sy, vx, vy))


def display_text(window, screen, msg, color, base_w, base_h, scale, off_x, off_y, font_name="Arial", font_size=24):
    screen.fill((15, 15, 20))
    font = pygame.font.SysFont(font_name, font_size)
    lines = msg.splitlines() if "\n" in msg else [msg]

    rendered = [font.render(line, True, color) for line in lines]
    line_h = font.get_linesize()

    total_h = len(rendered) * line_h
    start_y = (base_h - total_h) // 2

    for i, surf in enumerate(rendered):
        rect = surf.get_rect()
        rect.centerx = base_w // 2
        rect.y = start_y + i * line_h
        screen.blit(surf, rect)

    _, _, _, scaled_w, scaled_h = calc_view(base_w, base_h)
    window.fill((0, 0, 0))
    scaled = pygame.transform.scale(screen, (scaled_w, scaled_h))
    window.blit(scaled, (off_x, off_y))
    pygame.display.flip()


async def pause_menu(window, screen, clock, base_w, base_h, scale, off_x, off_y):
    while True:
        display_text(
            window, screen,
            "Game Paused.\nPress Space or Esc to resume.\nPress 'r' to restart.\nPress 'q' to quit",
            pygame.Color("white"),
            base_w, base_h, scale, off_x, off_y
        )
        clock.tick(30)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    return "restart"
                if event.key == pygame.K_q:
                    return "quit"
                if event.key in (pygame.K_SPACE, pygame.K_ESCAPE):
                    pygame.event.clear(pygame.KEYDOWN)
                    return "resume"

        await asyncio.sleep(0)


async def end_menu(window, screen, clock, msg, base_w, base_h, scale, off_x, off_y):
    while True:
        display_text(window, screen, msg, pygame.Color("white"), base_w, base_h, scale, off_x, off_y)
        clock.tick(30)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    return "restart"
                if event.key == pygame.K_q:
                    return "quit"

        await asyncio.sleep(0)


async def open_chest(window, screen, clock, level, base_w, base_h, scale, off_x, off_y):
    level_str = "lvl" + str(level)
    msgs = MAP_DICT[level_str]["chest_msg"]

    for m in msgs:
        space_was_down = True
        while True:
            display_text(window, screen, m, pygame.Color("white"), base_w, base_h, scale, off_x, off_y)
            clock.tick(30)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "quit"

            keys = pygame.key.get_pressed()
            space_down = keys[pygame.K_SPACE]

            if space_was_down and not space_down:
                space_was_down = False

            if (not space_was_down) and space_down:
                pygame.event.clear(pygame.KEYDOWN)
                break

            await asyncio.sleep(0)

    return None


def load_level(path):
    from pytmx.util_pygame import load_pygame
    tmx = load_pygame(path)
    solids = build_collision_rects(tmx, "Collision")
    return tmx, solids


def apply_reward(player, reward):
    attr, op, val = reward
    cur = getattr(player, attr)
    if op == "add":
        setattr(player, attr, cur + val)
    elif op == "mul":
        setattr(player, attr, cur * val)
    elif op == "set":
        setattr(player, attr, val)

    if attr in ("max_hp", "hp"):
        if player.max_hp < 1:
            player.max_hp = 1
        if player.hp > player.max_hp:
            player.hp = player.max_hp
        if player.hp < 0:
            player.hp = 0

    if attr == "shoot_cooldown":
        if player.shoot_cooldown < 0.05:
            player.shoot_cooldown = 0.05


def make_enemies(level_str):
    from classes import Pancake, Waffle, Amrany, Cookie
    enemy_map = {
        "Pancake": Pancake,
        "Waffle": Waffle,
        "Amrany": Amrany,
        "Cookie": Cookie,
    }
    es = []
    for e_name, (ex, ey) in MAP_DICT[level_str]["enemies"]:
        es.append(enemy_map[e_name](ex, ey))
    return es


def swap_map_keep_state(new_level, current_level):
    new_level_str = "lvl" + str(new_level)

    map_path = MAP_DICT[new_level_str]["map"] + ".tmx"
    tmx, solids = load_level(map_path)

    end_x, end_y = MAP_DICT[new_level_str]["end"]
    end_rect = pygame.Rect(end_x, end_y, 16, 16)

    chest_x, chest_y = MAP_DICT[new_level_str]["chest"]
    chest_rect = pygame.Rect(chest_x, chest_y, 16, 16)

    chest_open = False

    return tmx, solids, end_rect, chest_rect, chest_open, new_level