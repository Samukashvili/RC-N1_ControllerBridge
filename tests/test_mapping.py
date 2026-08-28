from __future__ import annotations

import unittest

from rcn1_bridge.config import AxisCalibration, BridgeConfig
from rcn1_bridge.mapping import ControlMapper, map_axis
from rcn1_bridge.model import RawControls


class MappingTests(unittest.TestCase):
    def test_asymmetric_ranges_reach_endpoints(self) -> None:
        calibration = AxisCalibration(minimum=300, center=1000, maximum=1800)
        self.assertEqual(map_axis(300, calibration), -1.0)
        self.assertEqual(map_axis(1000, calibration), 0.0)
        self.assertEqual(map_axis(1800, calibration), 1.0)

    def test_deadzone_is_removed_and_range_rescaled(self) -> None:
        calibration = AxisCalibration(deadzone=0.1)
        self.assertEqual(map_axis(1024 + 20, calibration), 0.0)
        self.assertAlmostEqual(map_axis(1684, calibration), 1.0)

    def test_inversion(self) -> None:
        calibration = AxisCalibration(invert=True, deadzone=0.0)
        self.assertLess(map_axis(1200, calibration), 0.0)

    def test_camera_buttons_always_release_inside_threshold(self) -> None:
        config = BridgeConfig(camera_button_threshold=0.5)
        mapper = ControlMapper(config)
        right = mapper.map(RawControls(1024, 1024, 1024, 1024, 1684))
        centered = mapper.map(RawControls(1024, 1024, 1024, 1024, 1024))
        self.assertTrue(right.camera_right)
        self.assertFalse(centered.camera_right)
        self.assertFalse(centered.camera_left)


if __name__ == "__main__":
    unittest.main()
