from __future__ import annotations

from dataclasses import dataclass

from .crc import crc8_dji, crc16_dji
from .model import FlightMode, PhysicalControls, RawControls

SYNC = 0x55
MIN_FRAME_LENGTH = 13
MAX_FRAME_LENGTH = 0x3FF
PROTOCOL_VERSION = 1

SOURCE_APPLICATION = 0x0A
TARGET_REMOTE = 0x06
COMMAND_TYPE_REQUEST = 0x40
COMMAND_SET_REMOTE = 0x06
COMMAND_READ_CHANNELS = 0x01
COMMAND_READ_BUTTONS = 0x27
COMMAND_SIMULATOR_MODE = 0x24


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DumlFrame:
    raw: bytes
    source: int
    target: int
    sequence: int
    command_type: int
    command_set: int
    command_id: int
    payload: bytes

    @classmethod
    def parse(cls, raw: bytes) -> DumlFrame:
        if len(raw) < MIN_FRAME_LENGTH:
            raise ProtocolError("DUML frame is shorter than 13 bytes")
        if raw[0] != SYNC:
            raise ProtocolError("DUML sync byte is missing")
        length_word = int.from_bytes(raw[1:3], "little")
        length = length_word & MAX_FRAME_LENGTH
        version = length_word >> 10
        if length != len(raw):
            raise ProtocolError(f"DUML length says {length}, received {len(raw)}")
        if version != PROTOCOL_VERSION:
            raise ProtocolError(f"unsupported DUML protocol version {version}")
        if crc8_dji(raw[:3]) != raw[3]:
            raise ProtocolError("DUML header CRC mismatch")
        expected_crc = int.from_bytes(raw[-2:], "little")
        if crc16_dji(raw[:-2]) != expected_crc:
            raise ProtocolError("DUML packet CRC mismatch")
        return cls(
            raw=raw,
            source=raw[4],
            target=raw[5],
            sequence=int.from_bytes(raw[6:8], "little"),
            command_type=raw[8],
            command_set=raw[9],
            command_id=raw[10],
            payload=raw[11:-2],
        )


class FrameDecoder:
    """Incremental DUML stream decoder with CRC-backed resynchronization."""

    def __init__(self, max_buffer: int = 4096) -> None:
        self._buffer = bytearray()
        self.max_buffer = max_buffer
        self.invalid_frames = 0
        self.discarded_bytes = 0

    def clear(self) -> None:
        self._buffer.clear()

    def feed(self, data: bytes) -> list[DumlFrame]:
        self._buffer.extend(data)
        frames: list[DumlFrame] = []
        while True:
            sync_index = self._buffer.find(SYNC)
            if sync_index < 0:
                self.discarded_bytes += len(self._buffer)
                self._buffer.clear()
                break
            if sync_index:
                self.discarded_bytes += sync_index
                del self._buffer[:sync_index]
            if len(self._buffer) < 4:
                break
            length_word = int.from_bytes(self._buffer[1:3], "little")
            length = length_word & MAX_FRAME_LENGTH
            version = length_word >> 10
            header_valid = crc8_dji(self._buffer[:3]) == self._buffer[3]
            if not header_valid or version != PROTOCOL_VERSION or length < MIN_FRAME_LENGTH:
                self.invalid_frames += 1
                del self._buffer[0]
                continue
            if len(self._buffer) < length:
                break
            candidate = bytes(self._buffer[:length])
            try:
                frames.append(DumlFrame.parse(candidate))
            except ProtocolError:
                self.invalid_frames += 1
                del self._buffer[0]
                continue
            del self._buffer[:length]
        if len(self._buffer) > self.max_buffer:
            overflow = len(self._buffer) - self.max_buffer
            self.discarded_bytes += overflow
            del self._buffer[:overflow]
        return frames


def build_command(
    command_id: int,
    *,
    sequence: int,
    payload: bytes = b"",
    source: int = SOURCE_APPLICATION,
    target: int = TARGET_REMOTE,
    command_type: int = COMMAND_TYPE_REQUEST,
    command_set: int = COMMAND_SET_REMOTE,
) -> bytes:
    length = MIN_FRAME_LENGTH + len(payload)
    if length > MAX_FRAME_LENGTH:
        raise ValueError("DUML payload is too large")
    frame = bytearray((SYNC, length & 0xFF, ((length >> 8) & 0x03) | 0x04))
    frame.append(crc8_dji(frame))
    frame.extend((source & 0xFF, target & 0xFF))
    frame.extend((sequence & 0xFFFF).to_bytes(2, "little"))
    frame.extend((command_type & 0xFF, command_set & 0xFF, command_id & 0xFF))
    frame.extend(payload)
    frame.extend(crc16_dji(frame).to_bytes(2, "little"))
    return bytes(frame)


def build_poll_command(sequence: int) -> bytes:
    return build_command(COMMAND_READ_CHANNELS, sequence=sequence)


def build_button_poll_command(sequence: int) -> bytes:
    return build_command(COMMAND_READ_BUTTONS, sequence=sequence)


def build_simulator_mode_command(sequence: int, enabled: bool = True) -> bytes:
    return build_command(
        COMMAND_SIMULATOR_MODE,
        sequence=sequence,
        payload=b"\x01" if enabled else b"\x00",
    )


def is_channel_response(frame: DumlFrame) -> bool:
    return frame.command_set == COMMAND_SET_REMOTE and frame.command_id == COMMAND_READ_CHANNELS


def is_button_response(frame: DumlFrame) -> bool:
    return frame.command_set == COMMAND_SET_REMOTE and frame.command_id == COMMAND_READ_BUTTONS


def parse_physical_controls(frame: DumlFrame) -> PhysicalControls:
    """Decode the RC-N1 extended button/status response (command 0x27)."""
    if len(frame.raw) != 58:
        raise ProtocolError(f"unsupported RC button frame length {len(frame.raw)}")
    bits = int.from_bytes(frame.raw[28:30], "big")
    mode_bits = bits & 0x3000
    modes = {
        0x0000: FlightMode.SPORT,
        0x1000: FlightMode.NORMAL,
        0x2000: FlightMode.CINE,
    }
    return PhysicalControls(
        raw_bits=bits,
        fn=bool(bits & 0x0002),
        record=bool(bits & 0x0004),
        photo=bool(bits & 0x0060),
        rth=bool(bits & 0x0080),
        mode=modes.get(mode_bits, FlightMode.UNKNOWN),
    )


def parse_controls(frame: DumlFrame) -> RawControls:
    """Decode known RC channel layouts after full DUML validation."""
    raw = frame.raw
    if len(raw) == 38:
        base = 13
        packet_format = "rcn1-38"
    elif len(raw) == 32:
        # Seen on newer screen-equipped DJI remotes; harmless to support here.
        base = 12
        packet_format = "dji-32"
    else:
        raise ProtocolError(f"unsupported RC channel frame length {len(raw)}")

    def value(offset: int) -> int:
        end = offset + 2
        if end > len(raw) - 2:
            raise ProtocolError("RC channel frame is truncated")
        return int.from_bytes(raw[offset:end], "little")

    return RawControls(
        right_x=value(base),
        right_y=value(base + 3),
        left_y=value(base + 6),
        left_x=value(base + 9),
        camera=value(base + 12),
        packet_format=packet_format,
    )
