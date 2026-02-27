import sys

import pygame
from pytmx.util_pygame import load_pygame

BASE_W, BASE_H = 800, 160
SCALE = 3
FPS = 60

GRAVITY = 2200.0
MOVE_SPEED = 260.0
JUMP_VEL = 540.0

BULLET_SPEED = 900.0
BULLET_TTL = 1.2
BULLET_RADIUS = 3
BASE_SHOOT_COOLDOWN = 0.5
JUMP_BUFFER_TIME = 0.12
INVINCIBILITY_TIME = 0.8

ENEMY_SPEED = 120.0
ENEMY_SHOOT_COOLDOWN = 0.9
ENEMY_BULLET_SPEED = 520.0
ENEMY_BULLET_TTL = 2.0
ENEMY_SIZE = 32

MAX_STEP_HEIGHT = 16

MODE = 0

MAP_DICT = {
    "lvl1": {
        "map": "assets/maps/map1",
        "start": (60, 20),
        "end": (750, 70),
        "chest": (646, 45),
        "enemies": [("Pancake", (400, 100))],
        "chest_msg": ["Chest:\n Increase fire rate by 25%!\n Press Space to continue"],
        "chest_reward": [("shoot_cooldown", "mul", 0.75)],
        "hearts": 3
    },
    "lvl2": {
        "map": "assets/maps/map2",
        "start": (60, 140),
        "end": (380, 140),
        "chest": (208, 70),
        "enemies": [],
        "chest_msg": [
            'Mysterious Statue:\n "You are going to need\nthis when you face\nthe devourer of crepes"\n Press Space to continue',
            "You gained an extra heart!"
        ],
        "chest_reward": [("max_hp", "add", 1), ("hp", "add", 1)],
        "hearts": 3
    }
}


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
            self.frame_index = (self.frame_index + 1) % 2

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


def move_and_collide(rect: pygame.Rect, vx: float, vy: float, solids: list[pygame.Rect], dt: float, allow_step: bool):
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


class Enemy:
    def __init__(self, x, y, image_path):
        self.rect = pygame.Rect(x, y, ENEMY_SIZE, ENEMY_SIZE)
        self.image = pygame.image.load(image_path).convert_alpha()
        self.image = pygame.transform.scale(self.image, (ENEMY_SIZE, ENEMY_SIZE))

        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False

        self.hp = 1

        self.shoot_timer = 0.0
        self.shoot_cooldown = ENEMY_SHOOT_COOLDOWN

    def update(self, dt, player_rect, enemy_projectiles):
        self.update_ai(dt, player_rect)
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
        super().__init__(x, y, "assets/enemies/pancake/pancake_frame1.png")

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
    for layer in tmx.visible_layers:
        if getattr(layer, "name", "") == "Collision":
            continue
        if hasattr(layer, "data"):
            for x, y, gid in layer:
                tile = tmx.get_tile_image_by_gid(gid)
                if tile:
                    screen.blit(tile, (x * tmx.tilewidth, y * tmx.tileheight))


def shoot(projectiles: list, player: Player):
    mx, my = pygame.mouse.get_pos()
    mx //= SCALE
    my //= SCALE

    sx, sy = player.hitbox.centerx, player.hitbox.centery
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


def display_text(window, screen, msg, color, base_w, base_h, scale, font_name="Arial", font_size=24):
    screen.fill((15, 15, 20))
    font = pygame.font.SysFont(font_name, font_size)
    lines = msg.splitlines() if "\n" in msg else [msg]

    rendered = [font.render(line, True, color) for line in lines]
    line_h = font.get_linesize()

    total_h = len(rendered) * line_h
    start_y = (base_h - total_h) // 2

    for i, surf in enumerate(rendered):
        rect = surf.get_rect()
        rect.centerx = base_w // 2
        rect.y = start_y + i * line_h
        screen.blit(surf, rect)

    scaled = pygame.transform.scale(screen, (base_w * scale, base_h * scale))
    window.blit(scaled, (0, 0))
    pygame.display.flip()


def pause_menu(window, screen, clock):
    while True:
        display_text(
            window, screen,
            "Game Paused.\nPress Space or Esc to resume.\nPress 'r' to restart.\nPress 'q' to quit",
            pygame.Color("white"),
            BASE_W, BASE_H, SCALE
        )
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    return "restart"
                if event.key == pygame.K_q:
                    return "quit"
                if event.key in (pygame.K_SPACE, pygame.K_ESCAPE):
                    pygame.event.clear(pygame.KEYDOWN)
                    return "resume"


def end_menu(window, screen, clock, msg):
    while True:
        display_text(window, screen, msg, pygame.Color("white"), BASE_W, BASE_H, SCALE)
        clock.tick(30)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    return "restart"
                if event.key == pygame.K_q:
                    return "quit"


def open_chest(window, screen, clock, level):
    level_str = "lvl" + str(level)
    msg = MAP_DICT[level_str]["chest_msg"]
    for m in msg:
        active = True
        while active:
            display_text(
                window, screen,
                m,
                pygame.Color("white"),
                BASE_W, BASE_H, SCALE
            )
            clock.tick(30)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "quit"
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        pygame.event.clear(pygame.KEYDOWN)
                        active = False
    return None


def load_level(path):
    tmx = load_pygame(path)
    solids = build_collision_rects(tmx, "Collision")
    return tmx, solids


def apply_reward(player: Player, reward):
    attr, op, val = reward
    cur = getattr(player, attr)
    if op == "add":
        setattr(player, attr, cur + val)
    elif op == "mul":
        setattr(player, attr, cur * val)
    elif op == "set":
        setattr(player, attr, val)

    if attr in ("max_hp", "hp"):
        if player.max_hp < 1:
            player.max_hp = 1
        if player.hp > player.max_hp:
            player.hp = player.max_hp
        if player.hp < 0:
            player.hp = 0

    if attr == "shoot_cooldown":
        if player.shoot_cooldown < 0.05:
            player.shoot_cooldown = 0.05


def main():
    current_level = 1
    pygame.init()
    window = pygame.display.set_mode((BASE_W * SCALE, BASE_H * SCALE))
    screen = pygame.Surface((BASE_W, BASE_H))
    pygame.display.set_caption("Tiled TMX + Collision + Jump + Shoot")
    clock = pygame.time.Clock()

    full_heart_img = pygame.image.load("assets/ui/full_heart.png").convert_alpha()
    broken_heart_img = pygame.image.load("assets/ui/broken_heart.png").convert_alpha()

    tmx, solids = load_level("assets/maps/map1.tmx")

    def reset_level(carry_player: Player | None = None):
        level_str = "lvl" + str(current_level)
        px, py = MAP_DICT[level_str]["start"]
        p = Player(px, py)

        if carry_player is None:
            base_hearts = MAP_DICT[level_str]["hearts"]
            p.max_hp = base_hearts
            p.hp = base_hearts
        else:
            p.max_hp = carry_player.max_hp
            p.hp = min(carry_player.hp, p.max_hp)
            p.shoot_cooldown = carry_player.shoot_cooldown

        cx, cy = MAP_DICT[level_str]["chest"]
        c_rect = pygame.Rect(cx, cy, 16, 16)
        c_open = False

        es = []
        for e_name, (ex, ey) in MAP_DICT[level_str]["enemies"]:
            es.append(globals()[e_name](ex, ey))

        enemy_ps = []
        ps = []
        dead = False
        return p, es, enemy_ps, ps, dead, c_rect, c_open

    player, enemies, enemy_projectiles, projectiles, dead, chest_rect, chest_open = reset_level()
    running = True

    while running:
        if dead:
            action = end_menu(window, screen, clock, "You Died.\nPress 'q' to quit or 'r' to restart")
            if action == "restart":
                current_level = 1
                tmx, solids = load_level("assets/maps/map1.tmx")
                player, enemies, enemy_projectiles, projectiles, dead, chest_rect, chest_open = reset_level()
                continue
            pygame.quit()
            sys.exit()

        dt = clock.tick(FPS) / 1000.0

        player.shoot_timer = max(0.0, player.shoot_timer - dt)

        if player.hurt_timer > 0:
            player.hurt_timer = max(0.0, player.hurt_timer - dt)

        if player.jump_buffer > 0:
            player.jump_buffer = max(0.0, player.jump_buffer - dt)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_SPACE, pygame.K_w, pygame.K_UP):
                    player.jump_buffer = JUMP_BUFFER_TIME

                if event.key == pygame.K_ESCAPE:
                    action = pause_menu(window, screen, clock)
                    if action == "resume":
                        continue
                    if action == "restart":
                        current_level = 1
                        tmx, solids = load_level("assets/maps/map1.tmx")
                        player, enemies, enemy_projectiles, projectiles, dead, chest_rect, chest_open = reset_level()
                        break
                    pygame.quit()
                    sys.exit()

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if player.shoot_timer == 0.0:
                    shoot(projectiles, player)
                    player.shoot_timer = player.shoot_cooldown

        keys = pygame.key.get_pressed()
        player.vx = 0.0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            player.vx = -MOVE_SPEED
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            player.vx = MOVE_SPEED

        player.vy += GRAVITY * dt
        player.vy, player.on_ground = move_and_collide(
            player.hitbox, player.vx, player.vy, solids, dt,
            allow_step=player.on_ground
        )

        if (not chest_open) and (
            player.hitbox.colliderect(chest_rect)
            or player.hitbox.right == chest_rect.left
            or player.hitbox.left == chest_rect.right
        ):
            chest_open = True
            level_str = "lvl" + str(current_level)
            for r in MAP_DICT[level_str].get("chest_reward", []):
                apply_reward(player, r)
            open_chest(window, screen, clock, current_level)

        level_str = "lvl" + str(current_level)
        end_x, end_y = MAP_DICT[level_str]["end"]
        end_rect = pygame.Rect(end_x, end_y, 16, 16)

        if (
            player.hitbox.colliderect(end_rect)
            or player.hitbox.right == end_rect.left
            or player.hitbox.left == end_rect.right
        ):
            current_level += 1
            next_level_str = "lvl" + str(current_level)
            if next_level_str not in MAP_DICT:
                pygame.quit()
                sys.exit()

            map_path = MAP_DICT[next_level_str]["map"] + ".tmx"
            tmx, solids = load_level(map_path)
            player, enemies, enemy_projectiles, projectiles, dead, chest_rect, chest_open = reset_level(player)
            continue

        if player.jump_buffer > 0 and player.on_ground:
            player.vy = -JUMP_VEL
            player.on_ground = False
            player.jump_buffer = 0.0

        for e in enemies:
            e.update(dt, player.hitbox, enemy_projectiles)
            e.vy += GRAVITY * dt
            e.vy, e.on_ground = move_and_collide(e.rect, e.vx, e.vy, solids, dt, allow_step=False)

        player.update_animation(dt)

        for e in enemies:
            if player.hurt_timer == 0 and player.hitbox.colliderect(e.rect):
                player.hp -= 1
                player.hurt_timer = INVINCIBILITY_TIME

                if player.hitbox.centerx < e.rect.centerx:
                    player.vx = -250
                else:
                    player.vx = 250

                player.vy = -200

        for p in projectiles:
            p.update(dt)

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

            hit_enemy = False
            for e in enemies:
                if r.colliderect(e.rect):
                    e.hp -= 1
                    hit_enemy = True
                    break
            if hit_enemy:
                continue

            alive.append(p)

        projectiles = alive
        enemies = [e for e in enemies if e.hp > 0]

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

            if r.colliderect(player.hitbox):
                if MODE != 1:
                    player.hp -= 1
                continue

            alive_enemy.append(p)

        enemy_projectiles = alive_enemy
        if player.hp <= 0:
            dead = True

        screen.fill((15, 15, 20))
        draw_tmx(screen, tmx)

        for p in projectiles:
            p.draw(screen)

        screen.blit(player.image, player.draw_pos)

        for p in enemy_projectiles:
            p.draw(screen)

        for e in enemies:
            e.draw(screen)

        for i in range(player.max_hp):
            x = 8 + i * 20
            y = 8
            if i < player.hp:
                screen.blit(full_heart_img, (x, y))
            else:
                screen.blit(broken_heart_img, (x, y))

        scaled = pygame.transform.scale(screen, (BASE_W * SCALE, BASE_H * SCALE))
        window.blit(scaled, (0, 0))
        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()