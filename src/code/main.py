import argparse
import logging
from pathlib import Path
import sys

import pygame

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.classes.Player import Player
from src.code.functions import (
    apply_latest_state,
    build_amrany_levels,
    calc_view,
    compute_aim_position,
    create_connection_or_show_error,
    draw_tmx,
    ensure_frame_surface,
    handle_main_events,
    load_visual_level,
    should_start_lobby_music,
    poll_network_messages,
    present_frame,
    render_lobby_scene,
    render_playing_scene,
    render_waiting_scene,
    reset_non_playing_ui_state,
    send_client_message,
    update_chest_overlay_progress,
)
from src.env_config import CLIENT_SERVER_HOST, CLIENT_SERVER_PORT
from src.settings import BASE_H, BASE_W, FPS, STARTING_LVL


logger = logging.getLogger(__name__)


WINDOW_W = 1920
WINDOW_H = 1080
UI_W = 1280
UI_H = 720


def main(host: str, port: int) -> None:
    """Run the pygame client loop and synchronize state with the server."""
    pygame.init()
    window = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("HellCrepe Multiplayer Client")
    clock = pygame.time.Clock()

    full_heart_img = pygame.image.load(
        str(PROJECT_ROOT / "assets" / "ui" / "full_heart.png")).convert_alpha()
    broken_heart_img = pygame.image.load(
        str(PROJECT_ROOT / "assets" / "ui" / "broken_heart.png")).convert_alpha()

    info_font = pygame.font.SysFont("arial", 18)
    overlay_font = pygame.font.SysFont("arial", 28, bold=True)
    boss_font = pygame.font.SysFont("arial", 12, bold=True)
    boss_name_font = pygame.font.SysFont("arial", 14, bold=True)
    lobby_title_font = pygame.font.SysFont("arial", 44, bold=True)
    lobby_body_font = pygame.font.SysFont("arial", 28)
    lobby_small_font = pygame.font.SysFont("arial", 22)
    lobby_arrow_font = pygame.font.SysFont("arial", 56, bold=True)

    lobby_music_path = PROJECT_ROOT / \
        "assets" / "music" / "main_music.mp3"
    lobby_music_available = lobby_music_path.exists()
    lobby_music_loaded = False
    lobby_music_playing = False

    connection = create_connection_or_show_error(
        host,
        port,
        window,
        overlay_font,
        UI_W,
        UI_H,
        WINDOW_W,
        WINDOW_H,
    )
    if connection is None:
        logger.error(
            "Client shutdown because server connection failed"
        )
        return

    net_state = {"player_id": None, "latest_state": None, "error": None}
    visual_cache: dict[int, tuple] = {}

    current_level = STARTING_LVL
    current_visual = load_visual_level(current_level, visual_cache)
    if current_visual is None:
        current_visual = (None, BASE_W, BASE_H)

    tmx, base_w, base_h = current_visual
    screen = pygame.Surface((base_w, base_h))
    scale, off_x, off_y, scaled_w, scaled_h = calc_view(
        base_w, base_h, WINDOW_W, WINDOW_H)

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
    amrany_server_defeated = False
    running = True

    while running:
        dt = clock.tick(FPS) / 1000.0
        poll_network_messages(connection, net_state)

        (
            running,
            restart_requested,
            lobby_ready,
            lobby_skin_index,
            lobby_username,
            pause_menu_open,
            pause_menu_index,
            win_menu_open,
            win_menu_index,
            win_menu_acknowledged,
            amrany_seen_alive,
            amrany_defeated,
        ) = handle_main_events(
            session_phase,
            running,
            win_menu_open,
            win_menu_index,
            win_menu_options,
            win_menu_acknowledged,
            amrany_seen_alive,
            amrany_defeated,
            pause_menu_open,
            pause_menu_index,
            pause_menu_options,
            lobby_ready,
            lobby_skin_index,
            available_skins,
            lobby_username,
        )

        state = apply_latest_state(
            net_state,
            available_skins,
            lobby_skin_index,
            lobby_owner_id,
            lobby_initialized,
            lobby_username,
            lobby_ready,
            connected_players,
            required_players,
            session_phase,
            current_level,
            visual_cache,
            tmx,
            base_w,
            base_h,
            screen,
            scale,
            off_x,
            off_y,
            scaled_w,
            scaled_h,
            last_chest_event_id,
            chest_overlay_messages,
            chest_overlay_index,
            chest_overlay_wait_release,
            STARTING_LVL,
            WINDOW_W,
            WINDOW_H,
        )

        local_player = state["local_player"]
        world = state["world"]
        players: list[dict] = state["players"]
        player_id = state["player_id"]
        available_skins = state["available_skins"]
        lobby_skin_index = state["lobby_skin_index"]
        lobby_owner_id = state["lobby_owner_id"]
        lobby_initialized = state["lobby_initialized"]
        lobby_username = state["lobby_username"]
        lobby_ready = state["lobby_ready"]
        connected_players = state["connected_players"]
        required_players = state["required_players"]
        session_phase = state["session_phase"]
        current_level = state["current_level"]
        tmx = state["tmx"]
        base_w = state["base_w"]
        base_h = state["base_h"]
        screen = state["screen"]
        scale = state["scale"]
        off_x = state["off_x"]
        off_y = state["off_y"]
        scaled_w = state["scaled_w"]
        scaled_h = state["scaled_h"]
        last_chest_event_id = state["last_chest_event_id"]
        chest_overlay_messages = state["chest_overlay_messages"]
        chest_overlay_index = state["chest_overlay_index"]
        chest_overlay_wait_release = state["chest_overlay_wait_release"]
        spectating_player_id = state["spectating_player_id"]
        amrany_server_defeated = state["amrany_server_defeated"]

        (
            lobby_music_available,
            lobby_music_loaded,
            lobby_music_playing,
        ) = should_start_lobby_music(
            session_phase,
            local_player,
            connected_players,
            required_players,
            net_state,
            lobby_music_available,
            lobby_music_loaded,
            lobby_music_playing,
            lobby_music_path,
        )

        (
            chest_overlay_messages,
            chest_overlay_index,
            chest_overlay_wait_release,
            pause_menu_open,
            win_menu_open,
            win_menu_acknowledged,
            amrany_seen_alive,
            amrany_defeated,
        ) = reset_non_playing_ui_state(
            session_phase,
            chest_overlay_messages,
            chest_overlay_index,
            chest_overlay_wait_release,
            pause_menu_open,
            win_menu_open,
            win_menu_acknowledged,
            amrany_seen_alive,
            amrany_defeated,
        )

        screen, scale, off_x, off_y, scaled_w, scaled_h = ensure_frame_surface(
            screen,
            session_phase,
            base_w,
            base_h,
            UI_W,
            UI_H,
            WINDOW_W,
            WINDOW_H,
            scale,
            off_x,
            off_y,
            scaled_w,
            scaled_h,
        )

        keys = pygame.key.get_pressed()
        mouse_buttons = pygame.mouse.get_pressed()
        mx, my = pygame.mouse.get_pos()

        (
            chest_overlay_index,
            chest_overlay_wait_release,
            chest_overlay_active,
        ) = update_chest_overlay_progress(
            chest_overlay_messages,
            chest_overlay_index,
            chest_overlay_wait_release,
            keys,
        )

        aim_x, aim_y = compute_aim_position(
            mx, my, off_x, off_y, scale, screen)

        send_client_message(
            connection,
            net_state,
            session_phase,
            local_player,
            player_id,
            lobby_username,
            lobby_skin_index,
            available_skins,
            lobby_ready,
            keys,
            mouse_buttons,
            chest_overlay_active,
            pause_menu_open,
            win_menu_open,
            aim_x,
            aim_y,
            restart_requested,
        )

        screen.fill((15, 15, 20))
        if tmx is not None:
            draw_tmx(screen, tmx)

        if local_player is not None and session_phase == "playing":
            (
                enemy_sprites,
                player_sprites,
                win_menu_open,
                pause_menu_open,
                win_menu_index,
                amrany_seen_alive,
                amrany_defeated,
            ) = render_playing_scene(
                screen,
                dt,
                players,
                player_id,
                world,
                current_level,
                enemy_sprites,
                player_sprites,
                info_font,
                overlay_font,
                boss_font,
                boss_name_font,
                full_heart_img,
                broken_heart_img,
                local_player,
                spectating_player_id,
                pause_menu_open,
                pause_menu_index,
                pause_menu_options,
                win_menu_open,
                win_menu_index,
                win_menu_options,
                win_menu_acknowledged,
                chest_overlay_active,
                chest_overlay_messages,
                chest_overlay_index,
                amrany_levels,
                amrany_server_defeated,
                amrany_seen_alive,
                amrany_defeated,
            )
        elif local_player is not None and session_phase == "lobby":
            render_lobby_scene(
                screen,
                players,
                player_id,
                lobby_username,
                lobby_skin_index,
                available_skins,
                lobby_ready,
                preview_cache,
                lobby_title_font,
                lobby_body_font,
                lobby_small_font,
                lobby_arrow_font,
            )
        else:
            render_waiting_scene(
                screen,
                net_state,
                local_player,
                session_phase,
                connected_players,
                required_players,
                overlay_font,
            )

        present_frame(window, screen, scaled_w, scaled_h, off_x, off_y)

    logger.info("Closing client connection and pygame")
    connection.close()
    pygame.quit()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="HellCrepe multiplayer client")
    parser.add_argument("--host", default=CLIENT_SERVER_HOST, help="Server host/IP")
    parser.add_argument("--port", type=int, default=CLIENT_SERVER_PORT, help="Server port")
    args = parser.parse_args()
    main(args.host, args.port)
