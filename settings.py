# settings.py
BASE_W, BASE_H = 53 * 16, 20 * 16
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
BASE_HEARTS = 3

MODE = 0
STARTING_LVL = 2

MAP_DICT = {
    "lvl1": {
        "window": (50 * 16, 10 * 16),
        "map": "assets/maps/map1",
        "start": (60, 20),
        "end": (750, 70),
        "chest": (646, 45),
        "enemies": [("Pancake", (400, 100))],
        "chest_msg": ["Chest:\n Increase fire rate by 25%!\n Press Space to continue"],
        "chest_reward": [("shoot_cooldown", "mul", 0.75)],
    },
    "lvl2": {
        "window": (53 * 16, 20 * 16),
        "map": "assets/maps/map3",
        "start": (60, 20),
        "end": (752, 128),
        "chest": (816, 64),
        "enemies": [("Pancake", (400, 100)), ("Pancake", (775, 64))],
        "chest_msg": [
            "Chest:\n Movement speed increased by 25%"
        ],
        "chest_reward": [("move_speed", "mul", 1.25)],
    },
    "lvl3": {
        "window": (53 * 16, 20 * 16),
        "map": "assets/maps/map3.1",
        "start": (60, 17 * 16),
        "end": (752, 128),
        "chest": (816, 64),
        "enemies": [("Waffle", (400, 272)), ("Waffle", (300, 272)), ("Waffle", (575, 220))],
        "chest_msg": [
            "Chest:\n Movement speed increased by 25%"
        ],
        "chest_reward": [("move_speed", "mul", 1.25)],
        "cleared": 1
    },
    "lvl4": {
        "window": (53 * 16, 20 * 16),
        "map": "assets/maps/map3.2",
        "start": (60, 17 * 16),
        "end": (47 * 16, 14 * 16),
        "chest": (816, 64),
        "enemies": [],
        "chest_msg": [
            "Chest:\n Movement speed increased by 25%"
        ],
        "chest_reward": [("move_speed", "mul", 1.25)],
    },
    "lvl5": {
        "window": (25 * 16, 10 * 16),
        "map": "assets/maps/map2",
        "start": (60, 140),
        "end": (380, 300),
        "chest": (208, 70),
        "enemies": [],
        "chest_msg": [
            'Mysterious Statue:\n "You are going to need\nthis when you face\nthe devourer of crepes"\n Press Space to continue',
            "You gained an extra heart!"
        ],
        "chest_reward": [("max_hp", "add", 1), ("hp", "add", 1)],
        "chest_change_map": 1
    },
    "lvl6": {
        "window": (25 * 16, 10 * 16),
        "map": "assets/maps/map2.1",
        "start": (60, 140),
        "end": (380, 140),
        "chest": (208, 300),
        "enemies": [],
        "chest_msg": [
            ""
        ],
        "chest_reward": [],
    },
    "lvl7": {
        "window": (50 * 16, 15 * 16),
        "map": "assets/maps/map4",
        "start": (60, 208),
        "end": (380, 1400),
        "chest": (208, 300),
        "enemies": [("Amrany", (42 * 16, 12 * 16))],
        "chest_msg": [
            ""
        ],
        "chest_reward": [],
    },
}