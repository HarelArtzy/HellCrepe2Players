import pygame


def calc_view(base_w, base_h, target_w=1920, target_h=1080):
    s = min(target_w / base_w, target_h / base_h)
    scaled_w = max(1, int(base_w * s))
    scaled_h = max(1, int(base_h * s))
    off_x = (target_w - scaled_w) // 2
    off_y = (target_h - scaled_h) // 2
    return s, off_x, off_y, scaled_w, scaled_h


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


def load_level(path):
    from pytmx.util_pygame import load_pygame

    tmx = load_pygame(path)
    solids = build_collision_rects(tmx, "Collision")
    return tmx, solids
