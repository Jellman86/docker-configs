from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
README = ROOT / "README.md"
EXPECTED_IMAGE = "ghcr.io/jellman86/autofpl:dev"
EXPECTED_DATA_PATH = "/mnt/apps/docker/autofpl/data"
EXPECTED_RESEARCH_NETWORK = "hermes_agent_research_private"


class AutoFplStackPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        cls.service = cls.compose["services"]["autofpl"]

    def test_image_tracks_verified_dev_publications(self) -> None:
        self.assertEqual(EXPECTED_IMAGE, self.service["image"])
        self.assertEqual("always", self.service["pull_policy"])

    def test_documentation_matches_dev_image_policy(self) -> None:
        documentation = README.read_text(encoding="utf-8")
        self.assertIn(EXPECTED_IMAGE, documentation)
        self.assertIn("pull_policy: always", documentation)

    def test_service_has_no_host_port_and_one_private_data_mount(self) -> None:
        self.assertNotIn("ports", self.service)
        self.assertEqual(["8080"], self.service["expose"])
        self.assertEqual(
            {"general_brg", "research_private"}, set(self.service["networks"])
        )
        self.assertTrue(self.compose["networks"]["general_brg"]["external"])
        self.assertTrue(self.compose["networks"]["research_private"]["external"])
        self.assertEqual(
            EXPECTED_RESEARCH_NETWORK,
            self.compose["networks"]["research_private"]["name"],
        )
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
        self.assertEqual(
            "360",
            self.service["environment"][
                "AutoFpl__Research__ResearchSourcePollIntervalMinutes"
            ],
        )


if __name__ == "__main__":
    unittest.main()
