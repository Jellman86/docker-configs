"""Tests for the idempotent OpenViking tenant provisioner."""

from __future__ import annotations

import contextlib
import io
import os
import unittest
from unittest.mock import patch

import bootstrap_tenant


class BootstrapTenantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.seeds = {"hermes": "1" * 64, "codex": "2" * 64}
        self.environment = {
            "OPENVIKING_ROOT_API_KEY": "3" * 64,
            "OPENVIKING_HERMES_KEY_SEED": self.seeds["hermes"],
            "OPENVIKING_API_KEY": bootstrap_tenant.derive_user_key(
                "hermes", self.seeds["hermes"]
            ),
            "OPENVIKING_CODEX_KEY_SEED": self.seeds["codex"],
            "OPENVIKING_CODEX_API_KEY": bootstrap_tenant.derive_user_key(
                "codex", self.seeds["codex"]
            ),
        }

    def run_bootstrap(self, account_exists: bool) -> list[tuple[str, str, dict | None]]:
        calls: list[tuple[str, str, dict | None]] = []

        def fake_request(
            endpoint: str,
            root_key: str,
            method: str,
            path: str,
            body: dict | None = None,
        ) -> dict:
            self.assertEqual(endpoint, bootstrap_tenant.DEFAULT_ENDPOINT)
            self.assertEqual(root_key, self.environment["OPENVIKING_ROOT_API_KEY"])
            calls.append((method, path, body))

            if path == "/api/v1/admin/accounts":
                if account_exists:
                    raise RuntimeError("HTTP 409")
                return {}

            user_id = (body or {}).get("user_id")
            if user_id is None and "/users/" in path:
                user_id = path.split("/users/", 1)[1].split("/", 1)[0]
            if path.endswith("/role"):
                return {}
            return {
                "user_key": bootstrap_tenant.derive_user_key(
                    user_id, self.seeds[user_id]
                )
            }

        with (
            patch.dict(os.environ, self.environment, clear=True),
            patch.object(bootstrap_tenant, "request_json", fake_request),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            bootstrap_tenant.main()
        return calls

    def test_keys_are_bound_to_each_user(self) -> None:
        self.assertNotEqual(
            bootstrap_tenant.derive_user_key("hermes", self.seeds["hermes"]),
            bootstrap_tenant.derive_user_key("codex", self.seeds["hermes"]),
        )

    def test_new_account_creates_both_users(self) -> None:
        calls = self.run_bootstrap(account_exists=False)
        user_creates = [
            body["user_id"]
            for method, path, body in calls
            if method == "POST" and path.endswith("/users") and body is not None
        ]
        self.assertEqual(user_creates, ["hermes", "codex"])

    def test_existing_account_reasserts_roles_and_keys(self) -> None:
        calls = self.run_bootstrap(account_exists=True)
        paths = [path for _, path, _ in calls]
        for user_id in ("hermes", "codex"):
            self.assertIn(
                f"/api/v1/admin/accounts/hermes/users/{user_id}/role", paths
            )
            self.assertIn(
                f"/api/v1/admin/accounts/hermes/users/{user_id}/key", paths
            )

    def test_mismatched_codex_key_fails_before_api_write(self) -> None:
        invalid_environment = {
            **self.environment,
            "OPENVIKING_CODEX_API_KEY": "invalid",
        }
        with (
            patch.dict(os.environ, invalid_environment, clear=True),
            patch.object(bootstrap_tenant, "request_json") as request,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit):
                bootstrap_tenant.main()
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
