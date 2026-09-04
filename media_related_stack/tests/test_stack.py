from __future__ import annotations

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
README = ROOT / "README.md"


class MediaStackPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        cls.plex = cls.compose["services"]["plex"]
        cls.jellyfin = cls.compose["services"]["jellyfin"]

    def test_jellyfin_uses_the_stable_linuxserver_image_contract(self) -> None:
        self.assertEqual(
            "lscr.io/linuxserver/jellyfin:latest", self.jellyfin["image"]
        )
        self.assertEqual("jellyfin", self.jellyfin["container_name"])
        self.assertEqual("unless-stopped", self.jellyfin["restart"])
        self.assertEqual(
            {
                "PUID=${PUID:-568}",
                "PGID=${PGID:-568}",
                "TZ=${TZ:-Europe/London}",
                "UMASK=${UMASK:-002}",
                "LIBVA_DRIVER_NAME=${LIBVA_DRIVER_NAME:-iHD}",
            },
            set(self.jellyfin["environment"]),
        )

    def test_jellyfin_reads_the_exact_plex_media_source(self) -> None:
        plex_media = next(
            volume
            for volume in self.plex["volumes"]
            if volume["target"] == "/library"
        )
        jellyfin_media = next(
            volume
            for volume in self.jellyfin["volumes"]
            if volume["target"] == "/library"
        )
        self.assertEqual(plex_media["source"], jellyfin_media["source"])
        self.assertTrue(jellyfin_media["read_only"])
        self.assertFalse(jellyfin_media["bind"]["create_host_path"])

    def test_plex_reads_only_immich_originals(self) -> None:
        immich_mounts = {
            volume["target"]: volume
            for volume in self.plex["volumes"]
            if volume["target"].startswith("/immich/")
        }
        self.assertEqual({"/immich/library", "/immich/upload"}, set(immich_mounts))
        self.assertEqual(
            "${IMMICH_PHOTOS_PATH:-/mnt/tank/photos}/library",
            immich_mounts["/immich/library"]["source"],
        )
        self.assertEqual(
            "${IMMICH_PHOTOS_PATH:-/mnt/tank/photos}/upload",
            immich_mounts["/immich/upload"]["source"],
        )
        for volume in immich_mounts.values():
            self.assertTrue(volume["read_only"])
            self.assertFalse(volume["bind"]["create_host_path"])

        sources = {volume["source"] for volume in self.plex["volumes"]}
        self.assertNotIn("${IMMICH_PHOTOS_PATH:-/mnt/tank/photos}", sources)
        for generated_directory in ("thumbs", "encoded-video", "backups", "profile"):
            self.assertFalse(
                any(source.endswith(f"/{generated_directory}") for source in sources)
            )

    def test_jellyfin_state_is_persistent_and_separate_from_plex(self) -> None:
        config = next(
            volume
            for volume in self.jellyfin["volumes"]
            if volume["target"] == "/config"
        )
        self.assertEqual(
            "${DOCKERCONFIGPATH:-/mnt/apps/docker}/jellyfin", config["source"]
        )
        self.assertTrue(config["bind"]["create_host_path"])

    def test_jellyfin_exposes_intel_gpu_and_host_discovery(self) -> None:
        self.assertEqual(["/dev/dri:/dev/dri"], self.jellyfin["devices"])
        self.assertEqual("host", self.jellyfin["network_mode"])
        self.assertNotIn("ports", self.jellyfin)
        self.assertNotIn("privileged", self.jellyfin)

    def test_jellyfin_healthcheck_allows_for_database_migrations(self) -> None:
        healthcheck = self.jellyfin["healthcheck"]
        self.assertIn("http://localhost:8096/health", " ".join(healthcheck["test"]))
        self.assertEqual("2m", healthcheck["start_period"])
        self.assertGreaterEqual(healthcheck["retries"], 3)

    def test_jellyfin_logs_are_bounded(self) -> None:
        self.assertEqual("json-file", self.jellyfin["logging"]["driver"])
        self.assertEqual("10m", self.jellyfin["logging"]["options"]["max-size"])
        self.assertEqual("3", self.jellyfin["logging"]["options"]["max-file"])

    def test_jellyfin_runbook_records_required_post_deploy_steps(self) -> None:
        documentation = README.read_text(encoding="utf-8")
        for required in (
            "http://localhost:8096/health",
            "/dev/dri/renderD128",
            "Intel Quick Sync (QSV)",
            "read-only",
            "https://jellyfin.org/docs/general/installation/container/",
            "https://docs.linuxserver.io/images/docker-jellyfin/",
        ):
            self.assertIn(required, documentation)


if __name__ == "__main__":
    unittest.main()
