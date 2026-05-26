from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from src.classes.EnemyState import EnemyState
from src.classes.ProjectileState import ProjectileState


@dataclass
class LevelState:
    level: int
    solids: list[pygame.Rect]
    end_rect: pygame.Rect
    chest_rect: pygame.Rect
    width: int
    height: int
    enemies: list[EnemyState] = field(default_factory=list)
    next_enemy_id: int = 1
    chest_open: bool = False
    chest_claimed_by: set[int] = field(default_factory=set)
    enemy_projectiles: list[ProjectileState] = field(default_factory=list)
