from __future__ import annotations

import random
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass

from .model import RawControls
from .protocol import (
    FrameDecoder,
    build_poll_command,
    build_simulator_mode_command,
    is_channel_response,
    parse_controls,
)


class TransportError(RuntimeError):
    pass


@dataclass(slots=True)
class TransportStats:
    polls_sent: int = 0
    frames_received: int = 0
    controls_received: int = 0
    response_timeouts: int = 0
    invalid_frames: int = 0
    discarded_bytes: int = 0
    last_response_ms: float = 0.0
    average_response_ms: float = 0.0


class Rcn1Transport:
    """Synchronous one-request-at-a-time serial transport."""

    def __init__(
        self,
        port: str,
        *,
        baud_rate: int = 115200,
        response_timeout: float = 0.15,
        serial_factory: Callable[..., object] | None = None,
    ) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.response_timeout = response_timeout
        self._serial_factory = serial_factory
        self._serial: object | None = None
        self._decoder = FrameDecoder()
        self._sequence = random.SystemRandom().randrange(0x10000)
        self.stats = TransportStats()
        self._response_time_total = 0.0

    def open(self) -> None:
        if self._serial is not None:
            return
        try:
            if self._serial_factory is None:
                import serial

                factory = serial.Serial
            else:
                factory = self._serial_factory
            self._serial = factory(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=min(0.05, self.response_timeout),
                write_timeout=0.25,
            )
            reset_input = getattr(self._serial, "reset_input_buffer", None)
            if reset_input:
                reset_input()
            self._decoder.clear()
        except Exception as exc:
            self._serial = None
            raise TransportError(f"could not open {self.port}: {exc}") from exc

    def close(self) -> None:
        serial_port, self._serial = self._serial, None
        if serial_port is not None:
            with suppress(Exception):
                serial_port.close()

    def __enter__(self) -> Rcn1Transport:
        self.open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _next_sequence(self) -> int:
        sequence = self._sequence
        self._sequence = (self._sequence + 1) & 0xFFFF
        return sequence

    def _write(self, data: bytes) -> None:
        if self._serial is None:
            raise TransportError("serial port is not open")
        try:
            written = self._serial.write(data)
            if written is not None and written != len(data):
                raise TransportError(f"short serial write: {written}/{len(data)} bytes")
        except TransportError:
            raise
        except Exception as exc:
            raise TransportError(f"serial write failed on {self.port}: {exc}") from exc

    def enable_simulator_mode(self) -> None:
        self._write(build_simulator_mode_command(self._next_sequence()))

    def poll(self) -> RawControls | None:
        """Send one poll, then wait for one validated channel response."""
        if self._serial is None:
            raise TransportError("serial port is not open")
        started = time.perf_counter()
        self._write(build_poll_command(self._next_sequence()))
        self.stats.polls_sent += 1
        deadline = started + self.response_timeout
        try:
            while time.perf_counter() < deadline:
                # Asking pyserial for a large fixed block waits for that entire
                # block or the port timeout, even after a 38-byte reply arrived.
                # Block for one byte when idle, then drain what is already ready.
                waiting = int(getattr(self._serial, "in_waiting", 0) or 0)
                chunk = self._serial.read(max(1, min(256, waiting)))
                if not chunk:
                    continue
                frames = self._decoder.feed(bytes(chunk))
                self.stats.invalid_frames = self._decoder.invalid_frames
                self.stats.discarded_bytes = self._decoder.discarded_bytes
                for frame in frames:
                    self.stats.frames_received += 1
                    if not is_channel_response(frame):
                        continue
                    controls = parse_controls(frame)
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    self.stats.controls_received += 1
                    self.stats.last_response_ms = elapsed_ms
                    self._response_time_total += elapsed_ms
                    self.stats.average_response_ms = (
                        self._response_time_total / self.stats.controls_received
                    )
                    return controls
        except Exception as exc:
            raise TransportError(f"serial read failed on {self.port}: {exc}") from exc
        self.stats.response_timeouts += 1
        return None


def probe_port(port: str, *, baud_rate: int = 115200, timeout: float = 0.2) -> bool:
    try:
        with Rcn1Transport(port, baud_rate=baud_rate, response_timeout=timeout) as transport:
            return transport.poll() is not None
    except (TransportError, OSError):
        return False
