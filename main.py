# /// script
# dependencies = [
#   "pygame-ce",
#   "pytmx",
# ]
# ///

import asyncio
import pygame

from settings import *
from functions import (
    load_level, move_and_collide, shoot, draw_tmx,
    pause_menu, end_menu, open_chest,
    apply_reward, make_enemies, swap_map_keep_state
)
from classes import Player


async def main():
    current_level = 1
    visual_advanced = False
    locked = True
    pygame.init()
    window = pygame.display.set_mode((BASE_W * SCALE, BASE_H * SCALE))
    screen = pygame.Surface((BASE_W, BASE_H))
    pygame.display.set_caption("Tiled TMX + Collision + Jump + Shoot")
    clock = pygame.time.Clock()

    full_heart_img = pygame.image.load("assets/ui/full_heart.png").convert_alpha()
    broken_heart_img = pygame.image.load("assets/ui/broken_heart.png").convert_alpha()

    level_str = "lvl" + str(current_level)
    tmx, solids = load_level(MAP_DICT[level_str]["map"] + ".tmx")
    end_x, end_y = MAP_DICT[level_str]["end"]
    end_rect = pygame.Rect(end_x, end_y, 16, 16)

    def reset_level(carry_player: Player | None = None):
        nonlocal visual_advanced, locked, end_rect, tmx, solids
        visual_advanced = False
        locked = True

        _level_str = "lvl" + str(current_level)
        px, py = MAP_DICT[_level_str]["start"]
        _p = Player(px, py)

        if carry_player is None:
            _p.max_hp = BASE_HEARTS
            _p.hp = BASE_HEARTS
        else:
            _p.max_hp = carry_player.max_hp
            _p.hp = min(carry_player.hp, _p.max_hp)
            _p.shoot_cooldown = carry_player.shoot_cooldown
            _p.move_speed = carry_player.move_speed

        tmx, solids = load_level(MAP_DICT[_level_str]["map"] + ".tmx")
        ex, ey = MAP_DICT[_level_str]["end"]
        end_rect = pygame.Rect(ex, ey, 16, 16)

        cx, cy = MAP_DICT[_level_str]["chest"]
        c_rect = pygame.Rect(cx, cy, 16, 16)
        c_open = False

        es = make_enemies(_level_str)
        enemy_ps = []
        ps = []
        dead_flag = False
        return _p, es, enemy_ps, ps, dead_flag, c_rect, c_open

    player, enemies, enemy_projectiles, projectiles, dead, chest_rect, chest_open = reset_level()
    running = True

    while running:
        if dead:
            action = await end_menu(window, screen, clock, "You Died.\nPress 'q' to quit or 'r' to restart")
            if action == "restart":
                current_level = 1
                player, enemies, enemy_projectiles, projectiles, dead, chest_rect, chest_open = reset_level()
                continue
            pygame.quit()
            return

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
                    action = await pause_menu(window, screen, clock)
                    if action == "resume":
                        continue
                    if action == "restart":
                        current_level = 1
                        player, enemies, enemy_projectiles, projectiles, dead, chest_rect, chest_open = reset_level()
                        break
                    pygame.quit()
                    return

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if player.shoot_timer == 0.0:
                    shoot(projectiles, player)
                    player.shoot_timer = player.shoot_cooldown

        keys = pygame.key.get_pressed()
        player.vx = 0.0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            player.vx = -player.move_speed
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            player.vx = player.move_speed

        player.vy += GRAVITY * dt
        player.vy, player.on_ground = move_and_collide(
            player.hitbox, player.vx, player.vy, solids, dt,
            allow_step=player.on_ground
        )

        level_str = "lvl" + str(current_level)

        if (not chest_open) and player.hitbox.colliderect(chest_rect):
            chest_open = True
            for r in MAP_DICT[level_str].get("chest_reward", []):
                apply_reward(player, r)
            result = await open_chest(window, screen, clock, current_level)
            if result == "quit":
                pygame.quit()
                return

        if (not visual_advanced) and len(enemies) == 0 and MAP_DICT[level_str].get("cleared", False):
            tmx, solids, end_rect, chest_rect, chest_open, current_level = swap_map_keep_state(current_level, current_level + 1)
            visual_advanced = True
            locked = False
            continue

        if player.hitbox.colliderect(end_rect) and ((not MAP_DICT[level_str].get("cleared", False)) or (MAP_DICT[level_str].get("cleared", False) and (not locked))):
            current_level += 1
            next_level_str = "lvl" + str(current_level)
            if next_level_str not in MAP_DICT:
                pygame.quit()
                return
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

        await asyncio.sleep(0)

    pygame.quit()
    return


if __name__ == "__main__":
    asyncio.run(main())