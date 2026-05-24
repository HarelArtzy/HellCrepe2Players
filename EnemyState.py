from __future__ import annotations

from dataclasses import dataclass

import pygame

from settings import ENEMY_SHOOT_COOLDOWN


@dataclass
class EnemyState:
    enemy_id: int
    enemy_type: str
    rect: pygame.Rect
    hp: int
    max_hp: int
    vx: float = 0.0
    vy: float = 0.0
    shoot_timer: float = 0.0
    shoot_cooldown: float = ENEMY_SHOOT_COOLDOWN
    spawn_timer: float = 0.0
    spawn_cooldown: float = ENEMY_SHOOT_COOLDOWN
    on_ground: bool = False
