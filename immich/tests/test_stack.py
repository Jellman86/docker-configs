from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
QUARK = ROOT / "docker-compose.quark.yml"
README = ROOT / "README.md"


class ImmichStackPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        cls.services = cls.compose["services"]
        cls.server = cls.services["immich-server"]
        cls.database = cls.services["immich-database"]
        cls.redis = cls.services["immich-redis"]
        cls.ml = cls.services["immich-machine-learning"]

    def test_the_four_upstream_services_are_present(self) -> None:
        self.assertEqual(
            {
                "immich-server",
                "immich-machine-learning",
                "immich-redis",
                "immich-database",
            },
            set(self.services),
        )

    def test_microservices_container_is_not_resurrected(self) -> None:
        # Upstream merged the workers into immich-server in v1.118.0. A compose
        # file carrying immich-microservices is copied from a stale blog post.
        for name, service in self.services.items():
            self.assertNotIn("microservices", name)
            self.assertNotIn("command", service, name)

    def test_database_uses_the_vector_enabled_upstream_image(self) -> None:
        # Immich runs vector similarity search over CLIP and face embeddings,
        # so a stock Postgres image cannot serve this stack.
        image = self.database["image"]
        self.assertTrue(image.startswith("ghcr.io/immich-app/postgres:"), image)
        self.assertIn("vectorchord", image)
        self.assertNotIn("pgvecto-rs", image)
        self.assertNotIn("tensorchord", image)

    def test_infrastructure_images_are_digest_pinned(self) -> None:
        # Upstream pins third-party images by digest; Immich's own images float
        # on the major-version metatag.
        for name in ("immich-redis", "immich-database"):
            self.assertIn("@sha256:", self.services[name]["image"], name)
        for name in ("immich-server", "immich-machine-learning"):
            self.assertIn("${IMMICH_VERSION:-v3}", self.services[name]["image"], name)

    def test_no_service_publishes_a_host_port(self) -> None:
        for name, service in self.services.items():
            self.assertNotIn("ports", service, name)

    def test_only_the_server_joins_the_proxy_network(self) -> None:
        self.assertIn("general_brg", self.server["networks"])
        for name in ("immich-database", "immich-redis", "immich-machine-learning"):
            self.assertNotIn("general_brg", self.services[name]["networks"], name)

    def test_database_password_has_no_default_in_a_public_repo(self) -> None:
        # A default here would publish a working credential to GitHub.
        raw = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("${IMMICH_DB_PASSWORD}", raw)
        self.assertNotIn("IMMICH_DB_PASSWORD:-", raw)

    def test_database_state_stays_off_the_media_pool_and_shares(self) -> None:
        source = next(
            v["source"]
            for v in self.database["volumes"]
            if v["target"] == "/var/lib/postgresql/data"
        )
        self.assertIn("/mnt/apps/docker", source)
        self.assertNotIn("/mnt/tank", source)

    def test_media_lives_on_the_bulk_pool(self) -> None:
        source = next(
            v["source"] for v in self.server["volumes"] if v["target"] == "/data"
        )
        self.assertIn("/mnt/tank", source)

    def test_igpu_is_passed_to_transcoding_and_inference(self) -> None:
        for name in ("immich-server", "immich-machine-learning"):
            service = self.services[name]
            self.assertIn("/dev/dri:/dev/dri", service["devices"], name)
            self.assertIn("${RENDER_GID:-107}", service["group_add"], name)
        # OpenVINO inference additionally needs the DRI cgroup rule.
        self.assertIn("c 189:* rmw", self.ml["device_cgroup_rules"])
        self.assertTrue(self.ml["image"].endswith("-openvino"), self.ml["image"])

    def test_machine_learning_is_opt_in(self) -> None:
        # Riker has roughly 3 GB free of 15 GB and no swap; the worker needs
        # 2-4 GB resident, so it must not start unless explicitly enabled.
        self.assertIn("machine-learning", self.ml["profiles"])
        for name in ("immich-server", "immich-redis", "immich-database"):
            self.assertNotIn("profiles", self.services[name], name)

    def test_every_service_is_hardened_and_bounded(self) -> None:
        for name, service in self.services.items():
            self.assertIn("no-new-privileges:true", service.get("security_opt", []), name)
            self.assertIn("mem_limit", service, name)
            self.assertEqual("unless-stopped", service.get("restart"), name)
            self.assertEqual("json-file", service["logging"]["driver"], name)

    def test_proxy_network_is_external_and_backend_is_owned(self) -> None:
        networks = self.compose["networks"]
        self.assertTrue(networks["general_brg"]["external"])
        self.assertNotIn("external", networks["immich_backend"])

    def test_readme_documents_the_reverse_proxy_requirements(self) -> None:
        # All three are silent-failure modes behind Nginx Proxy Manager.
        text = README.read_text(encoding="utf-8")
        self.assertIn("client_max_body_size", text)
        self.assertIn("proxy_request_buffering", text)
        self.assertIn("Websockets", text)


class ImmichQuarkWorkerTests(unittest.TestCase):
    """The machine-learning worker deployed on Quark, not Riker."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = yaml.safe_load(QUARK.read_text(encoding="utf-8"))
        cls.ml = cls.compose["services"]["immich-machine-learning"]

    def test_quark_file_carries_only_the_worker(self) -> None:
        self.assertEqual({"immich-machine-learning"}, set(self.compose["services"]))

    def test_worker_uses_the_openvino_image_on_the_same_major(self) -> None:
        image = self.ml["image"]
        self.assertTrue(image.endswith("-openvino"), image)
        # Server and worker must share a major version.
        self.assertIn("${IMMICH_VERSION:-v3}", image)

    def test_worker_uses_quarks_render_group_not_rikers(self) -> None:
        # Quark is 105, Riker is 107. Hard-coding either breaks the other host.
        self.assertIn("${RENDER_GID:-105}", self.ml["group_add"])
        self.assertIn("/dev/dri:/dev/dri", self.ml["devices"])
        self.assertIn("c 189:* rmw", self.ml["device_cgroup_rules"])

    def test_worker_port_is_bound_to_a_lan_address_not_all_interfaces(self) -> None:
        # Immich's ML API is unauthenticated, so the bind address is the only
        # boundary. A bare "3003:3003" would publish it on every interface.
        published = self.ml["ports"]
        self.assertEqual(1, len(published))
        # Resolve ${VAR:-default} first - the defaults themselves contain colons.
        resolved = re.sub(r"\$\{[A-Za-z0-9_]+:-([^}]*)\}", r"\1", published[0])
        self.assertEqual(3, len(resolved.split(":")), resolved)
        bind_addr = resolved.split(":")[0]
        self.assertNotEqual("0.0.0.0", bind_addr)
        self.assertTrue(bind_addr.startswith("192.168."), bind_addr)
        self.assertTrue(resolved.endswith(":3003"), resolved)

    def test_worker_is_hardened_and_bounded(self) -> None:
        self.assertIn("no-new-privileges:true", self.ml["security_opt"])
        self.assertIn("mem_limit", self.ml)
        self.assertEqual("unless-stopped", self.ml["restart"])
        self.assertEqual("json-file", self.ml["logging"]["driver"])

    def test_worker_has_no_profile_so_it_actually_starts(self) -> None:
        # The Riker copy is profile-gated off; this one is the live worker.
        self.assertNotIn("profiles", self.ml)


if __name__ == "__main__":
    unittest.main()
