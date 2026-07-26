from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
README = ROOT / "README.md"
EXPECTED_REVISION = "e21fc265a5a607305e54123160fa42e684c055a9"
EXPECTED_IMAGE = (
    "ghcr.io/jellman86/autofpl@"
    "sha256:4ce701472e1655d422a053214033c4fc6acd4e52aba0c8c835f92e58ef466c3c"
)
EXPECTED_DATA_PATH = "/mnt/apps/docker/autofpl/data"


class AutoFplStackPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        cls.service = cls.compose["services"]["autofpl"]

    def test_image_is_exactly_digest_pinned(self) -> None:
        self.assertEqual(EXPECTED_IMAGE, self.service["image"])
        self.assertRegex(self.service["image"], re.compile(r"@sha256:[0-9a-f]{64}$"))

    def test_documentation_matches_pinned_image(self) -> None:
        documentation = README.read_text(encoding="utf-8")
        self.assertIn(EXPECTED_REVISION, documentation)
        self.assertIn(EXPECTED_IMAGE.split("@", maxsplit=1)[1], documentation)

    def test_service_has_no_host_port_and_one_private_data_mount(self) -> None:
        self.assertNotIn("ports", self.service)
        self.assertEqual(["8080"], self.service["expose"])
        self.assertEqual({"general_brg"}, set(self.service["networks"]))
        self.assertTrue(self.compose["networks"]["general_brg"]["external"])
        self.assertEqual(
            [
                {
                    "type": "bind",
                    "source": EXPECTED_DATA_PATH,
                    "target": "/data",
                    "bind": {"create_host_path": False},
                }
            ],
            self.service["volumes"],
        )

    def test_service_is_non_root_read_only_and_bounded(self) -> None:
        self.assertEqual("1654:1654", self.service["user"])
        self.assertTrue(self.service["read_only"])
        self.assertTrue(self.service["init"])
        self.assertEqual(["ALL"], self.service["cap_drop"])
        self.assertIn("no-new-privileges:true", self.service["security_opt"])
        self.assertIn("/tmp:rw,nosuid,nodev,noexec,size=16m", self.service["tmpfs"])
        self.assertEqual("256m", self.service["mem_limit"])
        for key in ("pids_limit", "mem_limit", "cpus", "stop_grace_period", "logging"):
            self.assertIn(key, self.service)

    def test_health_and_internal_alias_are_explicit(self) -> None:
        self.assertEqual(
            ["CMD", "dotnet", "AutoFpl.Api.dll", "--health-check"],
            self.service["healthcheck"]["test"],
        )
        self.assertIn("autofpl-api", self.service["networks"]["general_brg"]["aliases"])
        self.assertEqual(
            "360",
            self.service["environment"][
                "AutoFpl__Research__FplFormPollIntervalMinutes"
            ],
        )
        self.assertEqual(
            "360",
            self.service["environment"][
                "AutoFpl__Research__OfficialFplPollIntervalMinutes"
            ],
        )


if __name__ == "__main__":
    unittest.main()
