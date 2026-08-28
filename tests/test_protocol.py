from __future__ import annotations

import unittest

from rcn1_bridge.crc import crc8_dji, crc16_dji
from rcn1_bridge.model import FlightMode
from rcn1_bridge.protocol import (
    COMMAND_READ_BUTTONS,
    COMMAND_READ_CHANNELS,
    FrameDecoder,
    ProtocolError,
    build_button_poll_command,
    build_command,
    build_poll_command,
    build_simulator_mode_command,
    parse_controls,
    parse_physical_controls,
)


def channel_frame(
    *,
    right_x: int = 900,
    right_y: int = 1000,
    left_y: int = 1100,
    left_x: int = 1200,
    camera: int = 1024,
) -> bytes:
    payload = bytearray(25)
    for offset, value in zip(
        (2, 5, 8, 11, 14), (right_x, right_y, left_y, left_x, camera), strict=True
    ):
        payload[offset : offset + 2] = value.to_bytes(2, "little")
    return build_command(
        COMMAND_READ_CHANNELS,
        sequence=42,
        payload=bytes(payload),
        source=0x06,
        target=0x0A,
        command_type=0x80,
    )


def button_frame(bits: int) -> bytes:
    payload = bytearray(45)
    payload[17:19] = bits.to_bytes(2, "big")
    return build_command(
        COMMAND_READ_BUTTONS,
        sequence=43,
        payload=bytes(payload),
        source=0x06,
        target=0x0A,
        command_type=0x80,
    )


class CrcTests(unittest.TestCase):
    def test_known_header_crc(self) -> None:
        self.assertEqual(crc8_dji(bytes.fromhex("55 0d 04")), 0x33)

    def test_known_packet_crc(self) -> None:
        packet_without_crc = bytes.fromhex("55 0d 04 33 0a 06 eb 34 40 06 01")
        self.assertEqual(crc16_dji(packet_without_crc), 0x2474)

    def test_known_poll_packet(self) -> None:
        self.assertEqual(
            build_poll_command(0x34EB), bytes.fromhex("55 0d 04 33 0a 06 eb 34 40 06 01 74 24")
        )

    def test_known_simulator_mode_packet(self) -> None:
        self.assertEqual(
            build_simulator_mode_command(0x34EB),
            bytes.fromhex("55 0e 04 66 0a 06 eb 34 40 06 24 01 d9 ec"),
        )

    def test_button_poll_uses_extended_status_command(self) -> None:
        self.assertEqual(build_button_poll_command(7)[10], COMMAND_READ_BUTTONS)


class FrameTests(unittest.TestCase):
    def test_fragmented_stream_and_noise(self) -> None:
        raw = channel_frame()
        decoder = FrameDecoder()
        self.assertEqual(decoder.feed(b"noise" + raw[:5]), [])
        frames = decoder.feed(raw[5:17]) + decoder.feed(raw[17:])
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].sequence, 42)
        self.assertEqual(decoder.discarded_bytes, 5)

    def test_corrupted_packet_is_rejected_and_resynchronized(self) -> None:
        corrupted = bytearray(channel_frame())
        corrupted[13] ^= 0x01
        decoder = FrameDecoder()
        frames = decoder.feed(bytes(corrupted) + channel_frame(right_x=777))
        self.assertEqual(len(frames), 1)
        self.assertEqual(parse_controls(frames[0]).right_x, 777)
        self.assertGreaterEqual(decoder.invalid_frames, 1)

    def test_channel_offsets(self) -> None:
        decoder = FrameDecoder()
        frame = decoder.feed(channel_frame())[0]
        controls = parse_controls(frame)
        self.assertEqual(
            (controls.right_x, controls.right_y, controls.left_y, controls.left_x, controls.camera),
            (900, 1000, 1100, 1200, 1024),
        )

    def test_parse_rejects_bad_crc(self) -> None:
        from rcn1_bridge.protocol import DumlFrame

        raw = bytearray(channel_frame())
        raw[-1] ^= 0xFF
        with self.assertRaises(ProtocolError):
            DumlFrame.parse(bytes(raw))

    def test_extended_buttons_and_mode(self) -> None:
        decoder = FrameDecoder()
        controls = parse_physical_controls(decoder.feed(button_frame(0x2086))[0])
        self.assertTrue(controls.fn)
        self.assertTrue(controls.record)
        self.assertTrue(controls.rth)
        self.assertEqual(controls.mode, FlightMode.CINE)

    def test_mode_switch_values(self) -> None:
        decoder = FrameDecoder()
        for bits, expected in (
            (0x0000, FlightMode.SPORT),
            (0x1000, FlightMode.NORMAL),
            (0x2000, FlightMode.CINE),
        ):
            controls = parse_physical_controls(decoder.feed(button_frame(bits))[0])
            self.assertEqual(controls.mode, expected)


if __name__ == "__main__":
    unittest.main()
