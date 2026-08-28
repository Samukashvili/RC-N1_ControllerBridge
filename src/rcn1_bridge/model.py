from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FlightMode(str, Enum):
    SPORT = "Sport"
    NORMAL = "Normal"
    CINE = "Cine"
    UNKNOWN = "Unknown"


@dataclass(frozen=True, slots=True)
class RawControls:
    right_x: int
    right_y: int
    left_y: int
    left_x: int
    camera: int
    packet_format: str = "rcn1-38"


@dataclass(frozen=True, slots=True)
class PhysicalControls:
    raw_bits: int = 0
    fn: bool = False
    record: bool = False
    photo: bool = False
    rth: bool = False
    mode: FlightMode = FlightMode.UNKNOWN


@dataclass(frozen=True, slots=True)
class MappedControls:
    left_x: float
    left_y: float
    right_x: float
    right_y: float
    camera: float
    buttons: frozenset[str] = frozenset()

    def neutral(self) -> bool:
        return not any(
            (
                self.left_x,
                self.left_y,
                self.right_x,
                self.right_y,
                self.camera,
                bool(self.buttons),
            )
        )


NEUTRAL_MAPPED = MappedControls(0.0, 0.0, 0.0, 0.0, 0.0)
NEUTRAL_PHYSICAL = PhysicalControls()
