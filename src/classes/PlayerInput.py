from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlayerInput:
    left: bool = False
    right: bool = False
    jump: bool = False
    shoot: bool = False
    aim_x: float = 0.0
    aim_y: float = 0.0
    restart: bool = False
