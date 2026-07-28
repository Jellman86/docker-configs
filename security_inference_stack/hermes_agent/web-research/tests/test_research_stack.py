from __future__ import annotations

import ipaddress
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"
MANAGED = ROOT / "managed" / "config.yaml"
SQUID = ROOT / "web-research" / "squid.conf"
CHROMIUM_LAUNCHER = ROOT / "web-research" / "chromium-launcher.js"
SEARXNG = ROOT / "web-research" / "searxng" / "settings.yml"
PATCH = ROOT / "web-research" / "spider-mcp" / "hardening.patch"
SPIDER_DOCKERFILE = ROOT / "web-research" / "spider-mcp" / "Dockerfile"
RESEARCH_SKILL = ROOT / "skills" / "private-web-research" / "SKILL.md"


class ResearchStackPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = yaml.safe_load(COMPOSE.read_text())
        cls.services = cls.compose["services"]
        cls.networks = cls.compose["networks"]
        cls.managed = yaml.safe_load(MANAGED.read_text())

    def test_required_services_exist(self) -> None:
        self.assertTrue(
            {"research-egress", "byparr", "searxng", "spider-chromium", "spider-mcp"}
            <= self.services.keys()
        )

    def test_no_research_service_publishes_ports_or_mounts_docker_socket(self) -> None:
        for name in ("research-egress", "byparr", "searxng", "spider-chromium", "spider-mcp"):
            service = self.services[name]
            self.assertNotIn("ports", service, name)
            for mount in service.get("volumes", []):
                self.assertNotIn("docker.sock", str(mount), name)

    def test_networks_force_browser_search_and_crawler_through_proxy(self) -> None:
        self.assertTrue(self.networks["research_private"]["internal"])
        self.assertTrue(self.networks["spider_browser_private"]["internal"])
        self.assertTrue(self.networks["spider_mcp_private"]["internal"])
        self.assertTrue(self.networks["search_private"]["internal"])
        self.assertFalse(self.networks["research_egress"].get("internal", False))

        self.assertEqual(
            set(self.services["spider-chromium"]["networks"]),
            {"spider_browser_private"},
        )
        self.assertEqual(
            set(self.services["searxng"]["networks"]),
            {"search_private", "research_private"},
        )
        self.assertEqual(
            set(self.services["spider-mcp"]["networks"]),
            {"spider_mcp_private", "spider_browser_private", "research_private"},
        )
        self.assertEqual(
            set(self.services["research-egress"]["networks"]),
            {"research_private", "spider_browser_private", "research_egress"},
        )
        self.assertEqual(
            set(self.services["byparr"]["networks"]),
            {"research_private"},
        )

    def test_services_are_hardened_and_bounded(self) -> None:
        for name in ("research-egress", "byparr", "searxng", "spider-chromium", "spider-mcp"):
            service = self.services[name]
            self.assertTrue(service.get("read_only"), name)
            self.assertEqual(service.get("cap_drop"), ["ALL"], name)
            self.assertIn("no-new-privileges:true", service.get("security_opt", []), name)
            self.assertIn("mem_limit", service, name)
            self.assertIn("cpus", service, name)
            self.assertIn("pids_limit", service, name)
            self.assertIn("healthcheck", service, name)

    def test_images_and_build_inputs_are_immutable(self) -> None:
        for name in ("research-egress", "byparr", "searxng", "spider-chromium"):
            image = self.services[name]["image"]
            self.assertIn("@sha256:", image, name)
            self.assertNotIn(":latest@", image, name)
        build_args = self.services["spider-mcp"]["build"]["args"]
        self.assertRegex(build_args["SPIDER_COMMIT"], r"^[0-9a-f]{40}$")
        self.assertRegex(build_args["SPIDER_SOURCE_SHA256"], r"^[0-9a-f]{64}$")

    def test_playwright_owns_an_isolated_proxy_forced_browser(self) -> None:
        service = self.services["playwright-mcp"]
        command = service["command"]
        self.assertNotIn("PLAYWRIGHT_MCP_CDP_ENDPOINT", service.get("environment", {}))
        self.assertIn("--isolated", command)
        self.assertIn("--proxy-server=http://research-egress:3128", command)
        self.assertIn("--proxy-bypass=<-loopback>", command)
        self.assertNotIn("spider_browser_private", service["networks"])
        self.assertIn("research-egress", service["depends_on"])

    def test_byparr_is_private_proxy_forced_and_uses_local_healthcheck(self) -> None:
        service = self.services["byparr"]
        self.assertEqual(service["environment"]["PROXY_SERVER"], "http://research-egress:3128")
        self.assertIn("research-egress", service["depends_on"])
        self.assertNotIn("general_brg", service["networks"])
        probe = " ".join(service["healthcheck"]["test"])
        self.assertIn("127.0.0.1',8191", probe)
        self.assertNotIn("/health", probe)
        self.assertNotIn("google", probe.lower())

    def test_spider_browser_is_not_shared_with_playwright(self) -> None:
        self.assertIn("spider_browser_private", self.services["spider-chromium"]["networks"])
        self.assertNotIn("research_private", self.services["spider-chromium"]["networks"])
        self.assertIn("spider_browser_private", self.services["spider-mcp"]["networks"])
        self.assertNotIn("spider_browser_private", self.services["playwright-mcp"]["networks"])

    def test_spider_chromium_uses_playwright_managed_launcher(self) -> None:
        service = self.services["spider-chromium"]
        self.assertEqual(service["entrypoint"], ["node", "/opt/hermes/chromium-launcher.js"])
        self.assertIn(
            "./web-research/chromium-launcher.js:/opt/hermes/chromium-launcher.js:ro",
            service["volumes"],
        )
        launcher = CHROMIUM_LAUNCHER.read_text()
        self.assertIn("chromium.launch", launcher)
        self.assertIn("remote-debugging-port=${INTERNAL_CDP_PORT}", launcher)
        self.assertIn("server.listen(EXTERNAL_CDP_PORT, '0.0.0.0'", launcher)
        self.assertIn("ws://spider-chromium:${EXTERNAL_CDP_PORT}", launcher)
        self.assertIn("http://research-egress:3128", launcher)
        self.assertIn("<-loopback>", launcher)

    def test_hermes_has_only_bounded_spider_tools_and_searxng_search(self) -> None:
        self.assertEqual(self.managed["web"]["search_backend"], "searxng")
        self.assertNotIn("extract_backend", self.managed["web"])
        self.assertNotIn("firecrawl", MANAGED.read_text().lower())
        spider = self.managed["mcp_servers"]["spider"]
        self.assertEqual(spider["url"], "http://spider-mcp:8080/mcp")
        self.assertFalse(spider["sampling"]["enabled"])
        self.assertEqual(
            spider["tools"]["include"],
            ["spider_scrape", "spider_crawl", "spider_links"],
        )

    def test_managed_skill_routes_research_without_firecrawl(self) -> None:
        skill = RESEARCH_SKILL.read_text()
        for marker in (
            "web_search",
            "mcp__spider__spider_scrape",
            "mcp__spider__spider_links",
            "mcp__spider__spider_crawl",
            "mcp__playwright__browser_navigate",
            "Do not use `web_extract`",
        ):
            self.assertIn(marker, skill)
        self.assertNotIn("FIRECRAWL_API_KEY", skill)

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
        for path in (SQUID, SEARXNG, CHROMIUM_LAUNCHER):
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

    def test_searxng_json_api_and_proxy_are_forced(self) -> None:
        settings = yaml.safe_load(SEARXNG.read_text())
        self.assertEqual(settings["search"]["formats"], ["json"])
        self.assertEqual(settings["server"]["bind_address"], "0.0.0.0")
        self.assertFalse(settings["server"]["limiter"])
        self.assertEqual(
            settings["outgoing"]["proxies"]["all://"],
            ["http://research-egress:3128"],
        )
        self.assertIsInstance(settings["outgoing"]["extra_proxy_timeout"], int)
        self.assertNotIn("secret_key", settings["server"])
        required_value = self.services["searxng"]["environment"]["SEARXNG_SECRET"]
        self.assertTrue(required_value.startswith("${SEARXNG_SECRET:?"))

    def test_spider_patch_removes_bypass_fields_and_enforces_caps(self) -> None:
        patch = PATCH.read_text()
        for removed in ("pub proxy:", "pub cookie:", "pub external_domains:", "pub respect_robots_txt:"):
            self.assertRegex(patch, rf"(?m)^-\s+{removed}")
        self.assertIn("MAX_CRAWL_PAGES: u32 = 10", patch)
        self.assertIn("MAX_CRAWL_DEPTH: usize = 3", patch)
        self.assertIn("with_respect_robots_txt(true)", patch)
        self.assertIn("deny_unknown_fields", patch)
        self.assertIn("untrusted_remote_content", patch)

    def test_spider_enforces_single_request_concurrency_and_bounded_links(self) -> None:
        patch = PATCH.read_text()
        self.assertGreaterEqual(patch.count("with_concurrency_limit(Some(1))"), 3)
        self.assertIn("MAX_LINKS: usize = 100", patch)
        self.assertIn("Semaphore::new(1)", patch)
        self.assertIn("TOOL_TIMEOUT", patch)
        self.assertGreaterEqual(patch.count("AbortOnDrop"), 3)
        self.assertIn("CRAWL_DEADLINE", patch)
        environment = self.services["spider-mcp"]["environment"]
        self.assertEqual(environment["SPIDER_RESPECT_CONCURRENCY_UNDER_LOAD"], "true")

    def test_spider_builder_installs_the_rustfmt_component_it_executes(self) -> None:
        dockerfile = SPIDER_DOCKERFILE.read_text()
        self.assertIn("rustup component add rustfmt", dockerfile)


if __name__ == "__main__":
    unittest.main()
