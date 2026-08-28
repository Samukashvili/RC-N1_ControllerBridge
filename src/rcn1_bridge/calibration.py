from __future__ import annotations

import statistics
import time
from collections.abc import Callable

from .config import AxisCalibration, BridgeConfig
from .model import RawControls
from .transport import Rcn1Transport

AXIS_NAMES = ("left_x", "left_y", "right_x", "right_y", "camera")


def _values(controls: RawControls) -> dict[str, int]:
    return {name: getattr(controls, name) for name in AXIS_NAMES}


def capture_calibration(
    transport: Rcn1Transport,
    *,
    center_seconds: float = 2.0,
    range_seconds: float = 10.0,
    on_phase: Callable[[str, float], None] | None = None,
) -> dict[str, tuple[int, int, int]]:
    centers: dict[str, list[int]] = {name: [] for name in AXIS_NAMES}
    ranges: dict[str, list[int]] = {name: [] for name in AXIS_NAMES}

    def collect(target: dict[str, list[int]], duration: float, phase: str) -> None:
        start = time.monotonic()
        while (elapsed := time.monotonic() - start) < duration:
            if on_phase:
                on_phase(phase, min(1.0, elapsed / duration))
            controls = transport.poll()
            if controls is None:
                continue
            for name, value in _values(controls).items():
                target[name].append(value)
        if on_phase:
            on_phase(phase, 1.0)

    collect(centers, center_seconds, "center")
    if not all(centers.values()):
        raise RuntimeError("no controller samples were received during center capture")
    collect(ranges, range_seconds, "range")
    if not all(ranges.values()):
        raise RuntimeError("no controller samples were received during range capture")

    result: dict[str, tuple[int, int, int]] = {}
    for name in AXIS_NAMES:
        center = round(statistics.median(centers[name]))
        minimum = min(ranges[name] + centers[name])
        maximum = max(ranges[name] + centers[name])
        if minimum >= center - 50 or maximum <= center + 50:
            raise RuntimeError(f"{name} did not move far enough in both directions")
        result[name] = (minimum, center, maximum)
    return result


def apply_calibration(
    config: BridgeConfig, values: dict[str, tuple[int, int, int]]
) -> BridgeConfig:
    for name, (minimum, center, maximum) in values.items():
        previous = config.axes[name]
        config.axes[name] = AxisCalibration(
            minimum=minimum,
            center=center,
            maximum=maximum,
            invert=previous.invert,
            deadzone=previous.deadzone,
            expo=previous.expo,
        )
    config.validate()
    return config
