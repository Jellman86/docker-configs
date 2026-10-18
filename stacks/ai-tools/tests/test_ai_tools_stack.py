from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "compose.yaml"


class AiToolsPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = yaml.safe_load(COMPOSE.read_text())
        cls.services = cls.compose["services"]
        cls.networks = cls.compose["networks"]

    def test_required_services_exist(self) -> None:
        self.assertEqual(
            {"playwright-mcp", "openknowledge", "searxng"},
            set(self.services.keys()),
        )

    def test_retired_services_are_absent(self) -> None:
        # Hermes, OpenViking and Rusty IMAP MCP were totally removed on
        # 2026-10-18 (containers, provisioning and data); see README.md.
        for name in ("hermes-agent", "openviking", "openviking-bootstrap",
                     "openviking-ollama", "openviking-ollama-model",
                     "rusty-imap-mcp", "spider-mcp",
                     "spider-chromium", "research-egress"):
            self.assertNotIn(name, self.services)
        self.assertFalse((ROOT / "managed").exists())
        self.assertFalse((ROOT / "openviking").exists())
        self.assertFalse((ROOT / "rusty-imap-mcp").exists())
        self.assertFalse((ROOT / "skills").exists())
        self.assertFalse((ROOT / "web-research").exists())

    def test_no_service_publishes_a_host_port(self) -> None:
        for name, service in self.services.items():
            self.assertNotIn("ports", service, name)

    def test_no_service_mounts_the_docker_socket(self) -> None:
        for name, service in self.services.items():
            for mount in service.get("volumes", []):
                self.assertNotIn("docker.sock", str(mount), name)

    def test_services_are_hardened_and_bounded(self) -> None:
        for name, service in self.services.items():
            self.assertEqual(service.get("cap_drop"), ["ALL"], name)
            self.assertIn("no-new-privileges:true",
                          service.get("security_opt", []), name)
            self.assertIn("mem_limit", service, name)
            self.assertIn("cpus", service, name)

    def test_pinned_images_are_immutable(self) -> None:
        for name, service in self.services.items():
            if name == "searxng":
                continue  # stateless; rolling latest by owner preference
            image = service.get("image")
            if image is None or "${" in image:
                continue
            self.assertIn("@sha256:", image, name)
            self.assertNotIn(":latest@", image, name)

    def test_playwright_browser_stays_isolated(self) -> None:
        service = self.services["playwright-mcp"]
        command = service["command"]
        self.assertIn("--isolated", command)
        self.assertIn("--block-service-workers", command)
        self.assertTrue(
            any(a.startswith("--allowed-hosts=") for a in command),
            "playwright must restrict the Host headers it will serve",
        )
        self.assertIn("general_brg", service["networks"])

    def test_openknowledge_stays_private_pinned_and_behind_npm(self) -> None:
        service = self.services["openknowledge"]
        self.assertTrue(service.get("read_only"))
        env = service["environment"]
        self.assertEqual(env["OK_ALLOW_EXTERNAL"], "1")
        self.assertEqual(
            env["OK_EXTERNAL_URL"],
            "${OPENKNOWLEDGE_EXTERNAL_URL:-https://openknowledge.pownet.uk}",
        )
        self.assertEqual(set(service["networks"]), {"npm_proxy_backends"})
        self.assertEqual(service["volumes"][0]["target"], "/data")
        self.assertTrue(
            any(t.startswith("/home/node:") for t in service["tmpfs"]),
            "server needs a writable passwd-home ~/.ok on the read-only rootfs",
        )
        self.assertEqual(
            service["build"]["args"]["OPENKNOWLEDGE_VERSION"],
            "${OPENKNOWLEDGE_VERSION:-0.86.22}",
        )
        dockerfile = (ROOT / "openknowledge/Dockerfile").read_text()
        self.assertIn("node:24-slim@sha256:", dockerfile)
        self.assertIn("@inkeep/open-knowledge@${OPENKNOWLEDGE_VERSION}", dockerfile)
        self.assertNotIn("ENV OK_ALLOW_EXTERNAL", dockerfile)

    def test_searxng_is_agent_ready_and_secret_free_in_git(self) -> None:
        service = self.services["searxng"]
        self.assertEqual(service["image"], "searxng/searxng:latest")
        self.assertTrue(service.get("read_only"))
        self.assertIn(":?", service["environment"]["SEARXNG_SECRET"])
        self.assertEqual(set(service["networks"]),
                         {"general_brg", "npm_proxy_backends"})
        self.assertEqual(service["volumes"],
                         ["./searxng/settings.yml:/etc/searxng/settings.yml:ro"])
        settings = yaml.safe_load((ROOT / "searxng/settings.yml").read_text())
        self.assertFalse(settings["server"]["limiter"])
        self.assertIn("json", settings["search"]["formats"])
        self.assertNotIn("secret_key", settings.get("server", {}))

    def test_no_orphaned_or_undeclared_networks(self) -> None:
        declared = set(self.networks)
        used: set[str] = set()
        for service in self.services.values():
            nets = service.get("networks")
            if isinstance(nets, dict):
                used |= set(nets)
            elif isinstance(nets, list):
                used |= set(nets)
        self.assertEqual(declared - used, set(), "orphaned networks")
        self.assertEqual(used - declared, set(), "undeclared networks")


if __name__ == "__main__":
    unittest.main()
