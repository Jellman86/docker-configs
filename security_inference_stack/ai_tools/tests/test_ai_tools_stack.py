from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"


class AiToolsPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = yaml.safe_load(COMPOSE.read_text())
        cls.services = cls.compose["services"]
        cls.networks = cls.compose["networks"]

    def test_required_services_exist(self) -> None:
        self.assertTrue(
            {"playwright-mcp", "openviking", "openviking-ollama", "rusty-imap-mcp"}
            <= self.services.keys()
        )

    def test_no_ai_tool_publishes_a_host_port(self) -> None:
        for name, service in self.services.items():
            self.assertNotIn("ports", service, name)

    def test_no_ai_tool_mounts_the_docker_socket(self) -> None:
        for name, service in self.services.items():
            for mount in service.get("volumes", []):
                self.assertNotIn("docker.sock", str(mount), name)

    def test_services_are_hardened_and_bounded(self) -> None:
        for name in ("playwright-mcp", "openviking", "rusty-imap-mcp"):
            service = self.services[name]
            self.assertEqual(service.get("cap_drop"), ["ALL"], name)
            self.assertIn("no-new-privileges:true", service.get("security_opt", []), name)
            self.assertIn("mem_limit", service, name)
            self.assertIn("cpus", service, name)

    def test_pinned_images_are_immutable(self) -> None:
        for name, service in self.services.items():
            image = service.get("image")
            if image is None or "${" in image:
                continue
            self.assertIn("@sha256:", image, name)
            self.assertNotIn(":latest@", image, name)

    def test_playwright_browser_stays_isolated(self) -> None:
        service = self.services["playwright-mcp"]
        command = service["command"]
        # --isolated keeps each session in a throwaway profile. The browser no
        # longer runs behind the squid egress gateway, so this and the
        # allowed-hosts list are what remain of its boundary.
        self.assertIn("--isolated", command)
        self.assertIn("--block-service-workers", command)
        self.assertNotIn("PLAYWRIGHT_MCP_CDP_ENDPOINT", service.get("environment", {}))
        self.assertTrue(
            any(a.startswith("--allowed-hosts=") for a in command),
            "playwright must restrict the Host headers it will serve",
        )

    def test_openviking_embedding_stays_local(self) -> None:
        # OpenRouter's free tier allows 50 requests a day; OpenViking issues
        # roughly 2,900, so the embedder must not be pointed at a remote API.
        env = self.services["openviking"]["environment"]
        self.assertIn("OPENVIKING_EMBED_MODEL", env)
        self.assertIn("OPENVIKING_EMBED_DIMENSION", env)

    def test_retired_runtimes_are_absent(self) -> None:
        for name in ("hermes-agent", "searxng", "spider-mcp", "spider-chromium",
                     "research-egress"):
            self.assertNotIn(name, self.services)
        self.assertFalse((ROOT / "managed").exists())
        self.assertFalse((ROOT / "skills").exists())
        self.assertFalse((ROOT / "web-research").exists())

    def test_shared_tool_endpoints_remain_available_to_trusted_consumers(self) -> None:
        self.assertIn("general_brg", self.services["playwright-mcp"]["networks"])
        self.assertIn("general_brg", self.services["rusty-imap-mcp"]["networks"])
        self.assertIn("npm_proxy_backends", self.services["openviking"]["networks"])

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
