from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RawControls:
    right_x: int
    right_y: int
    left_y: int
    left_x: int
    camera: int
    packet_format: str = "rcn1-38"


@dataclass(frozen=True, slots=True)
class MappedControls:
    left_x: float
    left_y: float
    right_x: float
    right_y: float
    camera: float
    camera_left: bool = False
    camera_right: bool = False

    def neutral(self) -> bool:
        return not any(
            (
                self.left_x,
                self.left_y,
                self.right_x,
                self.right_y,
                self.camera,
                self.camera_left,
                self.camera_right,
            )
        )


NEUTRAL_MAPPED = MappedControls(0.0, 0.0, 0.0, 0.0, 0.0)
