from __future__ import annotations

import unittest
from dataclasses import dataclass

from rcn1_bridge.ports import rank_ports


@dataclass
class FakePort:
    device: str
    description: str
    hwid: str = ""
    vid: int | None = None
    pid: int | None = None


class PortTests(unittest.TestCase):
    def test_protocol_name_wins_without_hard_coded_model(self) -> None:
        ports = [
            FakePort("COM9", "Future DJI USB VCOM For Protocol", vid=0x9999),
            FakePort("COM4", "Generic USB serial", vid=0x2CA3),
        ]
        ranked = rank_ports(ports)
        self.assertEqual(ranked[0].device, "COM9")

    def test_debug_port_is_always_excluded(self) -> None:
        ranked = rank_ports([FakePort("COM6", "DEVICE USB VCOM For Debug", vid=0x2CA3)])
        self.assertEqual(ranked, [])

    def test_unknown_ports_require_opt_in(self) -> None:
        unknown = FakePort("COM3", "Standard Serial over Bluetooth link")
        self.assertEqual(rank_ports([unknown]), [])
        self.assertEqual(rank_ports([unknown], include_unknown=True)[0].device, "COM3")


if __name__ == "__main__":
    unittest.main()
