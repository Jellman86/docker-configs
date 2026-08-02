"""Tests for the managed OpenViking runtime configuration renderer."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Optional
import unittest


SCRIPT = Path(__file__).with_name("render_config.py")


class RenderConfigTests(unittest.TestCase):
    def render(self, model: Optional[str] = None) -> dict:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "ov.conf"
            environment = {
                **os.environ,
                "OPENVIKING_CONFIG_FILE": str(output),
                "OPENVIKING_ROOT_API_KEY": "a" * 64,
            }
            environment.pop("OPENVIKING_VLM_MODEL", None)
            if model is not None:
                environment["OPENVIKING_VLM_MODEL"] = model
            subprocess.run(
                [sys.executable, str(SCRIPT)],
                check=True,
                env=environment,
                capture_output=True,
                text=True,
            )
            return json.loads(output.read_text())

    def test_supported_default_model(self) -> None:
        config = self.render()
        self.assertEqual(config["vlm"]["model"], "gpt-5.6-luna")
        self.assertNotIn("reasoning_effort", config["vlm"])

    def test_model_can_be_overridden_without_editing_the_renderer(self) -> None:
        self.assertEqual(
            self.render("gpt-5.4")["vlm"]["model"],
            "gpt-5.4",
        )

    def test_invalid_model_identifier_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = {
                **os.environ,
                "OPENVIKING_CONFIG_FILE": str(
                    Path(temporary_directory) / "ov.conf"
                ),
                "OPENVIKING_ROOT_API_KEY": "a" * 64,
                "OPENVIKING_VLM_MODEL": "gpt-5.4-mini\nunsafe",
            }
            result = subprocess.run(
                [sys.executable, str(SCRIPT)],
                env=environment,
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("valid model identifier", result.stderr)

if __name__ == "__main__":
    unittest.main()
