from __future__ import annotations

import math

from .config import AxisCalibration, BridgeConfig
from .model import MappedControls, RawControls


def map_axis(raw: int, calibration: AxisCalibration) -> float:
    """Map an asymmetric calibrated input to [-1, 1]."""
    if raw >= calibration.center:
        span = calibration.maximum - calibration.center
    else:
        span = calibration.center - calibration.minimum
    value = (raw - calibration.center) / span
    value = max(-1.0, min(1.0, value))
    if calibration.invert:
        value = -value

    magnitude = abs(value)
    if magnitude <= calibration.deadzone:
        return 0.0
    magnitude = (magnitude - calibration.deadzone) / (1.0 - calibration.deadzone)
    # Positive expo softens the center while preserving endpoints.
    curved = (1.0 - calibration.expo) * magnitude + calibration.expo * magnitude**3
    return math.copysign(max(0.0, min(1.0, curved)), value)


class ControlMapper:
    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self._previous: MappedControls | None = None

    def reset(self) -> None:
        self._previous = None

    def map(self, raw: RawControls) -> MappedControls:
        axes = self.config.axes
        current = MappedControls(
            left_x=map_axis(raw.left_x, axes["left_x"]),
            left_y=map_axis(raw.left_y, axes["left_y"]),
            right_x=map_axis(raw.right_x, axes["right_x"]),
            right_y=map_axis(raw.right_y, axes["right_y"]),
            camera=map_axis(raw.camera, axes["camera"]),
        )
        if self._previous is not None and self.config.smoothing:
            old_weight = self.config.smoothing
            new_weight = 1.0 - old_weight
            current = MappedControls(
                left_x=self._previous.left_x * old_weight + current.left_x * new_weight,
                left_y=self._previous.left_y * old_weight + current.left_y * new_weight,
                right_x=self._previous.right_x * old_weight + current.right_x * new_weight,
                right_y=self._previous.right_y * old_weight + current.right_y * new_weight,
                camera=self._previous.camera * old_weight + current.camera * new_weight,
            )
        threshold = self.config.camera_button_threshold
        current = MappedControls(
            left_x=current.left_x,
            left_y=current.left_y,
            right_x=current.right_x,
            right_y=current.right_y,
            camera=current.camera,
            camera_left=current.camera <= -threshold,
            camera_right=current.camera >= threshold,
        )
        self._previous = current
        return current
