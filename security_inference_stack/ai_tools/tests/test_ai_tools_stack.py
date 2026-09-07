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
            {"hermes-agent", "playwright-mcp", "openviking", "openviking-ollama", "rusty-imap-mcp"}
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
        for name in ("searxng", "spider-mcp", "spider-chromium",
                     "research-egress"):
            self.assertNotIn(name, self.services)
        self.assertFalse((ROOT / "skills").exists())
        self.assertFalse((ROOT / "web-research").exists())

    def test_hermes_auth_networks_and_secret_boundary(self) -> None:
        service = self.services["hermes-agent"]
        env = service["environment"]
        self.assertEqual(env["API_SERVER_ENABLED"], "false")
        for key in ("HERMES_DASHBOARD_BASIC_AUTH_USERNAME",
                    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD",
                    "HERMES_DASHBOARD_BASIC_AUTH_SECRET", "OPENVIKING_API_KEY",
                    "HERMES_GITHUB_TOKEN"):
            self.assertIn(":?", env[key])
        for key in ("OPENVIKING_ROOT_API_KEY", "OPENVIKING_CODEX_API_KEY",
                    "SUDO_PASSWORD", "TELEGRAM_BOT_TOKEN", "DISCORD_BOT_TOKEN"):
            self.assertNotIn(key, env)
        self.assertEqual(service["networks"]["npm_proxy_backends"]["aliases"],
                         ["hermes-dashboard"])
        self.assertIn("./managed:/etc/hermes:ro", service["volumes"])
        self.assertIn("no-new-privileges:true", service["security_opt"])
        self.assertEqual(service["volumes"][0]["bind"]["create_host_path"], False)

    def test_hermes_preserves_memory_and_requires_manual_approvals(self) -> None:
        config = yaml.safe_load((ROOT / "managed/config.yaml").read_text())
        self.assertEqual(config["approvals"]["mode"], "manual")
        self.assertEqual(config["approvals"]["cron_mode"], "deny")
        self.assertEqual(config["memory"]["openviking"]["agent"], "hermes")
        memory = config["mcp_servers"]["openviking"]
        self.assertEqual(memory["headers"]["X-OpenViking-Agent"], "hermes")
        self.assertEqual(memory["headers"]["Authorization"], "Bearer ${OPENVIKING_API_KEY}")
        self.assertFalse(config["mcp_servers"]["spider"]["enabled"])
        ha_events = config["platforms"]["homeassistant"]["extra"]
        self.assertFalse(ha_events["watch_all"])
        self.assertEqual(ha_events["watch_domains"], [])
        self.assertEqual(ha_events["watch_entities"], [])
        self.assertEqual(config["timezone"], "Europe/London")
        mail = config["mcp_servers"]["rusty_imap"]["tools"]["include"]
        for tool in ("export_messages", "expunge", "delete_folder"):
            self.assertNotIn(tool, mail)
        for channel in config["platforms"].values():
            self.assertFalse(channel["enabled"])

    def test_shared_tool_endpoints_remain_available_to_trusted_consumers(self) -> None:
        self.assertIn("general_brg", self.services["playwright-mcp"]["networks"])
        self.assertIn("general_brg", self.services["rusty-imap-mcp"]["networks"])
        self.assertIn("npm_proxy_backends", self.services["openviking"]["networks"])

    def test_github_and_mail_writes_require_runtime_consent(self) -> None:
        config = yaml.safe_load((ROOT / "managed/config.yaml").read_text())
        servers = config["mcp_servers"]
        for name in ("github", "rusty_imap"):
            self.assertEqual(servers[name]["trust"], "untrusted")
            self.assertFalse(servers[name]["sampling"]["enabled"])
            self.assertFalse(servers[name]["supports_parallel_tool_calls"])
        github = servers["github"]
        self.assertEqual(github["url"], "https://api.githubcopilot.com/mcp/")
        self.assertEqual(github["headers"]["Authorization"], "Bearer ${HERMES_GITHUB_TOKEN}")
        self.assertTrue({"get_me", "get_file_contents", "pull_request_read", "actions_list"}
                        <= set(github["tools"]["include"]))
        self.assertFalse({"create_repository", "delete_file", "fork_repository"}
                         & set(github["tools"]["include"]))
        self.assertLessEqual(len(github["tools"]["include"]), 25)
        for name, service in self.services.items():
            if name != "hermes-agent":
                self.assertNotIn("HERMES_GITHUB_TOKEN", service.get("environment", {}))

    def test_shared_host_concurrency_and_context_are_bounded(self) -> None:
        config = yaml.safe_load((ROOT / "managed/config.yaml").read_text())
        delegation = config["delegation"]
        self.assertEqual(delegation["max_concurrent_children"], 2)
        self.assertEqual(delegation["max_iterations"], 60)
        self.assertEqual(delegation["max_spawn_depth"], 1)
        self.assertFalse(delegation["subagent_auto_approve"])
        compression = config["compression"]
        self.assertEqual(compression["proactive_prune_tokens"], 48000)
        self.assertGreaterEqual(compression["proactive_prune_min_reclaim_tokens"], 4096)
        self.assertGreaterEqual(compression["protect_last_n"], 20)
        self.assertEqual(config["memory"]["provider"], "openviking")

    def test_only_lightweight_titles_use_luna(self) -> None:
        config = yaml.safe_load((ROOT / "managed/config.yaml").read_text())
        self.assertEqual(config["model"], {"provider": "openai-codex", "default": "gpt-5.6-sol"})
        self.assertEqual(config["agent"]["reasoning_effort"], "high")
        self.assertEqual(config["auxiliary"], {"title_generation": {
            "provider": "openai-codex", "model": "gpt-5.6-luna",
            "reasoning_effort": "low", "max_concurrency": 2,
        }})

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
