from __future__ import annotations

import threading
from abc import ABC, abstractmethod

from .model import NEUTRAL_MAPPED, MappedControls


class GamepadOutput(ABC):
    @abstractmethod
    def update(self, controls: MappedControls) -> None:
        raise NotImplementedError

    @abstractmethod
    def neutralize(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class NullOutput(GamepadOutput):
    """Safe diagnostics backend that creates no virtual device."""

    def __init__(self) -> None:
        self.last = NEUTRAL_MAPPED
        self.report_count = 0

    def update(self, controls: MappedControls) -> None:
        self.last = controls
        self.report_count += 1

    def neutralize(self) -> None:
        self.update(NEUTRAL_MAPPED)

    def close(self) -> None:
        self.neutralize()


class XboxOutput(GamepadOutput):
    BUTTON_NAMES = {
        "A": "XUSB_GAMEPAD_A",
        "B": "XUSB_GAMEPAD_B",
        "X": "XUSB_GAMEPAD_X",
        "Y": "XUSB_GAMEPAD_Y",
        "LB": "XUSB_GAMEPAD_LEFT_SHOULDER",
        "RB": "XUSB_GAMEPAD_RIGHT_SHOULDER",
        "BACK": "XUSB_GAMEPAD_BACK",
        "START": "XUSB_GAMEPAD_START",
        "L3": "XUSB_GAMEPAD_LEFT_THUMB",
        "R3": "XUSB_GAMEPAD_RIGHT_THUMB",
    }

    def __init__(self, camera_left_button: str = "A", camera_right_button: str = "B") -> None:
        try:
            import vgamepad as vg
        except (ImportError, OSError) as exc:
            raise RuntimeError(
                "vgamepad/ViGEmBus is unavailable. Run setup.ps1 and install the driver."
            ) from exc
        self._vg = vg
        self._pad = vg.VX360Gamepad()
        self._lock = threading.Lock()
        self._closed = False
        self._left_button = self._resolve_button(camera_left_button)
        self._right_button = self._resolve_button(camera_right_button)
        self.neutralize()

    def _resolve_button(self, name: str):
        normalized = name.upper()
        try:
            attribute = self.BUTTON_NAMES[normalized]
        except KeyError as exc:
            choices = ", ".join(self.BUTTON_NAMES)
            raise ValueError(f"unknown Xbox button {name!r}; choose one of {choices}") from exc
        return getattr(self._vg.XUSB_BUTTON, attribute)

    @staticmethod
    def _axis(value: float) -> int:
        value = max(-1.0, min(1.0, value))
        return round(value * (32767 if value >= 0.0 else 32768))

    def update(self, controls: MappedControls) -> None:
        with self._lock:
            if self._closed:
                return
            self._pad.left_joystick(
                x_value=self._axis(controls.left_x), y_value=self._axis(controls.left_y)
            )
            self._pad.right_joystick(
                x_value=self._axis(controls.right_x), y_value=self._axis(controls.right_y)
            )
            if controls.camera_left:
                self._pad.press_button(button=self._left_button)
            else:
                self._pad.release_button(button=self._left_button)
            if controls.camera_right:
                self._pad.press_button(button=self._right_button)
            else:
                self._pad.release_button(button=self._right_button)
            self._pad.update()

    def neutralize(self) -> None:
        self.update(NEUTRAL_MAPPED)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._pad.reset()
            self._pad.update()
            self._closed = True


def create_output(kind: str, camera_left_button: str, camera_right_button: str) -> GamepadOutput:
    if kind == "none":
        return NullOutput()
    if kind == "xbox":
        return XboxOutput(camera_left_button, camera_right_button)
    raise ValueError(f"unsupported output backend {kind!r}")
