from __future__ import annotations

import asyncio
import json
import logging
import random
import xml.etree.ElementTree as ET
from contextlib import suppress
from pathlib import Path

import pygame

from EnemyState import EnemyState
from LevelState import LevelState
from PlayerInput import PlayerInput
from ProjectileState import ProjectileState
from SimPlayer import SimPlayer
from settings import (
    BASE_HEARTS,
    BASE_SHOOT_COOLDOWN,
    BULLET_SPEED,
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


logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parent
MAX_HEADER_BYTES = 12
MAX_FRAME_BYTES = 2_000_000


def move_and_collide(
    rect: pygame.Rect,
    vx: float,
    vy: float,
    solids: list[pygame.Rect],
    dt: float,
    allow_step: bool,
) -> tuple[float, bool]:
    """Move an axis-aligned rectangle and resolve collisions against solids."""
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


def load_collision_rects_from_tmx(path: Path) -> list[pygame.Rect]:
    """Read the Collision layer from a TMX file into pygame rectangles."""
    root = ET.parse(path).getroot()
    map_w = int(root.attrib["width"])
    tile_w = int(root.attrib["tilewidth"])
    tile_h = int(root.attrib["tileheight"])

    layer = None
    for candidate in root.findall("layer"):
        if candidate.attrib.get("name") == "Collision":
            layer = candidate
            break
    if layer is None:
        return []
    data_node = layer.find("data")
    if data_node is None:
        return []
    if data_node.attrib.get("encoding") != "csv":
        raise ValueError("Collision layer must use csv encoding")

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


class DungeonGameServer:
    def __init__(self, host: str, port: int, max_players: int = 2):
        """Initialize server state, player slots, and world caches."""
        self.host = host
        self.port = port
        self.max_players = max_players
        self.players: dict[int, SimPlayer] = {}
        self.inputs: dict[int, PlayerInput] = {}
        self.writers: dict[int, asyncio.StreamWriter] = {}
        self.level_cache: dict[int,
                               tuple[list[pygame.Rect],
                                     pygame.Rect,
                                     pygame.Rect,
                                     int,
                                     int]] = {}
        self.levels: dict[int, LevelState] = {}
        self.available_skins = self.discover_skins()
        self.match_started = False
        self.tick = 0

    def discover_skins(self) -> list[str]:
        """Discover available skin directories with required frame files."""
        base_dir = PROJECT_ROOT / "assets" / "player"
        skins: list[str] = []
        if base_dir.exists():
            for entry in sorted(
                    base_dir.iterdir(),
                    key=lambda p: p.name.lower()):
                if entry.is_dir() and (
                        entry /
                        "player_frame1.png").exists() and (
                        entry /
                        "player_frame2.png").exists():
                    skins.append(entry.name)
        return skins or ["default"]

    def default_skin(self) -> str:
        """Return the default skin name used for new players."""
        return self.available_skins[0]

    def players_connected(self) -> bool:
        """Return whether enough players are connected to fill the match."""
        return len(self.players) >= self.max_players

    def all_players_ready(self) -> bool:
        """Return whether all connected players are marked ready."""
        return self.players_connected() and all(p.ready
                                                for p in self.players.values())

    def session_phase(self) -> str:
        """Return waiting, lobby, or playing from current match state."""
        if not self.players_connected():
            return "waiting"
        return "playing" if self.match_started else "lobby"

    def next_free_player_id(self) -> int | None:
        """Return the next available player slot, or None if full."""
        for pid in range(1, self.max_players + 1):
            if pid not in self.players:
                return pid
        return None

    def reset_dynamic_world(self):
        """Clear simulated level state and reset the server tick counter."""
        self.levels.clear()
        self.tick = 0

    def make_enemy(
            self,
            enemy_id: int,
            enemy_type: str,
            ex: int,
            ey: int) -> EnemyState:
        """Create one enemy state with type-specific dimensions and hp."""
        if enemy_type == "Amrany":
            return EnemyState(
                enemy_id, enemy_type, pygame.Rect(
                    ex, ey, 64, 144), hp=67, max_hp=67)
        return EnemyState(
            enemy_id,
            enemy_type,
            pygame.Rect(
                ex,
                ey,
                ENEMY_SIZE,
                ENEMY_SIZE),
            hp=1,
            max_hp=1)

    def ensure_level(self, level: int) -> LevelState:
        """Load level state on demand and return the cached object."""
        state = self.levels.get(level)
        if state is not None:
            return state

        cached = self.level_cache.get(level)
        if cached is None:
            cfg = MAP_DICT[f"lvl{level}"]
            width, height = cfg.get("window", (53 * 16, 20 * 16))
            end_x, end_y = cfg["end"]
            chest_x, chest_y = cfg["chest"]
            solids = load_collision_rects_from_tmx(
                PROJECT_ROOT / f"{cfg['map']}.tmx")
            cached = (
                solids, pygame.Rect(
                    end_x, end_y, 16, 16), pygame.Rect(
                    chest_x, chest_y, 16, 16), width, height)
            self.level_cache[level] = cached

        solids, end_rect, chest_rect, width, height = cached
        cfg = MAP_DICT[f"lvl{level}"]
        enemies: list[EnemyState] = []
        next_id = 1
        for enemy_name, (ex, ey) in cfg["enemies"]:
            enemies.append(self.make_enemy(next_id, enemy_name, ex, ey))
            next_id += 1

        state = LevelState(
            level=level,
            solids=solids,
            end_rect=end_rect.copy(),
            chest_rect=chest_rect.copy(),
            width=width,
            height=height,
            enemies=enemies,
            next_enemy_id=next_id,
        )
        self.levels[level] = state
        return state

    def spawn_enemy(
            self,
            state: LevelState,
            enemy_type: str,
            ex: int,
            ey: int):
        """Spawn a new enemy in an existing level state."""
        enemy = self.make_enemy(state.next_enemy_id, enemy_type, ex, ey)
        state.next_enemy_id += 1
        state.enemies.append(enemy)

    def apply_reward(self, player: SimPlayer,
                     reward: tuple[str, str, float]) -> None:
        """Apply one chest reward mutation tuple to a player's stats."""
        attr, op, val = reward
        cur = getattr(player, attr)
        if op == "add":
            setattr(player, attr, cur + val)
        elif op == "mul":
            setattr(player, attr, cur * val)
        elif op == "set":
            setattr(player, attr, val)
        if attr in ("max_hp", "hp"):
            player.max_hp = max(1, player.max_hp)
            player.hp = max(0, min(player.hp, player.max_hp))
        if attr == "shoot_cooldown":
            player.shoot_cooldown = max(0.05, player.shoot_cooldown)

    def reset_player(self, player: SimPlayer, carry_stats: bool):
        """Reset a player and optionally preserve upgraded stats."""
        cfg = MAP_DICT[f"lvl{player.current_level}"]
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
        self.ensure_level(player.current_level)
        if player.player_id in self.inputs:
            self.inputs[player.player_id].aim_x = player.hitbox.centerx
            self.inputs[player.player_id].aim_y = player.hitbox.centery

    def create_player(self, player_id: int) -> SimPlayer:
        """Create and initialize a new player simulation object."""
        player = SimPlayer(
            player_id=player_id,
            hitbox=pygame.Rect(0, 0, 16, 22),
            username=f"Player {player_id}",
            skin=self.default_skin(),
            ready=False,
        )
        self.inputs[player_id] = PlayerInput()
        self.reset_player(player, carry_stats=False)
        return player

    def reset_players_for_lobby(self):
        """Reset all players and world state back to lobby defaults."""
        self.match_started = False
        self.reset_dynamic_world()
        for player in self.players.values():
            player.current_level = STARTING_LVL
            player.ready = False
            self.reset_player(player, carry_stats=False)

    def start_match(self):
        """Start a fresh match and reset all players to initial level state."""
        self.match_started = True
        self.reset_dynamic_world()
        for player in self.players.values():
            player.current_level = STARTING_LVL
            player.ready = False
            self.reset_player(player, carry_stats=False)

    @staticmethod
    def chest_interaction_rect(chest_rect: pygame.Rect) -> pygame.Rect:
        """Return the interaction area around a chest rectangle."""
        return pygame.Rect(chest_rect.x - 16, chest_rect.y, 48, 32)

    @staticmethod
    def nearest_target(enemy_rect: pygame.Rect,
                       players: list[SimPlayer]) -> pygame.Rect | None:
        """Return the closest player hitbox to an enemy, if any."""
        if not players:
            return None
        ex, ey = enemy_rect.centerx, enemy_rect.centery
        best_dist = None
        best = None
        for player in players:
            dx = player.hitbox.centerx - ex
            dy = player.hitbox.centery - ey
            dist = dx * dx + dy * dy
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best = player.hitbox
        return best

    @staticmethod
    def shoot_toward(
        shooter_rect: pygame.Rect,
        target_rect: pygame.Rect | None,
        projectiles: list[ProjectileState],
        speed: float,
        ttl: float,
    ) -> bool:
        """Spawn a projectile toward the target and return success state."""
        if target_rect is None:
            return False
        sx, sy = shooter_rect.centerx, shooter_rect.centery
        dx = target_rect.centerx - sx
        dy = target_rect.centery - sy
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return False
        dx /= length
        dy /= length
        projectiles.append(
            ProjectileState(
                sx,
                sy,
                dx * speed,
                dy * speed,
                radius=3,
                ttl=ttl))
        return True

    def step_players(self, dt: float):
        """Advance player simulation for one fixed-timestep tick."""
        if any(inp.restart for inp in self.inputs.values()):
            for inp in self.inputs.values():
                inp.restart = False
            self.reset_players_for_lobby()
            return

        for pid, player in list(self.players.items()):
            inp = self.inputs.get(pid)
            if inp is None or player.dead or player.won:
                continue

            level = self.ensure_level(player.current_level)
            cfg = MAP_DICT[f"lvl{player.current_level}"]

            player.shoot_timer = max(0.0, player.shoot_timer - dt)
            player.hurt_timer = max(0.0, player.hurt_timer - dt)
            player.jump_buffer = max(0.0, player.jump_buffer - dt)

            if inp.jump and not player.last_jump_down:
                player.jump_buffer = JUMP_BUFFER_TIME
            player.last_jump_down = inp.jump

            if inp.shoot and player.shoot_timer == 0.0:
                sx, sy = player.hitbox.centerx, player.hitbox.centery
                dx = inp.aim_x - sx
                dy = inp.aim_y - sy
                length = (dx * dx + dy * dy) ** 0.5
                if length > 0:
                    player.projectiles.append(
                        ProjectileState(
                            sx,
                            sy,
                            (dx / length) * BULLET_SPEED,
                            (dy / length) * BULLET_SPEED))
                    player.shoot_timer = player.shoot_cooldown

            player.vx = 0.0
            if inp.left:
                player.vx -= player.move_speed
            if inp.right:
                player.vx += player.move_speed

            player.vy += GRAVITY * dt
            player.vy, player.on_ground = move_and_collide(
                player.hitbox, player.vx, player.vy, level.solids, dt,
                allow_step=player.on_ground)

            chest_rect = self.chest_interaction_rect(level.chest_rect)
            if player.hitbox.colliderect(
                    chest_rect) and pid not in level.chest_claimed_by:
                level.chest_claimed_by.add(pid)
                level.chest_open = True
                player.chest_event_id += 1
                player.chest_event_level = player.current_level
                for reward in cfg.get("chest_reward", []):
                    self.apply_reward(player, reward)

            has_claimed = pid in level.chest_claimed_by
            if (not player.visual_advanced) and has_claimed and cfg.get(
                    "chest_change_map", False):
                next_level = player.current_level + 1
                if f"lvl{next_level}" in MAP_DICT:
                    player.current_level = next_level
                    player.visual_advanced = True
                    player.projectiles.clear()
                    self.ensure_level(next_level)
                    continue

            if (not player.visual_advanced) and len(
                    level.enemies) == 0 and cfg.get("cleared", False):
                next_level = player.current_level + 1
                if f"lvl{next_level}" in MAP_DICT:
                    player.current_level = next_level
                    player.visual_advanced = True
                    player.locked = False
                    player.projectiles.clear()
                    self.ensure_level(next_level)
                    continue

            can_exit = (
                not cfg.get(
                    "cleared",
                    False)) or (
                cfg.get(
                    "cleared",
                    False) and (
                    not player.locked))
            if player.hitbox.colliderect(level.end_rect) and can_exit:
                next_level = player.current_level + 1
                if f"lvl{next_level}" not in MAP_DICT:
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

    def step_levels(self, dt: float):
        """Advance enemies/projectiles and resolve combat for active levels."""
        for level_idx, level in list(self.levels.items()):
            players_here = [
                p for p in self.players.values() if (
                    not p.dead) and p.current_level == level_idx]

            for enemy in level.enemies:
                target = self.nearest_target(enemy.rect, players_here)
                enemy.shoot_timer = max(0.0, enemy.shoot_timer - dt)

                if enemy.enemy_type in ("Pancake", "Waffle", "Cookie"):
                    if target is None:
                        enemy.vx = 0.0
                    else:
                        enemy.vx = (
                            -ENEMY_SPEED
                            if target.centerx < enemy.rect.centerx
                            else ENEMY_SPEED
                        )
                    if enemy.shoot_timer == 0.0 and self.shoot_toward(
                            enemy.rect,
                            target,
                            level.enemy_projectiles,
                            ENEMY_BULLET_SPEED,
                            ENEMY_BULLET_TTL):
                        enemy.shoot_timer = enemy.shoot_cooldown
                elif enemy.enemy_type == "Amrany":
                    enemy.vx = 0.0
                    enemy.spawn_timer = max(0.0, enemy.spawn_timer - dt)
                    if enemy.spawn_timer == 0.0 and target is not None:
                        direction = (
                            -1 if target.centerx < enemy.rect.centerx else 1
                        )
                        spawn_x = enemy.rect.centerx + direction * \
                            ((enemy.rect.width // 2) + (ENEMY_SIZE // 2) + 6)
                        upper = enemy.rect.bottom - ENEMY_SIZE - 10
                        if upper <= enemy.rect.top:
                            spawn_y = enemy.rect.top
                        else:
                            spawn_y = random.randrange(enemy.rect.top, upper)
                        self.spawn_enemy(
                            level, "Cookie", int(
                                spawn_x - ENEMY_SIZE // 2), int(spawn_y))
                        enemy.spawn_timer = enemy.spawn_cooldown

                use_gravity = enemy.enemy_type != "Cookie"
                if use_gravity:
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
                    if player.hurt_timer == 0 and player.hitbox.colliderect(
                            enemy.rect):
                        player.hp -= 1
                        player.hurt_timer = INVINCIBILITY_TIME
                        player.vx = (
                            -250
                            if player.hitbox.centerx < enemy.rect.centerx
                            else 250
                        )
                        player.vy = -200

            for player in players_here:
                for proj in player.projectiles:
                    proj.update(dt)
                alive: list[ProjectileState] = []
                for proj in player.projectiles:
                    if proj.ttl <= 0:
                        continue
                    r = proj.rect
                    if (
                        r.right < 0
                        or r.left > level.width
                        or r.bottom < 0
                        or r.top > level.height
                    ):
                        continue
                    if any(r.colliderect(s) for s in level.solids):
                        continue
                    hit = False
                    for enemy in level.enemies:
                        if r.colliderect(enemy.rect):
                            enemy.hp -= 1
                            hit = True
                            break
                    if not hit:
                        alive.append(proj)
                player.projectiles = alive

            level.enemies = [e for e in level.enemies if e.hp > 0]

            for proj in level.enemy_projectiles:
                proj.update(dt)
            alive_enemy: list[ProjectileState] = []
            for proj in level.enemy_projectiles:
                if proj.ttl <= 0:
                    continue
                r = proj.rect
                if (
                    r.right < 0
                    or r.left > level.width
                    or r.bottom < 0
                    or r.top > level.height
                ):
                    continue
                if any(r.colliderect(s) for s in level.solids):
                    continue
                hit = False
                for player in players_here:
                    if r.colliderect(player.hitbox):
                        if MODE != 1:
                            player.hp -= 1
                        hit = True
                        break
                if not hit:
                    alive_enemy.append(proj)
            level.enemy_projectiles = alive_enemy

            for player in players_here:
                if player.hp <= 0:
                    player.dead = True
                    player.projectiles.clear()

    def apply_client_message(self, player_id: int, msg: dict):
        """Apply one input message payload to the stored player input state."""
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
        except Exception:
            inp.aim_x = float(default_x)
        try:
            inp.aim_y = float(msg.get("aim_y", default_y))
        except Exception:
            inp.aim_y = float(default_y)

    def apply_lobby_message(self, player_id: int, msg: dict):
        """Apply lobby updates for username, skin, and ready status."""
        player = self.players.get(player_id)
        if player is None or self.session_phase() != "lobby":
            return
        username_raw = str(msg.get("username", "")).strip()
        if username_raw:
            player.username = username_raw[:20]
        skin_raw = str(msg.get("skin", "")).strip()
        if skin_raw in self.available_skins:
            player.skin = skin_raw
        player.ready = bool(msg.get("ready", False))

    def build_snapshot(self, player_id: int) -> dict:
        """Build the world snapshot payload sent to one specific player."""
        player = self.players[player_id]
        snapshot_level = player.current_level
        spectating_player_id = None
        if player.dead and not player.won:
            for pid, other in sorted(self.players.items()):
                if pid != player_id and not other.dead:
                    spectating_player_id = pid
                    snapshot_level = other.current_level
                    break

        level = self.ensure_level(snapshot_level)
        chest_rect = self.chest_interaction_rect(level.chest_rect)
        can_interact_chest = (
            (not player.dead)
            and player.current_level == snapshot_level
            and player.hitbox.colliderect(chest_rect)
            and player_id not in level.chest_claimed_by
        )

        players_payload = []
        for pid, other in sorted(self.players.items()):
            if other.current_level == snapshot_level:
                projs = [
                    {"x": p.x, "y": p.y, "radius": p.radius}
                    for p in other.projectiles
                ]
            else:
                projs = []
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
                    "projectiles": projs,
                }
            )

        enemies_payload = [
            {
                "id": e.enemy_id,
                "type": e.enemy_type,
                "x": e.rect.x,
                "y": e.rect.y,
                "w": e.rect.w,
                "h": e.rect.h,
                "vx": e.vx,
                "hp": e.hp,
                "max_hp": e.max_hp,
            }
            for e in level.enemies
        ]
        enemy_projectiles_payload = [
            {"x": p.x, "y": p.y, "radius": p.radius}
            for p in level.enemy_projectiles]

        return {
            "type": "state",
            "tick": self.tick,
            "you": player_id,
            "spectating_player_id": spectating_player_id,
            "session": {
                "connected_players": len(self.players),
                "required_players": self.max_players,
                "ready": self.match_started or self.all_players_ready(),
                "phase": self.session_phase(),
                "available_skins": self.available_skins,
            },
            "level_size": {"w": level.width, "h": level.height},
            "players": players_payload,
            "world": {
                "current_level": snapshot_level,
                "chest": {
                    "x": level.chest_rect.x,
                    "y": level.chest_rect.y,
                    "w": level.chest_rect.w,
                    "h": level.chest_rect.h,
                    "open": level.chest_open,
                    "can_interact": can_interact_chest,
                    "claimed_by_you": player_id in level.chest_claimed_by,
                },
                "enemies": enemies_payload,
                "enemy_projectiles": enemy_projectiles_payload,
                "locked": player.locked,
            },
        }

    async def send_json(self, conn: asyncio.StreamWriter, payload: dict):
        """Serialize and send one JSON payload over an asyncio stream."""
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        conn.write(f"{len(body)}#".encode("ascii") + body)
        await conn.drain()

    async def read_json(self, reader: asyncio.StreamReader) -> dict:
        """Read one length-prefixed JSON payload from the stream."""
        header = await reader.readuntil(b"#")
        if not header:
            raise ValueError("Missing frame header")

        header_digits = header[:-1]
        if (
            (not header_digits)
            or (len(header_digits) > MAX_HEADER_BYTES)
            or (not header_digits.isdigit())
        ):
            raise ValueError("Invalid frame header")

        body_len = int(header_digits.decode("ascii"))
        if body_len > MAX_FRAME_BYTES:
            raise ValueError("Frame too large")

        body = await reader.readexactly(body_len)
        return json.loads(body.decode("utf-8"))

    async def remove_player(self, player_id: int):
        """Remove a player connection and reset/cleanup match state."""
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
            logger.info("All players disconnected; world reset")
        else:
            self.reset_players_for_lobby()
            logger.info(
                "Player %s removed; returning remaining players to lobby",
                player_id)

    async def game_loop(self):
        """Run simulation ticks and broadcast snapshots continuously."""
        tick_dt = 1.0 / FPS
        while True:
            if (not self.match_started) and self.all_players_ready():
                self.start_match()
                logger.info("All players ready; match started")
            if self.match_started and self.players_connected():
                self.step_players(tick_dt)
                self.step_levels(tick_dt)
                if self.players and all(
                        p.dead for p in self.players.values()) and all(
                        not p.won for p in self.players.values()):
                    self.reset_players_for_lobby()
                    logger.info("All players died; reset to lobby")

            for pid, writer in list(self.writers.items()):
                if pid not in self.players:
                    continue
                try:
                    await self.send_json(writer, self.build_snapshot(pid))
                except Exception:
                    logger.exception(
                        "Failed to send snapshot to player %s", pid)
                    await self.remove_player(pid)

            self.tick += 1
            await asyncio.sleep(tick_dt)

    async def handle_client(
            self,
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter):
        """Handle one client connection for lobby/input message processing."""
        if not self.players:
            self.match_started = False
            self.reset_dynamic_world()

        player_id = self.next_free_player_id()
        if player_id is None:
            with suppress(Exception):
                await self.send_json(
                    writer,
                    {"type": "error", "message": "Already In Session"},
                )
                writer.close()
                await writer.wait_closed()
            logger.warning("Rejected connection because session is full")
            return

        self.players[player_id] = self.create_player(player_id)
        self.writers[player_id] = writer
        self.reset_players_for_lobby()
        logger.info("Player %s connected", player_id)

        with suppress(Exception):
            await self.send_json(
                writer,
                {
                    "type": "welcome",
                    "player_id": player_id,
                    "tick_rate": FPS,
                    "max_players": self.max_players,
                },
            )

        try:
            while True:
                try:
                    msg = await self.read_json(reader)
                except asyncio.IncompleteReadError:
                    break
                except asyncio.LimitOverrunError:
                    logger.warning(
                        "Received oversized frame header from player %s",
                        player_id)
                    break
                except ValueError:
                    logger.warning(
                        "Received invalid framed payload from player %s",
                        player_id)
                    break
                except Exception:
                    logger.warning(
                        "Received invalid JSON from player %s", player_id)
                    continue
                msg_type = msg.get("type")
                if msg_type == "input":
                    self.apply_client_message(player_id, msg)
                elif msg_type == "lobby":
                    self.apply_lobby_message(player_id, msg)
        finally:
            logger.info("Player %s disconnected", player_id)
            await self.remove_player(player_id)

    async def run(self):
        """Start TCP server, run game loop task, and serve forever."""
        tcp_server = await asyncio.start_server(
            self.handle_client,
            self.host,
            self.port,
        )
        sockets = ", ".join(str(sock.getsockname())
                            for sock in (tcp_server.sockets or []))
        logger.info("Dungeon TCP server listening on %s", sockets)
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
