from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from src.classes.ProjectileState import ProjectileState
from src.settings import BASE_HEARTS, BASE_SHOOT_COOLDOWN, MOVE_SPEED, STARTING_LVL


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
    projectiles: list[ProjectileState] = field(default_factory=list)
