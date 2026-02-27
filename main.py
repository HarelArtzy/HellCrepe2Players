import sys
import pygame
from pytmx.util_pygame import load_pygame

# Window matches your earlier size
BASE_W, BASE_H = 512, 128
SCALE = 3
FPS = 60

GRAVITY = 2200.0
MOVE_SPEED = 260.0
JUMP_VEL = 540.0

# Shooting
BULLET_SPEED = 900.0
BULLET_TTL = 1.2
BULLET_RADIUS = 3
SHOOT_COOLDOWN = 0.5

ENEMY_SPEED = 120.0
ENEMY_SHOOT_COOLDOWN = 0.9
ENEMY_BULLET_SPEED = 520.0
ENEMY_BULLET_TTL = 2.0
ENEMY_SIZE = 32

class Player:
    def __init__(self, x, y):
        self.rect = pygame.Rect(x, y, 32, 32)

        # Load 2 frames
        self.frames = [
            pygame.image.load("assets/player/player_frame1.png").convert_alpha(),
            pygame.image.load("assets/player/player_frame2.png").convert_alpha()
        ]

        # Scale if needed
        self.frames = [pygame.transform.scale(img, (32, 32)) for img in self.frames]

        self.image = self.frames[0]

        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False

        # Animation
        self.anim_timer = 0.0
        self.anim_speed = 0.5  # seconds per frame
        self.frame_index = 0

    def jump(self):
        if self.on_ground:
            self.vy = -JUMP_VEL
            self.on_ground = False

    def update_animation(self, dt):
        self.anim_timer += dt

        if self.anim_timer >= self.anim_speed:
            self.anim_timer = 0
            self.frame_index = (self.frame_index + 1) % 2

        self.image = self.frames[self.frame_index]

        # Flip when moving left
        if self.vx < 0:
            self.image = pygame.transform.flip(self.image, True, False)


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


def move_and_collide(rect: pygame.Rect, vx: float, vy: float, solids: list[pygame.Rect], dt: float):
    # Move X
    rect.x += int(vx * dt)
    for s in solids:
        if rect.colliderect(s):
            if vx > 0:
                rect.right = s.left
            elif vx < 0:
                rect.left = s.right

    on_ground = False

    # Move Y
    rect.y += int(vy * dt)
    for s in solids:
        if rect.colliderect(s):
            if vy > 0:  # falling
                rect.bottom = s.top
                vy = 0
                on_ground = True
            elif vy < 0:  # jumping
                rect.top = s.bottom
                vy = 0

    return vy, on_ground

class Enemy:
    def __init__(self, x, y, image_path):
        self.rect = pygame.Rect(x, y, ENEMY_SIZE, ENEMY_SIZE)

        self.image = pygame.image.load(image_path).convert_alpha()
        self.image = pygame.transform.scale(self.image, (ENEMY_SIZE, ENEMY_SIZE))

        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False

        self.hp = 3

        # Shooting system
        self.shoot_timer = 0.0
        self.shoot_cooldown = ENEMY_SHOOT_COOLDOWN

    def update(self, dt, player_rect, enemy_projectiles):
        # Movement logic defined by subclass
        self.update_ai(dt, player_rect)

        # Cooldown tick
        self.shoot_timer = max(0.0, self.shoot_timer - dt)

        # Shooting decision defined by subclass
        self.try_shoot(player_rect, enemy_projectiles)

    def update_ai(self, dt, player_rect):
        pass  # overridden in subclass

    def try_shoot(self, player_rect, enemy_projectiles):
        pass  # overridden in subclass

    def draw(self, screen):
        screen.blit(self.image, self.rect)

class Pancake(Enemy):
    def __init__(self, x, y):
        super().__init__(x, y, "assets/enemies/pancake/pancake_frame1.png")

    def update_ai(self, dt, player_rect):
        # Simple horizontal chase
        if player_rect.centerx < self.rect.centerx:
            self.vx = -ENEMY_SPEED
        else:
            self.vx = ENEMY_SPEED

    def try_shoot(self, player_rect, enemy_projectiles):
        if self.shoot_timer > 0:
            return

        # Shoot toward player
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

        enemy_projectiles.append(
            Projectile(sx, sy, vx, vy, radius=3, ttl=ENEMY_BULLET_TTL)
        )

        self.shoot_timer = self.shoot_cooldown


def build_collision_rects(tmx, layer_name: str):
    tile_w = tmx.tilewidth
    tile_h = tmx.tileheight

    layer = tmx.get_layer_by_name(layer_name)
    solids = []
    for x, y, gid in layer:
        if gid != 0:
            solids.append(pygame.Rect(x * tile_w, y * tile_h, tile_w, tile_h))
    return solids


def draw_tmx(screen, tmx):
    # Draw in layer order as in Tiled
    for layer in tmx.visible_layers:
        # Skip collision layer even if visible
        if getattr(layer, "name", "") == "Collision":
            continue

        if hasattr(layer, "data"):  # TileLayer
            for x, y, gid in layer:
                tile = tmx.get_tile_image_by_gid(gid)
                if tile:
                    screen.blit(tile, (x * tmx.tilewidth, y * tmx.tileheight))


def shoot(projectiles: list, player: Player):
    mx, my = pygame.mouse.get_pos()
    mx //= SCALE
    my //= SCALE
    sx, sy = player.rect.centerx, player.rect.centery

    dx = mx - sx
    dy = my - sy
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return

    dx /= length
    dy /= length

    vx = dx * BULLET_SPEED
    vy = dy * BULLET_SPEED

    projectiles.append(Projectile(sx, sy, vx, vy))


def main():
    pygame.init()
    window = pygame.display.set_mode((BASE_W * SCALE, BASE_H * SCALE))
    screen = pygame.Surface((BASE_W, BASE_H))
    pygame.display.set_caption("Tiled TMX + Collision + Jump + Shoot")
    clock = pygame.time.Clock()

    # Load TMX
    tmx = load_pygame("assets/maps/level1.tmx")

    # Build collision rects from your Collision tile layer
    solids = build_collision_rects(tmx, "Collision")

    # Spawn player somewhere safe (top-left-ish)
    player = Player(60, 20)

    enemies = [Pancake(280, 20)]
    enemy_projectiles = []

    # Projectiles + cooldown
    projectiles = []
    shoot_timer = 0.0

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        shoot_timer = max(0.0, shoot_timer - dt)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_SPACE, pygame.K_w, pygame.K_UP):
                    player.jump()

            # Left click to shoot
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if shoot_timer == 0.0:
                    shoot(projectiles, player)
                    shoot_timer = SHOOT_COOLDOWN

        keys = pygame.key.get_pressed()
        player.vx = 0.0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            player.vx = -MOVE_SPEED
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            player.vx = MOVE_SPEED

        # Gravity
        player.vy += GRAVITY * dt

        # Move + collide with tile solids
        player.vy, player.on_ground = move_and_collide(player.rect, player.vx, player.vy, solids, dt)

        for e in enemies:
            e.update(dt, player.rect, enemy_projectiles)

            # Apply gravity
            e.vy += GRAVITY * dt
            e.vy, e.on_ground = move_and_collide(e.rect, e.vx, e.vy, solids, dt)

        player.update_animation(dt)

        # Update projectiles
        for p in projectiles:
            p.update(dt)

        # Remove projectiles that expire, leave screen, or hit walls
        alive = []
        for p in projectiles:
            if p.ttl <= 0:
                continue

            r = p.rect
            if r.right < 0 or r.left > BASE_W or r.bottom < 0 or r.top > BASE_H:
                continue

            hit_wall = False
            for s in solids:
                if r.colliderect(s):
                    hit_wall = True
                    break
            if hit_wall:
                continue

            alive.append(p)
        projectiles = alive

        for p in enemy_projectiles:
            p.update(dt)

        alive_enemy = []
        for p in enemy_projectiles:
            if p.ttl <= 0:
                continue

            r = p.rect
            if r.right < 0 or r.left > BASE_W or r.bottom < 0 or r.top > BASE_H:
                continue

            hit_wall = False
            for s in solids:
                if r.colliderect(s):
                    hit_wall = True
                    break
            if hit_wall:
                continue

            # Hit player
            if r.colliderect(player.rect):
                # TODO: player.hp -= 1
                continue  # bullet disappears on hit

            alive_enemy.append(p)

        enemy_projectiles = alive_enemy

        # Draw
        screen.fill((15, 15, 20))
        draw_tmx(screen, tmx)

        # Draw bullets (behind player is fine; swap order if you want)
        for p in projectiles:
            p.draw(screen)

        # Draw player
        screen.blit(player.image, player.rect)

        # Draw enemy bullets
        for p in enemy_projectiles:
            p.draw(screen)

        # Draw enemies
        for e in enemies:
            e.draw(screen)

        scaled = pygame.transform.scale(screen, (BASE_W * SCALE, BASE_H * SCALE))
        window.blit(scaled, (0, 0))
        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()