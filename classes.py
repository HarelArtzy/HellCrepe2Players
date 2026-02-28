import pygame
from settings import *


class Player:
    def __init__(self, x, y):
        self.hitbox = pygame.Rect(x, y, 16, 22)

        self.sprite_w, self.sprite_h = 32, 32
        self.sprite_offset_x = -8
        self.sprite_offset_y = -10

        self.frames = [
            pygame.image.load("assets/player/player_frame1.png").convert_alpha(),
            pygame.image.load("assets/player/player_frame2.png").convert_alpha()
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

    def update(self, dt, player_rect, enemy_projectiles):
        self.update_ai(dt, player_rect)
        self.update_animation(dt)
        self.shoot_timer = max(0.0, self.shoot_timer - dt)
        self.try_shoot(player_rect, enemy_projectiles)

    def update_ai(self, dt, player_rect):
        pass

    def try_shoot(self, player_rect, enemy_projectiles):
        pass

    def draw(self, screen):
        screen.blit(self.image, self.rect)


class Pancake(Enemy):
    def __init__(self, x, y):
        super().__init__(x, y, [
            "assets/enemies/pancake/pancake_frame1.png",
            "assets/enemies/pancake/pancake_frame1.png"
        ])

    def update_ai(self, dt, player_rect):
        if player_rect.centerx < self.rect.centerx:
            self.vx = -ENEMY_SPEED
        else:
            self.vx = ENEMY_SPEED

    def try_shoot(self, player_rect, enemy_projectiles):
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

    def update_ai(self, dt, player_rect):
        if player_rect.centerx < self.rect.centerx:
            self.vx = -ENEMY_SPEED
        else:
            self.vx = ENEMY_SPEED

    def try_shoot(self, player_rect, enemy_projectiles):
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