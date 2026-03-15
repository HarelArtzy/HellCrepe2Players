# classes.py
import pygame
from pathlib import Path
from settings import *
import random


class Player:
    def __init__(self, x, y, skin_name: str | None = None):
        self.hitbox = pygame.Rect(x, y, 16, 22)

        self.sprite_w, self.sprite_h = 32, 32
        self.sprite_offset_x = -8
        self.sprite_offset_y = -10

        self.skin_name = skin_name or "default"

        root = Path(__file__).resolve().parent
        if self.skin_name != "default":
            skin_dir = root / "assets" / "player" / self.skin_name
            frame_paths = [
                skin_dir / "player_frame1.png",
                skin_dir / "player_frame2.png",
            ]
        else:
            frame_paths = [
                root / "assets" / "player" / "player_frame1.png",
                root / "assets" / "player" / "player_frame2.png",
            ]

        if not all(path.exists() for path in frame_paths):
            frame_paths = [
                root / "assets" / "player" / "player_frame1.png",
                root / "assets" / "player" / "player_frame2.png",
            ]
            self.skin_name = "default"

        self.frames = [
            pygame.image.load(str(frame_paths[0])).convert_alpha(),
            pygame.image.load(str(frame_paths[1])).convert_alpha()
        ]
        self.frames = [pygame.transform.scale(img, (self.sprite_w, self.sprite_h)) for img in self.frames]
        self.image = self.frames[0]

        self.hp = 3
        self.max_hp = 3

        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.move_speed = MOVE_SPEED

        self.anim_timer = 0.0
        self.anim_speed = 0.5
        self.frame_index = 0

        self.jump_buffer = 0.0
        self.hurt_timer = 0.0

        self.shoot_timer = 0.0
        self.shoot_cooldown = BASE_SHOOT_COOLDOWN

    @property
    def draw_pos(self):
        return self.hitbox.x + self.sprite_offset_x, self.hitbox.y + self.sprite_offset_y

    def update_animation(self, dt):
        self.anim_timer += dt
        if self.anim_timer >= self.anim_speed:
            self.anim_timer = 0.0
            self.frame_index = (self.frame_index + 1) % len(self.frames)

        img = self.frames[self.frame_index]
        if self.vx < 0:
            img = pygame.transform.flip(img, True, False)
        self.image = img


class Projectile:
    def __init__(self, x, y, vx, vy, radius=BULLET_RADIUS, ttl=BULLET_TTL):
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        self.radius = int(radius)
        self.ttl = float(ttl)

    @property
    def rect(self):
        return pygame.Rect(
            int(self.x - self.radius),
            int(self.y - self.radius),
            self.radius * 2,
            self.radius * 2
        )

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.ttl -= dt

    def draw(self, screen):
        pygame.draw.circle(screen, (255, 220, 120), (int(self.x), int(self.y)), self.radius)


class Enemy:
    def __init__(self, x, y, image_paths):
        self.rect = pygame.Rect(x, y, ENEMY_SIZE, ENEMY_SIZE)

        if isinstance(image_paths, str):
            image_paths = [image_paths]

        self.frames = [pygame.image.load(p).convert_alpha() for p in image_paths]
        self.frames = [pygame.transform.scale(img, (ENEMY_SIZE, ENEMY_SIZE)) for img in self.frames]
        self.image = self.frames[0]

        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False

        self.hp = 1

        self.shoot_timer = 0.0
        self.shoot_cooldown = ENEMY_SHOOT_COOLDOWN

        self.anim_timer = 0.0
        self.anim_speed = 0.25
        self.frame_index = 0

    def update_animation(self, dt):
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

    def update(self, dt, player_rect, enemy_projectiles, enemies, solids=None):
        self.update_ai(dt, player_rect, enemies, solids)
        self.update_animation(dt)
        self.shoot_timer = max(0.0, self.shoot_timer - dt)
        self.try_shoot(player_rect, enemy_projectiles, enemies)

    def update_ai(self, dt, player_rect, enemies, solids):
        pass

    def try_shoot(self, player_rect, enemy_projectiles, enemies):
        pass

    def draw(self, screen):
        screen.blit(self.image, self.rect)


class Pancake(Enemy):
    def __init__(self, x, y):
        super().__init__(x, y, [
            "assets/enemies/pancake/pancake_frame1.png",
            "assets/enemies/pancake/pancake_frame1.png"
        ])
        self.use_gravity = True

    def update_ai(self, dt, player_rect, enemies, solids):
        if player_rect.centerx < self.rect.centerx:
            self.vx = -ENEMY_SPEED
        else:
            self.vx = ENEMY_SPEED

    def try_shoot(self, player_rect, enemy_projectiles, enemies):
        if self.shoot_timer > 0:
            return

        sx, sy = self.rect.centerx, self.rect.centery
        dx = player_rect.centerx - sx
        dy = player_rect.centery - sy
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return

        dx /= length
        dy /= length

        vx = dx * ENEMY_BULLET_SPEED
        vy = dy * ENEMY_BULLET_SPEED

        enemy_projectiles.append(Projectile(sx, sy, vx, vy, radius=3, ttl=ENEMY_BULLET_TTL))
        self.shoot_timer = self.shoot_cooldown


class Waffle(Enemy):
    def __init__(self, x, y):
        super().__init__(x, y, [
            "assets/enemies/waffle/waffle_frame1.png",
            "assets/enemies/waffle/waffle_frame2.png"
        ])
        self.use_gravity = True

    def update_ai(self, dt, player_rect, enemies, solids):
        if player_rect.centerx < self.rect.centerx:
            self.vx = -ENEMY_SPEED
        else:
            self.vx = ENEMY_SPEED

    def try_shoot(self, player_rect, enemy_projectiles, enemies):
        if self.shoot_timer > 0:
            return

        sx, sy = self.rect.centerx, self.rect.centery
        dx = player_rect.centerx - sx
        dy = player_rect.centery - sy
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return

        dx /= length
        dy /= length

        vx = dx * ENEMY_BULLET_SPEED
        vy = dy * ENEMY_BULLET_SPEED

        enemy_projectiles.append(Projectile(sx, sy, vx, vy, radius=3, ttl=ENEMY_BULLET_TTL))
        self.shoot_timer = self.shoot_cooldown


class Cookie(Enemy):
    def __init__(self, x, y):
        super().__init__(x, y, [
            "assets/enemies/cookie/cookie_frame1.png",
            "assets/enemies/cookie/cookie_frame1.png"
        ])
        self.use_gravity = False

    def update_ai(self, dt, player_rect, enemies, solids):
        if player_rect.centerx < self.rect.centerx:
            self.vx = -ENEMY_SPEED
        else:
            self.vx = ENEMY_SPEED

    def try_shoot(self, player_rect, enemy_projectiles, enemies):
        if self.shoot_timer > 0:
            return

        sx, sy = self.rect.centerx, self.rect.centery
        dx = player_rect.centerx - sx
        dy = player_rect.centery - sy
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return

        dx /= length
        dy /= length

        vx = dx * ENEMY_BULLET_SPEED
        vy = dy * ENEMY_BULLET_SPEED

        enemy_projectiles.append(Projectile(sx, sy, vx, vy, radius=3, ttl=ENEMY_BULLET_TTL))
        self.shoot_timer = self.shoot_cooldown


class Amrany(Enemy):
    def __init__(self, x, y):
        paths = [
            "assets/enemies/Amrany/Amrany_frame1.png",
            "assets/enemies/Amrany/Amrany_frame2.png"
        ]
        super().__init__(x, y, paths)
        self.use_gravity = True

        self.spawn_cooldown = ENEMY_SHOOT_COOLDOWN
        self.spawn_timer = 0.0

        self.rect = pygame.Rect(x, y, 64, 144)

        self.frames = [pygame.image.load(p).convert_alpha() for p in paths]
        self.frames = [pygame.transform.scale(img, (64, 144)) for img in self.frames]
        self.image = self.frames[0]

        self.hp = 67
        self.max_hp = 67

    def update_ai(self, dt, player_rect, enemies, solids):
        self.vx = 0.0

    def update(self, dt, player_rect, enemy_projectiles, enemies, solids=None):
        self.update_ai(dt, player_rect, enemies, solids)
        self.update_animation(dt)
        self.spawn_timer = max(0.0, self.spawn_timer - dt)
        self.try_shoot(player_rect, enemy_projectiles, enemies)

    def try_shoot(self, player_rect, enemy_projectiles, enemies):
        if self.spawn_timer > 0:
            return

        direction = -1 if player_rect.centerx < self.rect.centerx else 1
        x_offset = (self.rect.width // 2) + (ENEMY_SIZE // 2) + 6
        spawn_x = self.rect.centerx + direction * x_offset
        spawn_y = random.randrange(self.rect.top, self.rect.bottom - ENEMY_SIZE-10)
        enemies.append(Cookie(int(spawn_x - ENEMY_SIZE // 2), int(spawn_y)))

        self.spawn_timer = self.spawn_cooldown
