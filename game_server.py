from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
import xml.etree.ElementTree as ET
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pygame

from settings import (
    BASE_HEARTS,
    BASE_SHOOT_COOLDOWN,
    BULLET_RADIUS,
    BULLET_SPEED,
    BULLET_TTL,
    ENEMY_BULLET_SPEED,
    ENEMY_BULLET_TTL,
    ENEMY_SHOOT_COOLDOWN,
    ENEMY_SIZE,
    ENEMY_SPEED,
    FPS,
    GRAVITY,
    INVINCIBILITY_TIME,
    JUMP_BUFFER_TIME,
    JUMP_VEL,
    MAP_DICT,
    MAX_STEP_HEIGHT,
    MODE,
    MOVE_SPEED,
    STARTING_LVL,
)


PROJECT_ROOT = Path(__file__).resolve().parent


def level_key(level: int) -> str:
    return f"lvl{level}"


def move_and_collide(
    rect: pygame.Rect,
    vx: float,
    vy: float,
    solids: list[pygame.Rect],
    dt: float,
    allow_step: bool,
) -> tuple[float, bool]:
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


def apply_reward(player: "SimPlayer", reward: tuple[str, str, float]) -> None:
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

    if attr == "shoot_cooldown" and player.shoot_cooldown < 0.05:
        player.shoot_cooldown = 0.05


def load_collision_rects_from_tmx(path: Path, layer_name: str = "Collision") -> list[pygame.Rect]:
    root = ET.parse(path).getroot()
    map_w = int(root.attrib["width"])
    tile_w = int(root.attrib["tilewidth"])
    tile_h = int(root.attrib["tileheight"])

    target_layer = None
    for layer in root.findall("layer"):
        if layer.attrib.get("name") == layer_name:
            target_layer = layer
            break

    if target_layer is None:
        return []

    data_node = target_layer.find("data")
    if data_node is None:
        return []

    encoding = data_node.attrib.get("encoding", "")
    if encoding != "csv":
        raise ValueError(f"Unsupported TMX data encoding '{encoding}' in {path}")

    raw = (data_node.text or "").replace("\n", "")
    gids = [int(token.strip()) for token in raw.split(",") if token.strip()]

    solids: list[pygame.Rect] = []
    for idx, gid in enumerate(gids):
        if gid == 0:
            continue
        tx = idx % map_w
        ty = idx // map_w
        solids.append(pygame.Rect(tx * tile_w, ty * tile_h, tile_w, tile_h))
    return solids


@dataclass
class PlayerInput:
    left: bool = False
    right: bool = False
    jump: bool = False
    shoot: bool = False
    aim_x: float = 0.0
    aim_y: float = 0.0
    restart: bool = False


@dataclass
class SimProjectile:
    x: float
    y: float
    vx: float
    vy: float
    radius: int = BULLET_RADIUS
    ttl: float = BULLET_TTL

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(
            int(self.x - self.radius),
            int(self.y - self.radius),
            self.radius * 2,
            self.radius * 2,
        )

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.ttl -= dt


class SimEnemy:
    enemy_type = "Enemy"
    use_gravity = True

    def __init__(self, enemy_id: int, x: int, y: int, w: int = ENEMY_SIZE, h: int = ENEMY_SIZE):
        self.enemy_id = enemy_id
        self.rect = pygame.Rect(x, y, w, h)
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.hp = 1
        self.max_hp = 1
        self.shoot_timer = 0.0
        self.shoot_cooldown = ENEMY_SHOOT_COOLDOWN

    def update_ai(
        self,
        dt: float,
        target_rect: pygame.Rect | None,
        enemies: list["SimEnemy"],
        solids: list[pygame.Rect],
    ) -> None:
        del dt, target_rect, enemies, solids

    def try_shoot(
        self,
        target_rect: pygame.Rect | None,
        enemy_projectiles: list[SimProjectile],
        enemies: list["SimEnemy"],
        spawn_enemy: Callable[[str, int, int], None] | None,
    ) -> None:
        del target_rect, enemy_projectiles, enemies, spawn_enemy

    def update(
        self,
        dt: float,
        target_rect: pygame.Rect | None,
        enemy_projectiles: list[SimProjectile],
        enemies: list["SimEnemy"],
        solids: list[pygame.Rect],
        spawn_enemy: Callable[[str, int, int], None] | None,
    ) -> None:
        self.update_ai(dt, target_rect, enemies, solids)
        self.shoot_timer = max(0.0, self.shoot_timer - dt)
        self.try_shoot(target_rect, enemy_projectiles, enemies, spawn_enemy)


def shoot_at_player(
    shooter: SimEnemy,
    target_rect: pygame.Rect | None,
    enemy_projectiles: list[SimProjectile],
) -> None:
    if shooter.shoot_timer > 0:
        return
    if target_rect is None:
        return

    sx, sy = shooter.rect.centerx, shooter.rect.centery
    dx = target_rect.centerx - sx
    dy = target_rect.centery - sy
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return

    dx /= length
    dy /= length
    vx = dx * ENEMY_BULLET_SPEED
    vy = dy * ENEMY_BULLET_SPEED
    enemy_projectiles.append(SimProjectile(sx, sy, vx, vy, radius=3, ttl=ENEMY_BULLET_TTL))
    shooter.shoot_timer = shooter.shoot_cooldown


class Pancake(SimEnemy):
    enemy_type = "Pancake"
    use_gravity = True

    def update_ai(
        self,
        dt: float,
        target_rect: pygame.Rect | None,
        enemies: list[SimEnemy],
        solids: list[pygame.Rect],
    ) -> None:
        del dt, enemies, solids
        if target_rect is None:
            self.vx = 0.0
            return
        self.vx = -ENEMY_SPEED if target_rect.centerx < self.rect.centerx else ENEMY_SPEED

    def try_shoot(
        self,
        target_rect: pygame.Rect | None,
        enemy_projectiles: list[SimProjectile],
        enemies: list[SimEnemy],
        spawn_enemy: Callable[[str, int, int], None] | None,
    ) -> None:
        del enemies, spawn_enemy
        shoot_at_player(self, target_rect, enemy_projectiles)


class Waffle(SimEnemy):
    enemy_type = "Waffle"
    use_gravity = True

    def update_ai(
        self,
        dt: float,
        target_rect: pygame.Rect | None,
        enemies: list[SimEnemy],
        solids: list[pygame.Rect],
    ) -> None:
        del dt, enemies, solids
        if target_rect is None:
            self.vx = 0.0
            return
        self.vx = -ENEMY_SPEED if target_rect.centerx < self.rect.centerx else ENEMY_SPEED

    def try_shoot(
        self,
        target_rect: pygame.Rect | None,
        enemy_projectiles: list[SimProjectile],
        enemies: list[SimEnemy],
        spawn_enemy: Callable[[str, int, int], None] | None,
    ) -> None:
        del enemies, spawn_enemy
        shoot_at_player(self, target_rect, enemy_projectiles)


class Cookie(SimEnemy):
    enemy_type = "Cookie"
    use_gravity = False

    def update_ai(
        self,
        dt: float,
        target_rect: pygame.Rect | None,
        enemies: list[SimEnemy],
        solids: list[pygame.Rect],
    ) -> None:
        del dt, enemies, solids
        if target_rect is None:
            self.vx = 0.0
            return
        self.vx = -ENEMY_SPEED if target_rect.centerx < self.rect.centerx else ENEMY_SPEED

    def try_shoot(
        self,
        target_rect: pygame.Rect | None,
        enemy_projectiles: list[SimProjectile],
        enemies: list[SimEnemy],
        spawn_enemy: Callable[[str, int, int], None] | None,
    ) -> None:
        del enemies, spawn_enemy
        shoot_at_player(self, target_rect, enemy_projectiles)


class Amrany(SimEnemy):
    enemy_type = "Amrany"
    use_gravity = True

    def __init__(self, enemy_id: int, x: int, y: int):
        super().__init__(enemy_id, x, y, 64, 144)
        self.hp = 67
        self.max_hp = 67
        self.spawn_cooldown = ENEMY_SHOOT_COOLDOWN
        self.spawn_timer = 0.0

    def update_ai(
        self,
        dt: float,
        target_rect: pygame.Rect | None,
        enemies: list[SimEnemy],
        solids: list[pygame.Rect],
    ) -> None:
        del dt, target_rect, enemies, solids
        self.vx = 0.0

    def update(
        self,
        dt: float,
        target_rect: pygame.Rect | None,
        enemy_projectiles: list[SimProjectile],
        enemies: list[SimEnemy],
        solids: list[pygame.Rect],
        spawn_enemy: Callable[[str, int, int], None] | None,
    ) -> None:
        self.update_ai(dt, target_rect, enemies, solids)
        self.spawn_timer = max(0.0, self.spawn_timer - dt)
        self.try_shoot(target_rect, enemy_projectiles, enemies, spawn_enemy)

    def try_shoot(
        self,
        target_rect: pygame.Rect | None,
        enemy_projectiles: list[SimProjectile],
        enemies: list[SimEnemy],
        spawn_enemy: Callable[[str, int, int], None] | None,
    ) -> None:
        del enemy_projectiles, enemies
        if self.spawn_timer > 0:
            return
        if spawn_enemy is None:
            return
        if target_rect is None:
            return

        direction = -1 if target_rect.centerx < self.rect.centerx else 1
        x_offset = (self.rect.width // 2) + (ENEMY_SIZE // 2) + 6
        spawn_x = self.rect.centerx + direction * x_offset

        upper = self.rect.bottom - ENEMY_SIZE - 10
        if upper <= self.rect.top:
            spawn_y = self.rect.top
        else:
            spawn_y = random.randrange(self.rect.top, upper)

        spawn_enemy("Cookie", int(spawn_x - ENEMY_SIZE // 2), int(spawn_y))
        self.spawn_timer = self.spawn_cooldown


ENEMY_FACTORY = {
    "Pancake": Pancake,
    "Waffle": Waffle,
    "Cookie": Cookie,
    "Amrany": Amrany,
}


@dataclass
class SimPlayer:
    player_id: int
    hitbox: pygame.Rect
    username: str = ""
    skin: str = "default"
    ready: bool = False
    hp: int = BASE_HEARTS
    max_hp: int = BASE_HEARTS
    vx: float = 0.0
    vy: float = 0.0
    on_ground: bool = False
    move_speed: float = MOVE_SPEED
    jump_buffer: float = 0.0
    hurt_timer: float = 0.0
    shoot_timer: float = 0.0
    shoot_cooldown: float = BASE_SHOOT_COOLDOWN
    dead: bool = False
    won: bool = False
    current_level: int = STARTING_LVL
    visual_advanced: bool = False
    locked: bool = True
    last_jump_down: bool = False
    chest_event_id: int = 0
    chest_event_level: int = STARTING_LVL
    projectiles: list[SimProjectile] = field(default_factory=list)


@dataclass
class LevelGeometry:
    solids: list[pygame.Rect]
    end_rect: pygame.Rect
    chest_rect: pygame.Rect
    width: int
    height: int


@dataclass
class SharedLevelState:
    level: int
    solids: list[pygame.Rect]
    end_rect: pygame.Rect
    chest_rect: pygame.Rect
    width: int
    height: int
    chest_open: bool = False
    chest_claimed_by: set[int] = field(default_factory=set)
    enemies: list[SimEnemy] = field(default_factory=list)
    enemy_projectiles: list[SimProjectile] = field(default_factory=list)
    next_enemy_id: int = 1


class DungeonGameServer:
    def __init__(
        self,
        host: str,
        port: int,
        max_players: int = 2,
        session_id: str = "default",
    ):
        self.host = host
        self.port = port
        self.max_players = max_players
        self.session_id = session_id

        self.players: dict[int, SimPlayer] = {}
        self.inputs: dict[int, PlayerInput] = {}
        self.writers: dict[int, asyncio.StreamWriter] = {}

        self.level_cache: dict[int, LevelGeometry] = {}
        self.levels: dict[int, SharedLevelState] = {}

        self.available_skins = self.discover_skins()
        self.match_started = False
        self.tick = 0

    def discover_skins(self) -> list[str]:
        base_dir = PROJECT_ROOT / "assets" / "player"
        skins: list[str] = []
        if base_dir.exists():
            for entry in sorted(base_dir.iterdir(), key=lambda p: p.name.lower()):
                if not entry.is_dir():
                    continue
                if (entry / "player_frame1.png").exists() and (entry / "player_frame2.png").exists():
                    skins.append(entry.name)

        if skins:
            return skins

        # Fallback to legacy single-skin files at assets/player/player_frame*.png.
        return ["default"]

    def default_skin(self) -> str:
        return self.available_skins[0] if self.available_skins else "default"

    def players_connected(self) -> bool:
        return len(self.players) >= self.max_players

    def all_players_ready(self) -> bool:
        if not self.players_connected():
            return False
        return all(player.ready for player in self.players.values())

    def session_phase(self) -> str:
        if not self.players_connected():
            return "waiting"
        if not self.match_started:
            return "lobby"
        return "playing"

    def reset_dynamic_world(self) -> None:
        self.levels.clear()
        self.tick = 0

    def reset_players_for_lobby(self) -> None:
        self.match_started = False
        self.reset_dynamic_world()
        for player in self.players.values():
            player.current_level = STARTING_LVL
            player.ready = False
            self.reset_player(player, carry_stats=False)

    def start_match(self) -> None:
        self.match_started = True
        self.reset_dynamic_world()
        for player in self.players.values():
            player.current_level = STARTING_LVL
            player.ready = False
            self.reset_player(player, carry_stats=False)

    def next_free_player_id(self) -> int | None:
        for pid in range(1, self.max_players + 1):
            if pid not in self.players:
                return pid
        return None

    def get_level_geometry(self, level: int) -> LevelGeometry:
        cached = self.level_cache.get(level)
        if cached is not None:
            return cached

        key = level_key(level)
        cfg = MAP_DICT[key]

        width, height = cfg.get("window", (53 * 16, 20 * 16))
        end_x, end_y = cfg["end"]
        chest_x, chest_y = cfg["chest"]
        tmx_path = PROJECT_ROOT / f"{cfg['map']}.tmx"
        solids = load_collision_rects_from_tmx(tmx_path)

        geom = LevelGeometry(
            solids=solids,
            end_rect=pygame.Rect(end_x, end_y, 16, 16),
            chest_rect=pygame.Rect(chest_x, chest_y, 16, 16),
            width=width,
            height=height,
        )
        self.level_cache[level] = geom
        return geom

    def make_level_enemies(self, level: int) -> tuple[list[SimEnemy], int]:
        enemies: list[SimEnemy] = []
        next_enemy_id = 1
        cfg = MAP_DICT[level_key(level)]
        for enemy_name, (ex, ey) in cfg["enemies"]:
            enemy_cls = ENEMY_FACTORY.get(enemy_name)
            if enemy_cls is None:
                continue
            enemies.append(enemy_cls(next_enemy_id, ex, ey))
            next_enemy_id += 1
        return enemies, next_enemy_id

    def get_or_create_level_state(self, level: int) -> SharedLevelState:
        state = self.levels.get(level)
        if state is not None:
            return state

        geom = self.get_level_geometry(level)
        enemies, next_enemy_id = self.make_level_enemies(level)
        state = SharedLevelState(
            level=level,
            solids=geom.solids,
            end_rect=geom.end_rect.copy(),
            chest_rect=geom.chest_rect.copy(),
            width=geom.width,
            height=geom.height,
            enemies=enemies,
            next_enemy_id=next_enemy_id,
        )
        self.levels[level] = state
        return state

    def spawn_enemy(self, level_state: SharedLevelState, enemy_name: str, ex: int, ey: int) -> None:
        enemy_cls = ENEMY_FACTORY.get(enemy_name)
        if enemy_cls is None:
            return
        enemy = enemy_cls(level_state.next_enemy_id, ex, ey)
        level_state.next_enemy_id += 1
        level_state.enemies.append(enemy)

    def reset_player(self, player: SimPlayer, carry_stats: bool) -> None:
        cfg = MAP_DICT[level_key(player.current_level)]
        sx, sy = cfg["start"]

        if carry_stats:
            max_hp = player.max_hp
            hp = min(player.hp, max_hp)
            shoot_cooldown = player.shoot_cooldown
            move_speed = player.move_speed
        else:
            max_hp = BASE_HEARTS
            hp = BASE_HEARTS
            shoot_cooldown = BASE_SHOOT_COOLDOWN
            move_speed = MOVE_SPEED

        player.hitbox = pygame.Rect(sx, sy, 16, 22)
        player.hp = hp
        player.max_hp = max_hp
        player.vx = 0.0
        player.vy = 0.0
        player.on_ground = False
        player.move_speed = move_speed
        player.jump_buffer = 0.0
        player.hurt_timer = 0.0
        player.shoot_timer = 0.0
        player.shoot_cooldown = shoot_cooldown
        player.dead = False
        player.won = False
        player.visual_advanced = False
        player.locked = True
        player.last_jump_down = False
        player.projectiles.clear()

        self.get_or_create_level_state(player.current_level)
        if player.player_id in self.inputs:
            self.inputs[player.player_id].aim_x = player.hitbox.centerx
            self.inputs[player.player_id].aim_y = player.hitbox.centery

    def create_player(self, player_id: int) -> SimPlayer:
        player = SimPlayer(
            player_id=player_id,
            hitbox=pygame.Rect(0, 0, 16, 22),
            username=f"Player {player_id}",
            skin=self.default_skin(),
            ready=False,
        )
        player.current_level = STARTING_LVL
        self.inputs[player_id] = PlayerInput()
        self.reset_player(player, carry_stats=False)
        return player

    def build_target_rect(self, enemy: SimEnemy, players_here: list[SimPlayer]) -> pygame.Rect | None:
        if not players_here:
            return None

        ex, ey = enemy.rect.centerx, enemy.rect.centery
        closest = None
        best_dist = None
        for p in players_here:
            dx = p.hitbox.centerx - ex
            dy = p.hitbox.centery - ey
            dist = dx * dx + dy * dy
            if best_dist is None or dist < best_dist:
                best_dist = dist
                closest = p
        return closest.hitbox if closest is not None else None

    def spawn_player_projectile(self, player: SimPlayer, aim_x: float, aim_y: float) -> None:
        sx, sy = player.hitbox.centerx, player.hitbox.centery
        dx = aim_x - sx
        dy = aim_y - sy
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return

        dx /= length
        dy /= length
        player.projectiles.append(
            SimProjectile(
                x=sx,
                y=sy,
                vx=dx * BULLET_SPEED,
                vy=dy * BULLET_SPEED,
            )
        )

    def get_chest_interaction_rect(self, chest_rect: pygame.Rect) -> pygame.Rect:
        # Chest sprites are larger than the 16x16 anchor tile; widen/lower interaction area.
        return pygame.Rect(chest_rect.x - 16, chest_rect.y, 48, 32)

    def step_players(self, dt: float) -> None:
        if any(inp.restart for inp in self.inputs.values()):
            for inp in self.inputs.values():
                inp.restart = False
            self.reset_players_for_lobby()
            return

        for pid, player in list(self.players.items()):
            inp = self.inputs.get(pid)
            if inp is None:
                continue

            if player.dead or player.won:
                continue

            level = self.get_or_create_level_state(player.current_level)
            cfg = MAP_DICT[level_key(player.current_level)]

            player.shoot_timer = max(0.0, player.shoot_timer - dt)
            player.hurt_timer = max(0.0, player.hurt_timer - dt)
            player.jump_buffer = max(0.0, player.jump_buffer - dt)

            if inp.jump and not player.last_jump_down:
                player.jump_buffer = JUMP_BUFFER_TIME
            player.last_jump_down = inp.jump

            if inp.shoot and player.shoot_timer == 0.0:
                self.spawn_player_projectile(player, inp.aim_x, inp.aim_y)
                player.shoot_timer = player.shoot_cooldown

            player.vx = 0.0
            if inp.left:
                player.vx -= player.move_speed
            if inp.right:
                player.vx += player.move_speed

            player.vy += GRAVITY * dt
            player.vy, player.on_ground = move_and_collide(
                player.hitbox,
                player.vx,
                player.vy,
                level.solids,
                dt,
                allow_step=player.on_ground,
            )

            chest_interaction_rect = self.get_chest_interaction_rect(level.chest_rect)
            if player.hitbox.colliderect(chest_interaction_rect) and pid not in level.chest_claimed_by:
                level.chest_claimed_by.add(pid)
                level.chest_open = True
                player.chest_event_id += 1
                player.chest_event_level = player.current_level
                for reward in cfg.get("chest_reward", []):
                    apply_reward(player, reward)

            has_claimed = pid in level.chest_claimed_by

            if (not player.visual_advanced) and has_claimed and cfg.get("chest_change_map", False):
                next_level = player.current_level + 1
                if level_key(next_level) in MAP_DICT:
                    player.current_level = next_level
                    player.visual_advanced = True
                    player.projectiles.clear()
                    self.get_or_create_level_state(next_level)
                    continue

            if (not player.visual_advanced) and len(level.enemies) == 0 and cfg.get("cleared", False):
                next_level = player.current_level + 1
                if level_key(next_level) in MAP_DICT:
                    player.current_level = next_level
                    player.visual_advanced = True
                    player.locked = False
                    player.projectiles.clear()
                    self.get_or_create_level_state(next_level)
                    continue

            can_exit = (not cfg.get("cleared", False)) or (cfg.get("cleared", False) and (not player.locked))
            if player.hitbox.colliderect(level.end_rect) and can_exit:
                next_level = player.current_level + 1
                if level_key(next_level) not in MAP_DICT:
                    player.won = True
                    player.dead = True
                    continue
                player.current_level = next_level
                self.reset_player(player, carry_stats=True)
                continue

            if player.jump_buffer > 0 and player.on_ground:
                player.vy = -JUMP_VEL
                player.on_ground = False
                player.jump_buffer = 0.0

    def step_levels(self, dt: float) -> None:
        for level_idx, level in list(self.levels.items()):
            players_here = [
                p for p in self.players.values()
                if (not p.dead) and p.current_level == level_idx
            ]

            for enemy in level.enemies[:]:
                target_rect = self.build_target_rect(enemy, players_here)
                enemy.update(
                    dt,
                    target_rect,
                    level.enemy_projectiles,
                    level.enemies,
                    level.solids,
                    lambda name, ex, ey: self.spawn_enemy(level, name, ex, ey),
                )
                if getattr(enemy, "use_gravity", True):
                    enemy.vy += GRAVITY * dt
                enemy.vy, enemy.on_ground = move_and_collide(
                    enemy.rect,
                    enemy.vx,
                    enemy.vy,
                    level.solids,
                    dt,
                    allow_step=False,
                )

            for player in players_here:
                for enemy in level.enemies:
                    if player.hurt_timer == 0 and player.hitbox.colliderect(enemy.rect):
                        player.hp -= 1
                        player.hurt_timer = INVINCIBILITY_TIME
                        player.vx = -250 if player.hitbox.centerx < enemy.rect.centerx else 250
                        player.vy = -200

            for player in players_here:
                for projectile in player.projectiles:
                    projectile.update(dt)

                alive_projectiles: list[SimProjectile] = []
                for projectile in player.projectiles:
                    if projectile.ttl <= 0:
                        continue

                    r = projectile.rect
                    if r.right < 0 or r.left > level.width or r.bottom < 0 or r.top > level.height:
                        continue
                    if any(r.colliderect(s) for s in level.solids):
                        continue

                    hit_enemy = False
                    for enemy in level.enemies:
                        if r.colliderect(enemy.rect):
                            enemy.hp -= 1
                            hit_enemy = True
                            break
                    if hit_enemy:
                        continue

                    alive_projectiles.append(projectile)

                player.projectiles = alive_projectiles

            level.enemies = [enemy for enemy in level.enemies if enemy.hp > 0]

            for projectile in level.enemy_projectiles:
                projectile.update(dt)

            alive_enemy_projectiles: list[SimProjectile] = []
            for projectile in level.enemy_projectiles:
                if projectile.ttl <= 0:
                    continue

                r = projectile.rect
                if r.right < 0 or r.left > level.width or r.bottom < 0 or r.top > level.height:
                    continue
                if any(r.colliderect(s) for s in level.solids):
                    continue

                hit_player = False
                for player in players_here:
                    if r.colliderect(player.hitbox):
                        if MODE != 1:
                            player.hp -= 1
                        hit_player = True
                        break
                if hit_player:
                    continue

                alive_enemy_projectiles.append(projectile)

            level.enemy_projectiles = alive_enemy_projectiles

            for player in players_here:
                if player.hp <= 0:
                    player.dead = True
                    player.projectiles.clear()

    def apply_client_message(self, player_id: int, msg: dict) -> None:
        inp = self.inputs.get(player_id)
        if inp is None:
            return

        inp.left = bool(msg.get("left", False))
        inp.right = bool(msg.get("right", False))
        inp.jump = bool(msg.get("jump", False))
        inp.shoot = bool(msg.get("shoot", False))
        inp.restart = bool(msg.get("restart", False))

        player = self.players.get(player_id)
        default_x = player.hitbox.centerx if player else 0
        default_y = player.hitbox.centery if player else 0
        try:
            inp.aim_x = float(msg.get("aim_x", default_x))
        except (TypeError, ValueError):
            inp.aim_x = float(default_x)
        try:
            inp.aim_y = float(msg.get("aim_y", default_y))
        except (TypeError, ValueError):
            inp.aim_y = float(default_y)

    def apply_lobby_message(self, player_id: int, msg: dict) -> None:
        player = self.players.get(player_id)
        if player is None:
            return
        if self.session_phase() != "lobby":
            return

        username_raw = str(msg.get("username", "")).strip()
        if username_raw:
            player.username = username_raw[:20]

        skin_raw = str(msg.get("skin", "")).strip()
        if skin_raw in self.available_skins:
            player.skin = skin_raw

        player.ready = bool(msg.get("ready", False))

    def build_snapshot(self, player_id: int) -> dict:
        player = self.players[player_id]
        snapshot_level = player.current_level
        spectating_player_id = None
        if player.dead and not player.won:
            for pid, other in sorted(self.players.items()):
                if pid == player_id:
                    continue
                if not other.dead:
                    spectating_player_id = pid
                    snapshot_level = other.current_level
                    break

        local_level = self.get_or_create_level_state(snapshot_level)
        chest_interaction_rect = self.get_chest_interaction_rect(local_level.chest_rect)
        can_interact_with_chest = (
            (not player.dead)
            and player.current_level == snapshot_level
            and player.hitbox.colliderect(chest_interaction_rect)
            and player_id not in local_level.chest_claimed_by
        )

        players_payload = []
        for pid, other in sorted(self.players.items()):
            if other.current_level == snapshot_level:
                projectiles = [
                    {"x": projectile.x, "y": projectile.y, "radius": projectile.radius}
                    for projectile in other.projectiles
                ]
            else:
                projectiles = []

            players_payload.append(
                {
                    "id": pid,
                    "username": other.username,
                    "skin": other.skin,
                    "ready": other.ready,
                    "x": other.hitbox.x,
                    "y": other.hitbox.y,
                    "w": other.hitbox.w,
                    "h": other.hitbox.h,
                    "vx": other.vx,
                    "vy": other.vy,
                    "hp": other.hp,
                    "max_hp": other.max_hp,
                    "dead": other.dead,
                    "won": other.won,
                    "current_level": other.current_level,
                    "chest_event_id": other.chest_event_id,
                    "chest_event_level": other.chest_event_level,
                    "projectiles": projectiles,
                }
            )

        enemies_payload = [
            {
                "id": enemy.enemy_id,
                "type": enemy.enemy_type,
                "x": enemy.rect.x,
                "y": enemy.rect.y,
                "w": enemy.rect.w,
                "h": enemy.rect.h,
                "vx": enemy.vx,
                "hp": enemy.hp,
                "max_hp": enemy.max_hp,
            }
            for enemy in local_level.enemies
        ]
        enemy_projectiles_payload = [
            {"x": projectile.x, "y": projectile.y, "radius": projectile.radius}
            for projectile in local_level.enemy_projectiles
        ]

        return {
            "type": "state",
            "tick": self.tick,
            "you": player_id,
            "spectating_player_id": spectating_player_id,
            "session": {
                "id": self.session_id,
                "connected_players": len(self.players),
                "required_players": self.max_players,
                "ready": self.match_started or self.all_players_ready(),
                "phase": self.session_phase(),
                "available_skins": self.available_skins,
            },
            "level_size": {"w": local_level.width, "h": local_level.height},
            "players": players_payload,
            "world": {
                "current_level": snapshot_level,
                "chest": {
                    "x": local_level.chest_rect.x,
                    "y": local_level.chest_rect.y,
                    "w": local_level.chest_rect.w,
                    "h": local_level.chest_rect.h,
                    "open": local_level.chest_open,
                    "can_interact": can_interact_with_chest,
                    "claimed_by_you": player_id in local_level.chest_claimed_by,
                },
                "enemies": enemies_payload,
                "enemy_projectiles": enemy_projectiles_payload,
                "locked": player.locked,
            },
        }

    async def send_json(self, conn: asyncio.StreamWriter, payload: dict) -> None:
        raw = json.dumps(payload, separators=(",", ":"))
        conn.write((raw + "\n").encode("utf-8"))
        await conn.drain()

    async def remove_player(self, player_id: int) -> None:
        self.players.pop(player_id, None)
        self.inputs.pop(player_id, None)
        conn = self.writers.pop(player_id, None)
        if conn is not None:
            with suppress(Exception):
                conn.close()
                await conn.wait_closed()

        if not self.players:
            self.match_started = False
            self.reset_dynamic_world()
            return

        # Someone left during/after a run: return remaining player(s) to lobby state.
        self.reset_players_for_lobby()

    async def stream_state_to_player(self, player_id: int, writer: asyncio.StreamWriter) -> None:
        if player_id not in self.players:
            return
        try:
            await self.send_json(writer, self.build_snapshot(player_id))
        except Exception:
            await self.remove_player(player_id)

    async def game_loop(self) -> None:
        tick_dt = 1.0 / FPS
        while True:
            started = time.perf_counter()

            if (not self.match_started) and self.all_players_ready():
                self.start_match()

            if self.match_started and self.players_connected():
                self.step_players(tick_dt)
                self.step_levels(tick_dt)
                if (
                    self.match_started
                    and self.players
                    and all(p.dead for p in self.players.values())
                    and all(not p.won for p in self.players.values())
                ):
                    self.reset_players_for_lobby()

            tasks = [
                self.stream_state_to_player(player_id, writer)
                for player_id, writer in list(self.writers.items())
            ]
            if tasks:
                await asyncio.gather(*tasks)

            self.tick += 1
            elapsed = time.perf_counter() - started
            await asyncio.sleep(max(0.0, tick_dt - elapsed))

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if not self.players:
            self.match_started = False
            self.reset_dynamic_world()

        player_id = self.next_free_player_id()
        if player_id is None:
            with suppress(Exception):
                await self.send_json(writer, {"type": "error", "message": "Server is full (max 2 players)."})
                writer.close()
                await writer.wait_closed()
            return

        self.players[player_id] = self.create_player(player_id)
        self.writers[player_id] = writer
        self.reset_players_for_lobby()

        with suppress(Exception):
            await self.send_json(
                writer,
                {
                    "type": "welcome",
                    "player_id": player_id,
                    "tick_rate": FPS,
                    "max_players": self.max_players,
                    "session_id": self.session_id,
                },
            )

        try:
            invalid_packets = 0
            while True:
                line = await reader.readline()
                if not line:
                    break

                try:
                    decoded = line.decode("utf-8")
                except UnicodeDecodeError:
                    invalid_packets += 1
                    if invalid_packets >= 3:
                        break
                    continue

                try:
                    msg = json.loads(decoded)
                except json.JSONDecodeError:
                    invalid_packets += 1
                    if invalid_packets >= 3:
                        break
                    continue

                invalid_packets = 0
                msg_type = msg.get("type")
                if msg_type == "input":
                    self.apply_client_message(player_id, msg)
                elif msg_type == "lobby":
                    self.apply_lobby_message(player_id, msg)
        finally:
            await self.remove_player(player_id)

    async def run(self) -> None:
        tcp_server = await asyncio.start_server(self.handle_client, self.host, self.port)
        tcp_targets = ", ".join(str(sock.getsockname()) for sock in (tcp_server.sockets or []))
        print(f"Dungeon TCP server listening on {tcp_targets}")

        tick_task = asyncio.create_task(self.game_loop())
        try:
            await tcp_server.serve_forever()
        finally:
            tcp_server.close()
            with suppress(Exception):
                await tcp_server.wait_closed()
            tick_task.cancel()
            with suppress(asyncio.CancelledError):
                await tick_task


class MultiSessionDungeonServer:
    def __init__(
        self,
        host: str,
        port: int,
        max_players_per_session: int = 2,
        max_sessions: int = 0,
    ):
        self.host = host
        self.port = port
        self.max_players_per_session = max_players_per_session
        self.max_sessions = max(0, int(max_sessions))

        self.sessions: dict[str, DungeonGameServer] = {}
        self.session_tasks: dict[str, asyncio.Task] = {}
        self.next_session_num = 1

    async def send_json(self, conn: asyncio.StreamWriter, payload: dict) -> None:
        raw = json.dumps(payload, separators=(",", ":"))
        conn.write((raw + "\n").encode("utf-8"))
        await conn.drain()

    def normalize_session_id(self, raw: str | None) -> str | None:
        if raw is None:
            return None
        cleaned = "".join(ch for ch in str(raw) if ch.isalnum() or ch in ("-", "_")).strip()
        if not cleaned:
            return None
        return cleaned[:32]

    def next_session_id(self) -> str:
        while True:
            sid = f"s{self.next_session_num}"
            self.next_session_num += 1
            if sid not in self.sessions:
                return sid

    def ensure_session_task(self, session_id: str, session: DungeonGameServer) -> None:
        task = self.session_tasks.get(session_id)
        if task is None or task.done():
            self.session_tasks[session_id] = asyncio.create_task(
                session.game_loop(),
                name=f"session-{session_id}",
            )

    def create_session(self, session_id: str) -> DungeonGameServer:
        session = DungeonGameServer(
            self.host,
            self.port,
            max_players=self.max_players_per_session,
            session_id=session_id,
        )
        self.sessions[session_id] = session
        self.ensure_session_task(session_id, session)
        print(f"[multisession] created session '{session_id}'")
        return session

    def pick_session(self, requested_session: str | None) -> tuple[str | None, DungeonGameServer | None, str | None]:
        wanted = self.normalize_session_id(requested_session)
        if wanted is not None:
            session = self.sessions.get(wanted)
            if session is None:
                if self.max_sessions and len(self.sessions) >= self.max_sessions:
                    return None, None, "Session limit reached."
                session = self.create_session(wanted)
            elif session.next_free_player_id() is None:
                return None, None, f"Session '{wanted}' is full."
            self.ensure_session_task(wanted, session)
            return wanted, session, None

        candidates: list[tuple[int, str, DungeonGameServer]] = []
        for sid, session in self.sessions.items():
            if session.next_free_player_id() is None:
                continue
            self.ensure_session_task(sid, session)
            candidates.append((len(session.players), sid, session))
        if candidates:
            # Prefer filling half-full rooms first so random matchmaking pairs up quickly.
            candidates.sort(key=lambda item: item[0], reverse=True)
            _, sid, session = candidates[0]
            return sid, session, None

        if self.max_sessions and len(self.sessions) >= self.max_sessions:
            return None, None, "All sessions are currently full."
        sid = self.next_session_id()
        session = self.create_session(sid)
        return sid, session, None

    async def close_connection(self, conn: asyncio.StreamWriter) -> None:
        with suppress(Exception):
            conn.close()
            await conn.wait_closed()

    async def cleanup_session_if_empty(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        if session is None:
            return
        if session.players:
            return

        task = self.session_tasks.pop(session_id, None)
        self.sessions.pop(session_id, None)
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        print(f"[multisession] removed session '{session_id}'")

    async def register_player(
        self,
        conn: asyncio.StreamWriter,
        requested_session: str | None,
    ) -> tuple[str | None, DungeonGameServer | None, int | None]:
        session_id, session, pick_error = self.pick_session(requested_session)
        if session is None or session_id is None:
            with suppress(Exception):
                await self.send_json(conn, {"type": "error", "message": pick_error or "No room available."})
            await self.close_connection(conn)
            return None, None, None

        player_id = session.next_free_player_id()
        if player_id is None:
            with suppress(Exception):
                await self.send_json(conn, {"type": "error", "message": "Selected room is full."})
            await self.close_connection(conn)
            return None, None, None

        session.players[player_id] = session.create_player(player_id)
        session.writers[player_id] = conn
        session.reset_players_for_lobby()

        welcome = {
            "type": "welcome",
            "player_id": player_id,
            "tick_rate": FPS,
            "max_players": session.max_players,
            "session_id": session_id,
        }

        try:
            await self.send_json(conn, welcome)
        except Exception:
            await session.remove_player(player_id)
            await self.cleanup_session_if_empty(session_id)
            await self.close_connection(conn)
            return None, None, None

        print(
            f"[multisession] session='{session_id}' connected player {player_id} "
            f"({len(session.players)}/{session.max_players})"
        )
        return session_id, session, player_id

    async def session_reaper_loop(self) -> None:
        while True:
            await asyncio.sleep(2.0)
            for session_id in list(self.sessions.keys()):
                await self.cleanup_session_if_empty(session_id)

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        session_id, session, player_id = await self.register_player(writer, requested_session=None)
        if session is None or player_id is None or session_id is None:
            return

        try:
            invalid_packets = 0
            while True:
                line = await reader.readline()
                if not line:
                    break

                try:
                    decoded = line.decode("utf-8")
                except UnicodeDecodeError:
                    invalid_packets += 1
                    if invalid_packets >= 3:
                        break
                    continue

                try:
                    msg = json.loads(decoded)
                except json.JSONDecodeError:
                    invalid_packets += 1
                    if invalid_packets >= 3:
                        break
                    continue

                invalid_packets = 0
                msg_type = msg.get("type")
                if msg_type == "input":
                    session.apply_client_message(player_id, msg)
                elif msg_type == "lobby":
                    session.apply_lobby_message(player_id, msg)
        finally:
            await session.remove_player(player_id)
            await self.cleanup_session_if_empty(session_id)

    async def run(self) -> None:
        tcp_server = await asyncio.start_server(self.handle_client, self.host, self.port)
        tcp_targets = ", ".join(str(sock.getsockname()) for sock in (tcp_server.sockets or []))
        print(f"Dungeon TCP server listening on {tcp_targets}")
        print("Matchmaking mode: multiple 2-player sessions enabled")

        reaper_task = asyncio.create_task(self.session_reaper_loop(), name="session-reaper")
        try:
            await tcp_server.serve_forever()
        finally:
            tcp_server.close()
            with suppress(Exception):
                await tcp_server.wait_closed()

            reaper_task.cancel()
            with suppress(asyncio.CancelledError):
                await reaper_task

            for session in list(self.sessions.values()):
                for player_id in list(session.players.keys()):
                    await session.remove_player(player_id)
            for session_id in list(self.sessions.keys()):
                await self.cleanup_session_if_empty(session_id)

            for task in list(self.session_tasks.values()):
                task.cancel()
            for task in list(self.session_tasks.values()):
                with suppress(asyncio.CancelledError, Exception):
                    await task
            self.session_tasks.clear()
            self.sessions.clear()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HellCrepe multiplayer game server")
    parser.add_argument("--host", default="0.0.0.0", help="Host/IP to bind")
    parser.add_argument("--port", type=int, default=9000, help="TCP port")
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=0,
        help="Maximum concurrent sessions (0 = unlimited)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    server = MultiSessionDungeonServer(
        args.host,
        args.port,
        max_players_per_session=2,
        max_sessions=args.max_sessions,
    )
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        pass
