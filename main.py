import argparse
from pathlib import Path

import pygame

from classes import Player
from functions import (
    build_amrany_levels,
    calc_view,
    connect_with_feedback,
    draw_tmx,
    level_key,
    load_player_preview,
    load_visual_level,
    make_enemy_sprite,
    normalize_username,
    poll_network_messages,
    render_center_text,
    show_connection_error_screen,
)
from settings import BASE_H, BASE_W, FPS, MAP_DICT, STARTING_LVL


WINDOW_W = 1920
WINDOW_H = 1080
UI_W = 1280
UI_H = 720


def main(host: str, port: int) -> None:
    """Run the full client game loop: input, networking, state sync, and rendering."""
    pygame.init()
    window = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("HellCrepe Multiplayer Client")
    clock = pygame.time.Clock()

    full_heart_img = pygame.image.load("assets/ui/full_heart.png").convert_alpha()
    broken_heart_img = pygame.image.load("assets/ui/broken_heart.png").convert_alpha()

    info_font = pygame.font.SysFont("arial", 18)
    overlay_font = pygame.font.SysFont("arial", 28, bold=True)
    boss_font = pygame.font.SysFont("arial", 12, bold=True)
    boss_name_font = pygame.font.SysFont("arial", 14, bold=True)
    lobby_title_font = pygame.font.SysFont("arial", 44, bold=True)
    lobby_body_font = pygame.font.SysFont("arial", 28)
    lobby_small_font = pygame.font.SysFont("arial", 22)
    lobby_arrow_font = pygame.font.SysFont("arial", 56, bold=True)

    lobby_music_path = Path(__file__).resolve().parent / "assets" / "music" / "main_music.mp3"
    lobby_music_available = lobby_music_path.exists()
    lobby_music_loaded = False
    lobby_music_playing = False

    connection, connect_error = connect_with_feedback(
        window,
        overlay_font,
        info_font,
        host,
        port,
        timeout_s=8.0,
    )
    if connection is None:
        show_connection_error_screen(
            window,
            overlay_font,
            info_font,
            host,
            port,
            connect_error or "Unknown connection error.",
        )
        pygame.quit()
        return

    net_state = {"player_id": None, "latest_state": None, "error": None, "session_id": None}

    visual_cache: dict[int, tuple] = {}
    current_level = STARTING_LVL
    current_visual = load_visual_level(current_level, visual_cache)
    if current_visual is None:
        current_visual = (None, BASE_W, BASE_H)

    tmx, base_w, base_h = current_visual
    screen = pygame.Surface((base_w, base_h))
    scale, off_x, off_y, scaled_w, scaled_h = calc_view(base_w, base_h, WINDOW_W, WINDOW_H)

    player_sprites: dict[int, Player] = {}
    enemy_sprites: dict[int, object] = {}
    preview_cache: dict[tuple[str, int], pygame.Surface] = {}
    last_chest_event_id = 0
    chest_overlay_messages: list[str] = []
    chest_overlay_index = 0
    chest_overlay_wait_release = True
    session_phase = "waiting"
    connected_players = 0
    required_players = 2

    available_skins = ["default"]
    lobby_username = ""
    lobby_skin_index = 0
    lobby_ready = False
    lobby_initialized = False
    lobby_owner_id = None
    pause_menu_open = False
    pause_menu_index = 0
    pause_menu_options = ["Resume", "Restart Session", "Quit"]
    win_menu_open = False
    win_menu_index = 0
    win_menu_acknowledged = False
    win_menu_options = ["Restart", "Quit"]
    amrany_levels = build_amrany_levels()
    amrany_seen_alive = False
    amrany_defeated = False
    running = True

    while running:
        dt = clock.tick(FPS) / 1000.0
        restart_requested = False

        poll_network_messages(connection, net_state)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if session_phase == "playing":
                    if win_menu_open:
                        if event.key in (pygame.K_UP, pygame.K_w):
                            win_menu_index = (win_menu_index - 1) % len(win_menu_options)
                        elif event.key in (pygame.K_DOWN, pygame.K_s):
                            win_menu_index = (win_menu_index + 1) % len(win_menu_options)
                        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                            selected = win_menu_options[win_menu_index]
                            if selected == "Restart":
                                restart_requested = True
                                win_menu_open = False
                                win_menu_acknowledged = True
                                amrany_seen_alive = False
                                amrany_defeated = False
                            elif selected == "Quit":
                                running = False
                        continue
                    if pause_menu_open:
                        if event.key in (pygame.K_UP, pygame.K_w):
                            pause_menu_index = (pause_menu_index - 1) % len(pause_menu_options)
                        elif event.key in (pygame.K_DOWN, pygame.K_s):
                            pause_menu_index = (pause_menu_index + 1) % len(pause_menu_options)
                        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                            selected = pause_menu_options[pause_menu_index]
                            if selected == "Resume":
                                pause_menu_open = False
                            elif selected == "Restart Session":
                                restart_requested = True
                                pause_menu_open = False
                            elif selected == "Quit":
                                running = False
                        elif event.key == pygame.K_ESCAPE:
                            pause_menu_open = False
                        continue
                    if event.key == pygame.K_ESCAPE:
                        pause_menu_open = True
                        pause_menu_index = 0
                        continue

                if session_phase == "lobby":
                    if event.key == pygame.K_RETURN:
                        lobby_ready = not lobby_ready
                    elif not lobby_ready:
                        if event.key == pygame.K_LEFT:
                            lobby_skin_index = (lobby_skin_index - 1) % max(1, len(available_skins))
                        elif event.key == pygame.K_RIGHT:
                            lobby_skin_index = (lobby_skin_index + 1) % max(1, len(available_skins))
                        elif event.key == pygame.K_BACKSPACE:
                            lobby_username = lobby_username[:-1]
                        elif event.unicode and event.unicode.isprintable() and len(lobby_username) < 20:
                            lobby_username += event.unicode

        latest_state = net_state.get("latest_state")
        local_player = None
        world = {}
        players: list[dict] = []
        player_id = net_state.get("player_id")
        session: dict = {}
        spectating_player_id = None

        if latest_state is not None:
            players = latest_state.get("players", [])
            session = latest_state.get("session", {})
            server_session_id = str(session.get("id", "")).strip()
            if server_session_id:
                net_state["session_id"] = server_session_id
            spectating_player_id = latest_state.get("spectating_player_id")
            if player_id is None:
                player_id = latest_state.get("you")
                net_state["player_id"] = player_id
            local_player = next((p for p in players if p.get("id") == player_id), None)
            connected_players = int(session.get("connected_players", len(players)))
            required_players = int(session.get("required_players", 2))

            session_phase = str(session.get("phase", "waiting"))
            maybe_skins = session.get("available_skins", available_skins)
            if isinstance(maybe_skins, list):
                parsed_skins = [str(s) for s in maybe_skins if str(s).strip()]
                if parsed_skins:
                    available_skins = parsed_skins
                    lobby_skin_index %= len(available_skins)

            if local_player is not None:
                if lobby_owner_id != player_id:
                    lobby_owner_id = player_id
                    lobby_initialized = False

                server_username = str(local_player.get("username", f"Player {player_id}"))
                server_skin = str(local_player.get("skin", available_skins[0]))
                server_ready = bool(local_player.get("ready", False))

                if (not lobby_initialized) or session_phase == "waiting":
                    lobby_username = server_username
                    lobby_ready = server_ready
                    if server_skin in available_skins:
                        lobby_skin_index = available_skins.index(server_skin)
                    else:
                        lobby_skin_index = 0
                    lobby_initialized = True
                elif session_phase != "lobby":
                    lobby_ready = server_ready

                world = latest_state.get("world", {})
                render_level = int(world.get("current_level", local_player.get("current_level", STARTING_LVL)))
                if render_level != current_level:
                    maybe_visual = load_visual_level(render_level, visual_cache)
                    if maybe_visual is not None:
                        tmx, base_w, base_h = maybe_visual
                        screen = pygame.Surface((base_w, base_h))
                        scale, off_x, off_y, scaled_w, scaled_h = calc_view(base_w, base_h, WINDOW_W, WINDOW_H)
                        current_level = render_level

                chest_event_id = int(local_player.get("chest_event_id", 0))
                if chest_event_id > last_chest_event_id:
                    chest_event_level = int(local_player.get("chest_event_level", local_player.get("current_level", STARTING_LVL)))
                    cfg = MAP_DICT.get(level_key(chest_event_level), {})
                    msgs = [str(msg) for msg in cfg.get("chest_msg", []) if str(msg).strip()]
                    if msgs:
                        chest_overlay_messages = msgs
                        chest_overlay_index = 0
                        chest_overlay_wait_release = True
                    last_chest_event_id = chest_event_id

        should_start_lobby_music = (
            session_phase == "lobby"
            and local_player is not None
            and connected_players >= required_players
            and net_state.get("error") is None
        )
        if should_start_lobby_music and lobby_music_available and not lobby_music_playing:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                if not lobby_music_loaded:
                    pygame.mixer.music.load(str(lobby_music_path))
                    pygame.mixer.music.set_volume(0.45)
                    lobby_music_loaded = True
                pygame.mixer.music.play(-1)
                lobby_music_playing = True
            except Exception:
                lobby_music_available = False
                lobby_music_playing = False

        if session_phase != "playing":
            chest_overlay_messages = []
            chest_overlay_index = 0
            chest_overlay_wait_release = True
            pause_menu_open = False
            win_menu_open = False
            win_menu_acknowledged = False
            amrany_seen_alive = False
            amrany_defeated = False

        target_w, target_h = (base_w, base_h) if session_phase == "playing" else (UI_W, UI_H)
        if screen.get_width() != target_w or screen.get_height() != target_h:
            screen = pygame.Surface((target_w, target_h))
            scale, off_x, off_y, scaled_w, scaled_h = calc_view(target_w, target_h, WINDOW_W, WINDOW_H)

        keys = pygame.key.get_pressed()
        mouse_buttons = pygame.mouse.get_pressed()
        mx, my = pygame.mouse.get_pos()

        chest_overlay_active = chest_overlay_index < len(chest_overlay_messages)
        if chest_overlay_active:
            space_down = bool(keys[pygame.K_SPACE])
            if chest_overlay_wait_release:
                if not space_down:
                    chest_overlay_wait_release = False
            elif space_down:
                chest_overlay_index += 1
                chest_overlay_wait_release = True
                chest_overlay_active = chest_overlay_index < len(chest_overlay_messages)

        aim_x = int((mx - off_x) / scale) if scale else 0
        aim_y = int((my - off_y) / scale) if scale else 0
        if screen.get_width() > 0:
            aim_x = max(0, min(screen.get_width() - 1, aim_x))
        if screen.get_height() > 0:
            aim_y = max(0, min(screen.get_height() - 1, aim_y))

        if net_state.get("error") is None:
            try:
                if session_phase == "lobby" and local_player is not None:
                    fallback_name = f"Player {player_id}" if player_id is not None else "Player"
                    username_to_send = normalize_username(lobby_username, fallback_name)
                    chosen_skin = available_skins[lobby_skin_index] if available_skins else "default"
                    connection.queue_json(
                        {
                            "type": "lobby",
                            "username": username_to_send,
                            "skin": chosen_skin,
                            "ready": bool(lobby_ready),
                        }
                    )
                else:
                    input_locked = (session_phase != "playing") or chest_overlay_active or pause_menu_open or win_menu_open
                    input_payload = {
                        "type": "input",
                        "left": bool(keys[pygame.K_a] or keys[pygame.K_LEFT]) and (not input_locked),
                        "right": bool(keys[pygame.K_d] or keys[pygame.K_RIGHT]) and (not input_locked),
                        "jump": bool(keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP]) and (not input_locked),
                        "shoot": bool(mouse_buttons[0]) and (not input_locked),
                        "aim_x": aim_x,
                        "aim_y": aim_y,
                        "restart": restart_requested,
                    }
                    connection.queue_json(input_payload)
                connection.flush()
            except ConnectionError:
                net_state["error"] = "Disconnected from server."

        screen.fill((15, 15, 20))
        if tmx is not None:
            draw_tmx(screen, tmx)
        session_id_display = str(net_state.get("session_id") or "").strip()

        if local_player is not None and session_phase == "playing":
            for p_data in players:
                if int(p_data.get("current_level", -1)) != current_level:
                    continue
                color = (255, 220, 120) if p_data.get("id") == player_id else (120, 220, 255)
                for projectile in p_data.get("projectiles", []):
                    pygame.draw.circle(
                        screen,
                        color,
                        (int(projectile.get("x", 0)), int(projectile.get("y", 0))),
                        int(projectile.get("radius", 3)),
                    )

            for projectile in world.get("enemy_projectiles", []):
                pygame.draw.circle(
                    screen,
                    (255, 100, 100),
                    (int(projectile.get("x", 0)), int(projectile.get("y", 0))),
                    int(projectile.get("radius", 3)),
                )

            boss_enemy = None
            visible_enemy_ids: set[int] = set()
            for enemy in world.get("enemies", []):
                enemy_id = int(enemy.get("id", -1))
                enemy_type = str(enemy.get("type", ""))
                ex = int(enemy.get("x", 0))
                ey = int(enemy.get("y", 0))
                ew = int(enemy.get("w", 32))
                eh = int(enemy.get("h", 32))
                evx = float(enemy.get("vx", 0.0))

                sprite = enemy_sprites.get(enemy_id)
                if sprite is None or sprite.__class__.__name__ != enemy_type:
                    sprite = make_enemy_sprite(enemy_type, ex, ey)
                    if sprite is None:
                        fallback_rect = pygame.Rect(ex, ey, ew, eh)
                        pygame.draw.rect(screen, (220, 80, 80), fallback_rect)
                        continue
                    enemy_sprites[enemy_id] = sprite

                sprite.rect.x = ex
                sprite.rect.y = ey
                sprite.vx = evx
                if hasattr(sprite, "update_animation"):
                    sprite.update_animation(dt)
                sprite.draw(screen)
                visible_enemy_ids.add(enemy_id)

                if enemy_type == "Amrany":
                    boss_enemy = enemy

            stale_enemy_ids = [enemy_id for enemy_id in enemy_sprites if enemy_id not in visible_enemy_ids]
            for enemy_id in stale_enemy_ids:
                enemy_sprites.pop(enemy_id, None)

            if boss_enemy is not None:
                bar_w = 220
                bar_h = 10
                x = (base_w - bar_w) // 2
                y = 6

                ratio = 0.0
                max_hp = max(1, int(boss_enemy.get("max_hp", 1)))
                hp = int(boss_enemy.get("hp", 0))
                ratio = max(0.0, min(1.0, hp / max_hp))

                pygame.draw.rect(screen, (0, 0, 0), (x - 2, y - 2, bar_w + 4, bar_h + 4))
                pygame.draw.rect(screen, (60, 60, 60), (x, y, bar_w, bar_h))
                pygame.draw.rect(screen, (220, 60, 60), (x, y, int(bar_w * ratio), bar_h))

                hp_text = boss_font.render(f"{hp}/{max_hp}", True, (255, 255, 255))
                screen.blit(hp_text, hp_text.get_rect(center=(x + bar_w // 2, y + bar_h // 2)))
                boss_name = boss_name_font.render("Amrany - Devourer Of Crepes", True, (235, 235, 235))
                screen.blit(boss_name, boss_name.get_rect(center=(x + bar_w // 2, y + bar_h + 12)))

            is_amrany_level = current_level in amrany_levels
            if is_amrany_level:
                if boss_enemy is not None:
                    amrany_seen_alive = True
                    amrany_defeated = False
                elif amrany_seen_alive and (not amrany_defeated):
                    amrany_defeated = True
                    if not win_menu_acknowledged:
                        win_menu_open = True
                        win_menu_index = 0
                        pause_menu_open = False
            elif not win_menu_open:
                amrany_seen_alive = False
                amrany_defeated = False

            for p_data in players:
                if int(p_data.get("current_level", -1)) != current_level:
                    continue
                pid = int(p_data.get("id", -1))
                px = int(p_data.get("x", 0))
                py = int(p_data.get("y", 0))
                skin_name = str(p_data.get("skin", "default"))

                sprite = player_sprites.get(pid)
                if sprite is None or getattr(sprite, "skin_name", "default") != skin_name:
                    sprite = Player(px, py, skin_name=skin_name)
                    player_sprites[pid] = sprite

                sprite.hitbox.x = px
                sprite.hitbox.y = py
                sprite.vx = float(p_data.get("vx", 0.0))
                sprite.update_animation(dt)
                screen.blit(sprite.image, sprite.draw_pos)

                if pid != player_id:
                    pname = normalize_username(str(p_data.get("username", "")), f"P{pid}")
                    label = info_font.render(pname, True, (220, 235, 255))
                    screen.blit(label, (sprite.hitbox.x - 2, sprite.hitbox.y - 15))

            hp = max(0, int(local_player.get("hp", 0)))
            max_hp = max(1, int(local_player.get("max_hp", 1)))
            for i in range(max_hp):
                hx = 8 + i * 20
                hy = 8
                if i < hp:
                    screen.blit(full_heart_img, (hx, hy))
                else:
                    screen.blit(broken_heart_img, (hx, hy))

            other_lines: list[str] = []
            for p_data in players:
                pid = int(p_data.get("id", -1))
                if pid == player_id:
                    continue
                pname = normalize_username(str(p_data.get("username", "")), f"P{pid}")
                other_lines.append(
                    f"{pname} | L{int(p_data.get('current_level', 0))} | HP {int(p_data.get('hp', 0))}/{int(p_data.get('max_hp', 0))}"
                )
            for idx, line in enumerate(other_lines):
                text = info_font.render(line, True, (220, 220, 220))
                screen.blit(text, (base_w - text.get_width() - 8, 8 + idx * 16))

            if local_player.get("dead", False):
                if local_player.get("won", False):
                    if not win_menu_acknowledged:
                        win_menu_open = True
                else:
                    spectating_name = "teammate"
                    if spectating_player_id is not None:
                        target = next((p for p in players if int(p.get("id", -1)) == int(spectating_player_id)), None)
                        if target is not None:
                            spectating_name = normalize_username(str(target.get("username", "")), f"P{spectating_player_id}")
                    msg = f"You Died.\nSpectating {spectating_name}.\nWaiting for other player to die."
                    render_center_text(screen, overlay_font, msg, (255, 255, 255))

            if pause_menu_open:
                shade = pygame.Surface((base_w, base_h), pygame.SRCALPHA)
                shade.fill((0, 0, 0, 170))
                screen.blit(shade, (0, 0))

                menu_margin = max(8, min(24, min(base_w, base_h) // 12))
                menu_w = min(420, max(240, base_w - (menu_margin * 2)))
                menu_h = min(220, max(130, base_h - (menu_margin * 2)))
                menu_x = (base_w - menu_w) // 2
                menu_y = (base_h - menu_h) // 2
                panel = pygame.Rect(menu_x, menu_y, menu_w, menu_h)
                radius = max(8, min(12, menu_h // 16))
                pygame.draw.rect(screen, (25, 25, 35), panel, border_radius=radius)
                pygame.draw.rect(screen, (100, 100, 140), panel, 2, border_radius=radius)

                title = overlay_font.render("Paused", True, (240, 240, 250))
                title_center_y = panel.y + max(16, menu_h // 8) + (title.get_height() // 2)
                screen.blit(title, title.get_rect(center=(base_w // 2, title_center_y)))

                option_h = info_font.get_height()
                options_count = max(1, len(pause_menu_options))
                options_top = title_center_y + (title.get_height() // 2) + max(10, menu_h // 12) + (option_h // 2)
                options_bottom = panel.bottom - max(16, menu_h // 9) - (option_h // 2)
                if options_count == 1:
                    option_y_positions = [((options_top + options_bottom) // 2)]
                else:
                    span = max(0, options_bottom - options_top)
                    step = span / (options_count - 1)
                    option_y_positions = [int(options_top + (idx * step)) for idx in range(options_count)]

                for idx, option in enumerate(pause_menu_options):
                    color = (255, 220, 140) if idx == pause_menu_index else (220, 220, 230)
                    text = info_font.render(option, True, color)
                    option_y = option_y_positions[idx] if idx < len(option_y_positions) else panel.centery
                    screen.blit(text, text.get_rect(center=(base_w // 2, option_y)))

            if win_menu_open:
                shade = pygame.Surface((base_w, base_h), pygame.SRCALPHA)
                shade.fill((0, 0, 0, 170))
                screen.blit(shade, (0, 0))

                menu_margin = max(8, min(24, min(base_w, base_h) // 12))
                menu_w = min(420, max(240, base_w - (menu_margin * 2)))
                menu_h = min(220, max(130, base_h - (menu_margin * 2)))
                menu_x = (base_w - menu_w) // 2
                menu_y = (base_h - menu_h) // 2
                panel = pygame.Rect(menu_x, menu_y, menu_w, menu_h)
                radius = max(8, min(12, menu_h // 16))
                pygame.draw.rect(screen, (25, 25, 35), panel, border_radius=radius)
                pygame.draw.rect(screen, (100, 100, 140), panel, 2, border_radius=radius)

                title = overlay_font.render("You Beat Amrany!", True, (240, 240, 250))
                title_center_y = panel.y + max(16, menu_h // 8) + (title.get_height() // 2)
                screen.blit(title, title.get_rect(center=(base_w // 2, title_center_y)))

                option_h = info_font.get_height()
                options_count = max(1, len(win_menu_options))
                options_top = title_center_y + (title.get_height() // 2) + max(10, menu_h // 12) + (option_h // 2)
                options_bottom = panel.bottom - max(16, menu_h // 9) - (option_h // 2)
                if options_count == 1:
                    option_y_positions = [((options_top + options_bottom) // 2)]
                else:
                    span = max(0, options_bottom - options_top)
                    step = span / (options_count - 1)
                    option_y_positions = [int(options_top + (idx * step)) for idx in range(options_count)]

                for idx, option in enumerate(win_menu_options):
                    color = (255, 220, 140) if idx == win_menu_index else (220, 220, 230)
                    text = info_font.render(option, True, color)
                    option_y = option_y_positions[idx] if idx < len(option_y_positions) else panel.centery
                    screen.blit(text, text.get_rect(center=(base_w // 2, option_y)))

            if chest_overlay_active:
                shade = pygame.Surface((base_w, base_h), pygame.SRCALPHA)
                shade.fill((0, 0, 0, 155))
                screen.blit(shade, (0, 0))
                render_center_text(screen, overlay_font, chest_overlay_messages[chest_overlay_index], (245, 245, 245))
        elif local_player is not None and session_phase == "lobby":
            screen.fill((12, 12, 18))
            sw, sh = screen.get_width(), screen.get_height()

            fallback_name = f"Player {player_id}" if player_id is not None else "Player"
            your_name = normalize_username(lobby_username, fallback_name)
            selected_skin = available_skins[lobby_skin_index] if available_skins else "default"

            card_w = min(sw - 120, 900)
            card_h = min(sh - 100, 560)
            card = pygame.Rect((sw - card_w) // 2, (sh - card_h) // 2, card_w, card_h)
            pygame.draw.rect(screen, (20, 20, 30), card, border_radius=14)
            pygame.draw.rect(screen, (90, 90, 125), card, 2, border_radius=14)

            other_player = next((p for p in players if p.get("id") != player_id), None)
            if other_player is None:
                top_line = "Waiting for other player..."
                top_color = (220, 220, 220)
            else:
                other_name = normalize_username(str(other_player.get("username", "")), f"P{other_player.get('id', '?')}")
                other_ready = bool(other_player.get("ready", False))
                top_line = f"{other_name} is {'READY' if other_ready else 'NOT READY'}"
                top_color = (130, 240, 160) if other_ready else (240, 170, 130)

            top_surface = lobby_title_font.render(top_line, True, top_color)
            screen.blit(top_surface, ((sw - top_surface.get_width()) // 2, card.y + 24))

            username_label = lobby_small_font.render("Username", True, (230, 230, 230))
            username_box = pygame.Rect(card.x + 110, card.y + 100, card.w - 220, 52)
            pygame.draw.rect(screen, (30, 30, 42), username_box, border_radius=6)
            pygame.draw.rect(screen, (160, 160, 190), username_box, 2, border_radius=6)
            username_text = lobby_body_font.render(your_name, True, (250, 250, 250))
            screen.blit(username_label, (username_box.x, username_box.y - 20))
            screen.blit(username_text, (username_box.x + 12, username_box.y + 12))

            preview = load_player_preview(selected_skin, preview_cache, preview_size=144)
            preview_rect = preview.get_rect(center=(sw // 2, card.y + 285))
            screen.blit(preview, preview_rect)

            left_arrow = lobby_arrow_font.render("<", True, (230, 230, 230))
            right_arrow = lobby_arrow_font.render(">", True, (230, 230, 230))
            screen.blit(left_arrow, left_arrow.get_rect(center=(preview_rect.left - 48, preview_rect.centery)))
            screen.blit(right_arrow, right_arrow.get_rect(center=(preview_rect.right + 48, preview_rect.centery)))

            skin_text = lobby_body_font.render(f"Skin: {selected_skin}", True, (220, 220, 230))
            screen.blit(skin_text, skin_text.get_rect(center=(sw // 2, preview_rect.bottom + 32)))

            ready_state = "READY" if lobby_ready else "NOT READY"
            ready_color = (120, 240, 140) if lobby_ready else (255, 205, 120)
            ready_text = lobby_body_font.render(f"You are {ready_state}", True, ready_color)
            screen.blit(ready_text, ready_text.get_rect(center=(sw // 2, card.bottom - 64)))

            controls_text = lobby_small_font.render("Type username  |  Left/Right: skin  |  Enter: ready", True, (190, 190, 205))
            screen.blit(controls_text, controls_text.get_rect(center=(sw // 2, card.bottom - 28)))
            if session_id_display:
                sid_text = lobby_small_font.render(f"Session ID: {session_id_display}", True, (180, 180, 205))
                screen.blit(sid_text, (card.x + 22, card.bottom - 36))
        else:
            screen.fill((0, 0, 0))
            wait_msg = "Waiting for server state..."
            if net_state.get("error"):
                wait_msg = net_state["error"]
            elif local_player is not None and session_phase == "waiting":
                wait_msg = f"Waiting for Player 2 to join... ({connected_players}/{required_players})"
            if session_id_display:
                wait_msg += f"\nSession ID: {session_id_display}"
            render_center_text(screen, overlay_font, wait_msg, (235, 235, 235))

        window.fill((0, 0, 0))
        scaled = pygame.transform.scale(screen, (scaled_w, scaled_h))
        window.blit(scaled, (off_x, off_y))
        pygame.display.flip()
    connection.close()
    pygame.quit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HellCrepe multiplayer client")
    parser.add_argument("--host", default="127.0.0.1", help="Server host/IP")
    parser.add_argument("--port", type=int, default=9000, help="Server port")
    args = parser.parse_args()
    main(args.host, args.port)

