from __future__ import annotations

import pygame
from env_config import ASSETS_DIR


class Player:
    def __init__(self, x: int, y: int, skin_name: str | None = None):
        """Create a player sprite and load frames for the chosen skin."""
        self.hitbox = pygame.Rect(x, y, 16, 22)
        self.sprite_w, self.sprite_h = 32, 32
        self.sprite_offset_x = -8
        self.sprite_offset_y = -10
        self.skin_name = skin_name or "default"

        if self.skin_name != "default":
            skin_dir = ASSETS_DIR / "player" / self.skin_name
            paths = [
                skin_dir /
                "player_frame1.png",
                skin_dir /
                "player_frame2.png"]
        else:
            paths = [
                ASSETS_DIR / "player" / "player_frame1.png",
                ASSETS_DIR / "player" / "player_frame2.png",
            ]
        if not all(path.exists() for path in paths):
            self.skin_name = "default"
            paths = [
                ASSETS_DIR / "player" / "player_frame1.png",
                ASSETS_DIR / "player" / "player_frame2.png",
            ]

        self.frames = [
            pygame.transform.scale(
                pygame.image.load(str(path)).convert_alpha(),
                (self.sprite_w, self.sprite_h),
            )
            for path in paths
        ]
        self.image = self.frames[0]
        self.vx = 0.0
        self.anim_timer = 0.0
        self.anim_speed = 0.5
        self.frame_index = 0

    @property
    def draw_pos(self):
        """Return the sprite draw position relative to the player's hitbox."""
        return (
            self.hitbox.x + self.sprite_offset_x,
            self.hitbox.y + self.sprite_offset_y,
        )

    def update_animation(self, dt: float):
        """Advance the animation timer and set the current facing frame."""
        self.anim_timer += dt
        if self.anim_timer >= self.anim_speed:
            self.anim_timer = 0.0
            self.frame_index = (self.frame_index + 1) % len(self.frames)
        img = self.frames[self.frame_index]
        if self.vx < 0:
            img = pygame.transform.flip(img, True, False)
        self.image = img
