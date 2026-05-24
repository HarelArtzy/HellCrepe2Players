from __future__ import annotations

from dataclasses import dataclass

import pygame

from settings import BULLET_RADIUS, BULLET_TTL


@dataclass
class ProjectileState:
    """Projectile state used in simulation and rendering."""

    x: float
    y: float
    vx: float
    vy: float
    radius: int = BULLET_RADIUS
    ttl: float = BULLET_TTL

    @property
    def rect(self) -> pygame.Rect:
        """Return the current projectile collision rectangle."""
        return pygame.Rect(
            int(self.x - self.radius),
            int(self.y - self.radius),
            self.radius * 2,
            self.radius * 2,
        )

    def update(self, dt: float) -> None:
        """Advance projectile position and decrease remaining lifetime."""
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.ttl -= dt
