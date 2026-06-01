from __future__ import annotations

import pygame

from env_config import ASSETS_DIR
from settings import ENEMY_SIZE


class EnemySprite:
    def __init__(self, enemy_type: str, x: int, y: int):
        """Create a renderable enemy sprite with frames based on enemy type."""
        self.enemy_type = enemy_type
        configs = {
            "Pancake": (
                [
                    "enemies/pancake/pancake_frame1.png",
                    "enemies/pancake/pancake_frame1.png",
                ],
                (ENEMY_SIZE, ENEMY_SIZE),
            ),
            "Waffle": (
                [
                    "enemies/waffle/waffle_frame1.png",
                    "enemies/waffle/waffle_frame2.png",
                ],
                (ENEMY_SIZE, ENEMY_SIZE),
            ),
            "Cookie": (
                [
                    "enemies/cookie/cookie_frame1.png",
                    "enemies/cookie/cookie_frame1.png",
                ],
                (ENEMY_SIZE, ENEMY_SIZE),
            ),
            "Amrany": (
                [
                    "enemies/Amrany/Amrany_frame1.png",
                    "enemies/Amrany/Amrany_frame2.png",
                ],
                (64, 144),
            ),
        }
        paths, (w, h) = configs.get(enemy_type, configs["Cookie"])
        self.rect = pygame.Rect(x, y, w, h)
        self.frames = [
            pygame.transform.scale(
                pygame.image.load(str(ASSETS_DIR / path)).convert_alpha(),
                (w, h),
            )
            for path in paths
        ]
        self.image = self.frames[0]
        self.vx = 0.0
        self.anim_timer = 0.0
        self.anim_speed = 0.25
        self.frame_index = 0

    def update_animation(self, dt: float):
        """Update enemy animation frames while preserving facing direction."""
        if len(self.frames) <= 1:
            return
        self.anim_timer += dt
        if self.anim_timer >= self.anim_speed:
            self.anim_timer = 0.0
            self.frame_index = (self.frame_index + 1) % len(self.frames)
        img = self.frames[self.frame_index]
        if self.vx < 0:
            img = pygame.transform.flip(img, True, False)
        self.image = img

    def draw(self, screen: pygame.Surface):
        """Draw the current enemy frame to the target surface."""
        screen.blit(self.image, self.rect)
