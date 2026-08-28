from __future__ import annotations

import unittest

from rcn1_bridge.protocol import COMMAND_READ_CHANNELS, build_command
from rcn1_bridge.transport import Rcn1Transport


def response() -> bytes:
    payload = bytearray(25)
    for offset, value in zip((2, 5, 8, 11, 14), (800, 900, 1000, 1100, 1200), strict=True):
        payload[offset : offset + 2] = value.to_bytes(2, "little")
    return build_command(
        COMMAND_READ_CHANNELS,
        sequence=10,
        payload=bytes(payload),
        source=6,
        target=10,
        command_type=0x80,
    )


class FakeSerial:
    def __init__(self, **_kwargs: object) -> None:
        self.pending = bytearray()
        self.writes: list[bytes] = []
        self.closed = False

    def reset_input_buffer(self) -> None:
        self.pending.clear()

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        if len(data) > 10 and data[10] == COMMAND_READ_CHANNELS:
            self.pending.extend(b"\x00\xff" + response())
        return len(data)

    def read(self, size: int) -> bytes:
        data = bytes(self.pending[:size])
        del self.pending[:size]
        return data

    def close(self) -> None:
        self.closed = True


class TransportTests(unittest.TestCase):
    def test_one_poll_produces_one_validated_sample(self) -> None:
        fake = FakeSerial()
        transport = Rcn1Transport("COM1", serial_factory=lambda **_kwargs: fake)
        transport.open()
        controls = transport.poll()
        self.assertIsNotNone(controls)
        self.assertEqual(controls.left_x, 1100)
        self.assertEqual(transport.stats.polls_sent, 1)
        self.assertEqual(transport.stats.controls_received, 1)
        self.assertEqual(len(fake.writes), 1)
        transport.close()
        self.assertTrue(fake.closed)


if __name__ == "__main__":
    unittest.main()
