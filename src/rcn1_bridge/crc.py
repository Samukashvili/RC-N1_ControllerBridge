"""Small, table-free CRC helpers used by DJI DUML v1 packets."""

from __future__ import annotations


def crc8_dji(data: bytes | bytearray | memoryview, seed: int = 0x77) -> int:
    """Return DJI's reflected CRC-8 over *data*."""
    value = seed & 0xFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ 0x8C if value & 1 else value >> 1
    return value & 0xFF


def crc16_dji(data: bytes | bytearray | memoryview, seed: int = 0x3692) -> int:
    """Return DJI's reflected CRC-16 over *data*."""
    value = seed & 0xFFFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ 0x8408 if value & 1 else value >> 1
    return value & 0xFFFF
