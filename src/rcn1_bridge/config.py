from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AxisCalibration:
    minimum: int = 364
    center: int = 1024
    maximum: int = 1684
    invert: bool = False
    deadzone: float = 0.02
    expo: float = 0.0

    def validate(self, name: str) -> None:
        if not self.minimum < self.center < self.maximum:
            raise ValueError(f"{name}: calibration must satisfy minimum < center < maximum")
        if not 0.0 <= self.deadzone < 0.5:
            raise ValueError(f"{name}: deadzone must be between 0.0 and 0.5")
        if not -0.95 <= self.expo <= 0.95:
            raise ValueError(f"{name}: expo must be between -0.95 and 0.95")


def _default_axes() -> dict[str, AxisCalibration]:
    return {
        "left_x": AxisCalibration(),
        "left_y": AxisCalibration(invert=True),
        "right_x": AxisCalibration(),
        "right_y": AxisCalibration(invert=True),
        "camera": AxisCalibration(deadzone=0.08),
    }


@dataclass(slots=True)
class BridgeConfig:
    port: str | None = None
    baud_rate: int = 115200
    reconnect_seconds: float = 1.0
    response_timeout_seconds: float = 0.15
    stale_neutral_seconds: float = 0.25
    camera_button_threshold: float = 0.75
    camera_left_button: str = "A"
    camera_right_button: str = "B"
    smoothing: float = 0.0
    suppress_duplicate_reports: bool = True
    probe_unknown_ports: bool = False
    axes: dict[str, AxisCalibration] = field(default_factory=_default_axes)

    def validate(self) -> None:
        if not 1200 <= self.baud_rate <= 4_000_000:
            raise ValueError("baud_rate is outside the supported range")
        if not 0.01 <= self.response_timeout_seconds <= 2.0:
            raise ValueError("response_timeout_seconds must be between 0.01 and 2.0")
        if not 0.0 <= self.reconnect_seconds <= 60.0:
            raise ValueError("reconnect_seconds must be between 0 and 60")
        if not 0.05 <= self.stale_neutral_seconds <= 5.0:
            raise ValueError("stale_neutral_seconds must be between 0.05 and 5.0")
        if not 0.1 <= self.camera_button_threshold <= 1.0:
            raise ValueError("camera_button_threshold must be between 0.1 and 1.0")
        if not 0.0 <= self.smoothing <= 0.95:
            raise ValueError("smoothing must be between 0.0 and 0.95")
        required = {"left_x", "left_y", "right_x", "right_y", "camera"}
        missing = required - self.axes.keys()
        if missing:
            raise ValueError(f"missing axis configuration: {', '.join(sorted(missing))}")
        for name, axis in self.axes.items():
            axis.validate(name)


def default_config_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home()))
        return root / "RCN1Bridge" / "config.json"
    return Path.home() / ".config" / "rcn1-bridge" / "config.json"


def load_config(path: Path | None = None) -> BridgeConfig:
    config_path = path or default_config_path()
    if not config_path.exists():
        config = BridgeConfig()
        config.validate()
        return config
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read config {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("config root must be a JSON object")
    known = {item.name for item in BridgeConfig.__dataclass_fields__.values()}
    unknown = data.keys() - known
    if unknown:
        raise ValueError(f"unknown config keys: {', '.join(sorted(unknown))}")
    axes_data = data.pop("axes", {})
    axes = _default_axes()
    if not isinstance(axes_data, dict):
        raise ValueError("axes must be a JSON object")
    axis_fields = set(AxisCalibration.__dataclass_fields__)
    for name, values in axes_data.items():
        if name not in axes or not isinstance(values, dict):
            raise ValueError(f"invalid axis configuration for {name}")
        unknown_axis = values.keys() - axis_fields
        if unknown_axis:
            raise ValueError(f"{name}: unknown keys {', '.join(sorted(unknown_axis))}")
        axes[name] = AxisCalibration(**values)
    config = BridgeConfig(**data, axes=axes)
    config.validate()
    return config


def save_config(config: BridgeConfig, path: Path | None = None) -> Path:
    config.validate()
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    payload: dict[str, Any] = asdict(config)
    temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(config_path)
    return config_path
