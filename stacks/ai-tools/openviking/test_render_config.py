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
    def render(self, model: Optional[str] = None, provider: str = "openrouter") -> dict:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "ov.conf"
            environment = {
                **os.environ,
                "OPENVIKING_CONFIG_FILE": str(output),
                "OPENVIKING_ROOT_API_KEY": "a" * 64,
                "OPENROUTER_API_KEY": "test-only-placeholder",
                "OPENVIKING_VLM_PROVIDER": provider,
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
        self.assertEqual(config["vlm"]["model"], "inclusionai/ling-3.0-flash-vl:free")
        self.assertEqual(config["vlm"]["provider"], "openrouter")
        self.assertEqual(config["vlm"]["api_key"], "test-only-placeholder")
        self.assertEqual(config["vlm"]["extra_request_body"], {
            "reasoning": {"enabled": False, "exclude": True},
            "provider": {
                "require_parameters": True,
                "data_collection": "deny",
                "zdr": True,
            },
        })
        self.assertNotIn("reasoning_effort", config["vlm"])

    def test_openrouter_override_keeps_its_own_key_and_parameters(self) -> None:
        config = self.render("example/model", provider="openrouter")
        self.assertEqual(config["vlm"]["api_key"], "test-only-placeholder")
        self.assertEqual(config["vlm"]["extra_request_body"], {
            "reasoning": {"enabled": False, "exclude": True},
            "provider": {
                "require_parameters": True,
                "data_collection": "deny",
                "zdr": True,
            },
        })

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
