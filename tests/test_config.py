from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rcn1_bridge.config import BridgeConfig, load_config, save_config


class ConfigTests(unittest.TestCase):
    def test_legacy_defaults_migrate_to_direct_axes_and_disabled_wheel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "camera_left_button": "A",
                        "camera_right_button": "B",
                        "axes": {
                            "left_y": {"invert": True},
                            "right_y": {"invert": True},
                        },
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(path)
        self.assertFalse(config.axes["left_y"].invert)
        self.assertFalse(config.axes["right_y"].invert)
        self.assertEqual(config.camera_left_button, "NONE")
        self.assertEqual(config.camera_right_button, "NONE")
        self.assertEqual(config.schema_version, 3)
        self.assertEqual(config.response_timeout_seconds, 0.04)

    def test_new_schema_preserves_explicit_inversion(self) -> None:
        config = BridgeConfig()
        config.axes["left_y"].invert = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            save_config(config, path)
            loaded = load_config(path)
        self.assertTrue(loaded.axes["left_y"].invert)

    def test_version_two_default_timeout_is_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"schema_version": 2, "response_timeout_seconds": 0.15}),
                encoding="utf-8",
            )
            config = load_config(path)
        self.assertEqual(config.schema_version, 3)
        self.assertEqual(config.response_timeout_seconds, 0.04)

    def test_version_two_custom_timeout_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"schema_version": 2, "response_timeout_seconds": 0.08}),
                encoding="utf-8",
            )
            config = load_config(path)
        self.assertEqual(config.schema_version, 3)
        self.assertEqual(config.response_timeout_seconds, 0.08)


if __name__ == "__main__":
    unittest.main()
