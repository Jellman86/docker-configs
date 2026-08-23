from __future__ import annotations

import ipaddress
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"
SQUID = ROOT / "web-research" / "squid.conf"


class ResearchStackPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = yaml.safe_load(COMPOSE.read_text())
        cls.services = cls.compose["services"]
        cls.networks = cls.compose["networks"]

    def test_required_services_exist(self) -> None:
        self.assertTrue(
            {"research-egress", "playwright-mcp"} <= self.services.keys()
        )

    def test_no_research_service_publishes_ports_or_mounts_docker_socket(self) -> None:
        for name in ("research-egress", "playwright-mcp"):
            service = self.services[name]
            self.assertNotIn("ports", service, name)
            for mount in service.get("volumes", []):
                self.assertNotIn("docker.sock", str(mount), name)

    def test_no_ai_tool_publishes_a_host_port(self) -> None:
        for name, service in self.services.items():
            self.assertNotIn("ports", service, name)

    def test_networks_force_browser_search_and_crawler_through_proxy(self) -> None:
        self.assertTrue(self.networks["research_private"]["internal"])
        self.assertFalse(self.networks["research_egress"].get("internal", False))

        self.assertEqual(
            set(self.services["research-egress"]["networks"]),
            {"research_private", "research_egress"},
        )

    def test_services_are_hardened_and_bounded(self) -> None:
        for name in ("research-egress", "playwright-mcp"):
            service = self.services[name]
            self.assertTrue(service.get("read_only"), name)
            self.assertEqual(service.get("cap_drop"), ["ALL"], name)
            self.assertIn("no-new-privileges:true", service.get("security_opt", []), name)
            self.assertIn("mem_limit", service, name)
            self.assertIn("cpus", service, name)
            self.assertIn("pids_limit", service, name)
            self.assertIn("healthcheck", service, name)

    def test_images_and_build_inputs_are_immutable(self) -> None:
        for name in ("research-egress", "playwright-mcp"):
            image = self.services[name]["image"]
            self.assertIn("@sha256:", image, name)
            self.assertNotIn(":latest@", image, name)

    def test_playwright_owns_an_isolated_proxy_forced_browser(self) -> None:
        service = self.services["playwright-mcp"]
        command = service["command"]
        self.assertNotIn("PLAYWRIGHT_MCP_CDP_ENDPOINT", service.get("environment", {}))
        self.assertIn("--isolated", command)
        self.assertIn("--proxy-server=http://research-egress:3128", command)
        self.assertIn("--proxy-bypass=<-loopback>", command)
        self.assertIn("research-egress", service["depends_on"])



    def test_retired_agent_runtime_is_absent(self) -> None:
        self.assertNotIn("hermes-agent", self.services)
        self.assertFalse((ROOT / "managed").exists())
        self.assertFalse((ROOT / "skills").exists())

    def test_shared_tool_endpoints_remain_available_to_trusted_consumers(self) -> None:
        self.assertIn("general_brg", self.services["playwright-mcp"]["networks"])
        self.assertIn("general_brg", self.services["rusty-imap-mcp"]["networks"])
        self.assertIn("npm_proxy_backends", self.services["openviking"]["networks"])

    def test_squid_denies_all_private_special_ranges_before_allow(self) -> None:
        text = SQUID.read_text()
        expected = [
            "0.0.0.0/8",
            "10.0.0.0/8",
            "100.64.0.0/10",
            "127.0.0.0/8",
            "169.254.0.0/16",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "198.18.0.0/15",
            "224.0.0.0/4",
            "240.0.0.0/4",
            "::1/128",
            "fc00::/7",
            "fe80::/10",
            "ff00::/8",
        ]
        for network in expected:
            ipaddress.ip_network(network)
            self.assertIn(network, text)
        self.assertLess(text.index("http_access deny blocked_destination"), text.index("http_access allow all"))
        self.assertIn("acl Safe_ports port 80", text)
        self.assertIn("acl Safe_ports port 443", text)

    def test_squid_denies_literal_ipv4_mapped_ipv6_before_allow(self) -> None:
        text = SQUID.read_text()
        self.assertIn("acl blocked_mapped_ipv6 url_regex", text)
        self.assertIn(r"\[::ffff:", text)
        self.assertLess(
            text.index("http_access deny blocked_mapped_ipv6"),
            text.index("http_access allow all"),
        )

    def test_bind_mounted_configs_are_readable_by_non_root_services(self) -> None:
        for path in (SQUID,):
            self.assertEqual(path.stat().st_mode & 0o444, 0o444, str(path))

    def test_squid_healthcheck_uses_available_bash_tcp_probe(self) -> None:
        probe = self.services["research-egress"]["healthcheck"]["test"]
        self.assertIn("/bin/bash", probe[-1])
        self.assertIn("/dev/tcp/127.0.0.1/3128", probe[-1])
        self.assertNotIn("squidclient", probe[-1])

    def test_squid_hostname_acl_has_no_overlapping_localhost_entries(self) -> None:
        acl = next(
            line for line in SQUID.read_text().splitlines()
            if line.startswith("acl blocked_hostname dstdomain")
        ).split()
        self.assertIn("localhost", acl)
        self.assertNotIn(".localhost", acl)

    def test_squid_config_has_no_noncompliant_via_override(self) -> None:
        self.assertNotIn("\nvia off\n", SQUID.read_text())



