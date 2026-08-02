from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
README = ROOT / "README.md"
EXPECTED_IMAGE = "ghcr.io/jellman86/autofpl:dev"
EXPECTED_ANALYTICS_IMAGE = "ghcr.io/jellman86/autofpl-analytics:dev"
EXPECTED_DATA_PATH = "/mnt/apps/docker/autofpl/data"
EXPECTED_INBOX_PATH = "/mnt/apps/docker/autofpl/analytics-inbox"
EXPECTED_SNAPSHOT_PATH = "/mnt/apps/docker/autofpl/analytics-snapshot"
EXPECTED_RESEARCH_NETWORK = "ai_tools_research_private"
EXPECTED_BYPARR_URL = "http://192.168.213.101:8191/"


class AutoFplStackPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        cls.service = cls.compose["services"]["autofpl"]
        cls.analytics = cls.compose["services"]["autofpl-analytics"]

    def test_image_tracks_verified_dev_publications(self) -> None:
        self.assertEqual(EXPECTED_IMAGE, self.service["image"])
        self.assertEqual("always", self.service["pull_policy"])

    def test_documentation_matches_dev_image_policy(self) -> None:
        documentation = README.read_text(encoding="utf-8")
        self.assertIn(EXPECTED_IMAGE, documentation)
        self.assertIn("pull_policy: always", documentation)

    def test_service_has_no_host_port_and_private_mounts(self) -> None:
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
                },
                {
                    "type": "bind",
                    "source": EXPECTED_INBOX_PATH,
                    "target": "/analytics-inbox",
                    "bind": {"create_host_path": False},
                },
                {
                    "type": "bind",
                    "source": EXPECTED_SNAPSHOT_PATH,
                    "target": "/analytics-snapshot",
                    "bind": {"create_host_path": False},
                },
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
        self.assertEqual("512m", self.service["mem_limit"])
        for key in ("pids_limit", "mem_limit", "cpus", "stop_grace_period", "logging"):
            self.assertIn(key, self.service)

    def test_health_and_internal_alias_are_explicit(self) -> None:
        self.assertEqual(
            ["CMD", "dotnet", "AutoFpl.Api.dll", "--health-check"],
            self.service["healthcheck"]["test"],
        )
        self.assertIn("autofpl-api", self.service["networks"]["general_brg"]["aliases"])
        self.assertEqual(
            EXPECTED_BYPARR_URL,
            self.service["environment"]["AutoFpl__Research__ByparrUrl"],
        )
        self.assertEqual(
            "60",
            self.service["environment"][
                "AutoFpl__Research__FbrefMatchLogCaptureIntervalMinutes"
            ],
        )
        self.assertEqual(
            "5",
            self.service["environment"][
                "AutoFpl__Research__FbrefMatchLogCaptureBatchSize"
            ],
        )
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

    def test_shadow_handoff_is_explicitly_enabled(self) -> None:
        self.assertEqual(
            "1",
            self.service["environment"][
                "AutoFpl__Analytics__ShadowInboxPollIntervalMinutes"
            ],
        )
        self.assertEqual(
            "/analytics-inbox",
            self.service["environment"][
                "AutoFpl__Analytics__ShadowInboxPath"
            ],
        )
        self.assertEqual(
            "1",
            self.service["environment"][
                "AutoFpl__Analytics__SnapshotPollIntervalMinutes"
            ],
        )
        self.assertEqual(
            "/analytics-snapshot/autofpl.db",
            self.service["environment"][
                "AutoFpl__Analytics__SnapshotPath"
            ],
        )

    def test_analytics_worker_tracks_verified_dev_publications(self) -> None:
        self.assertEqual(EXPECTED_ANALYTICS_IMAGE, self.analytics["image"])
        self.assertEqual("always", self.analytics["pull_policy"])
        self.assertEqual(
            {"condition": "service_healthy"},
            self.analytics["depends_on"]["autofpl"],
        )

    def test_analytics_worker_has_no_network_or_port(self) -> None:
        self.assertEqual("none", self.analytics["network_mode"])
        self.assertNotIn("networks", self.analytics)
        self.assertNotIn("ports", self.analytics)
        self.assertNotIn("expose", self.analytics)

    def test_analytics_worker_snapshot_is_read_only_and_inbox_is_shared(
        self,
    ) -> None:
        self.assertEqual(
            [
                {
                    "type": "bind",
                    "source": EXPECTED_SNAPSHOT_PATH,
                    "target": "/analytics-snapshot",
                    "read_only": True,
                    "bind": {"create_host_path": False},
                },
                {
                    "type": "bind",
                    "source": EXPECTED_INBOX_PATH,
                    "target": "/analytics-inbox",
                    "bind": {"create_host_path": False},
                },
            ],
            self.analytics["volumes"],
        )

    def test_analytics_worker_is_non_root_read_only_and_bounded(self) -> None:
        self.assertEqual("1654:1654", self.analytics["user"])
        self.assertTrue(self.analytics["read_only"])
        self.assertTrue(self.analytics["init"])
        self.assertEqual(["ALL"], self.analytics["cap_drop"])
        self.assertIn(
            "no-new-privileges:true",
            self.analytics["security_opt"],
        )
        self.assertIn(
            "/tmp:rw,nosuid,nodev,noexec,size=32m",
            self.analytics["tmpfs"],
        )
        self.assertEqual("1g", self.analytics["mem_limit"])
        self.assertEqual(2.0, self.analytics["cpus"])
        for key in (
            "pids_limit",
            "mem_limit",
            "cpus",
            "stop_grace_period",
            "logging",
        ):
            self.assertIn(key, self.analytics)


if __name__ == "__main__":
    unittest.main()
