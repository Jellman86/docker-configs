#!/usr/bin/env python3
"""Provision least-privileged OpenViking tenant keys for approved clients."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import NoReturn

ACCOUNT_ID = "hermes"
BOOTSTRAP_ADMIN_ID = "bootstrap-admin"
DEFAULT_ENDPOINT = "http://openviking:1933"
USER_SPECS = (
    ("hermes", "OPENVIKING_HERMES_KEY_SEED", "OPENVIKING_API_KEY"),
    ("codex", "OPENVIKING_CODEX_KEY_SEED", "OPENVIKING_CODEX_API_KEY"),
)
PUBLISHED_PLACEHOLDERS = {
    "replace-with-64-random-hex-characters",
    "replace-with-a-random-64-character-hex-key",
}


def fail(message: str) -> NoReturn:
    print(f"OpenViking tenant bootstrap failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def required_hex_secret(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value.lower() in PUBLISHED_PLACEHOLDERS or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        fail(f"{name} must be exactly 64 hexadecimal characters and not a published placeholder")
    return value


def b64url(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def derive_user_key(user_id: str, seed: str) -> str:
    secret = hashlib.sha256(f"{user_id}\0{seed}".encode("utf-8")).hexdigest()
    return f"{b64url(ACCOUNT_ID)}.{b64url(user_id)}.{b64url(secret)}"


def request_json(endpoint: str, root_key: str, method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        f"{endpoint}{path}",
        data=data,
        method=method,
        headers={
            "X-API-Key": root_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        # Status is enough for control flow; never echo response bodies that may contain keys.
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(type(exc).__name__) from exc

    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise RuntimeError("unexpected API response")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("API response has no result object")
    return result


def provision_user(
    endpoint: str,
    root_key: str,
    user_id: str,
    seed: str,
    expected_key: str,
    account_created: bool,
) -> None:
    if account_created:
        try:
            result = request_json(
                endpoint,
                root_key,
                "POST",
                f"/api/v1/admin/accounts/{ACCOUNT_ID}/users",
                {"user_id": user_id, "role": "user", "seed": seed},
            )
        except RuntimeError as exc:
            fail(f"could not register {user_id} user ({exc})")
    else:
        try:
            request_json(
                endpoint,
                root_key,
                "PUT",
                f"/api/v1/admin/accounts/{ACCOUNT_ID}/users/{user_id}/role",
                {"role": "user"},
            )
            result = request_json(
                endpoint,
                root_key,
                "POST",
                f"/api/v1/admin/accounts/{ACCOUNT_ID}/users/{user_id}/key",
                {"seed": seed},
            )
        except RuntimeError as exc:
            if str(exc) != "HTTP 404":
                fail(f"could not reset {user_id} user key ({exc})")
            try:
                result = request_json(
                    endpoint,
                    root_key,
                    "POST",
                    f"/api/v1/admin/accounts/{ACCOUNT_ID}/users",
                    {"user_id": user_id, "role": "user", "seed": seed},
                )
            except RuntimeError as register_exc:
                fail(f"could not recover {user_id} user ({register_exc})")

    returned_key = result.get("user_key")
    if not isinstance(returned_key, str) or not hmac.compare_digest(returned_key, expected_key):
        fail(f"server returned an unexpected tenant key for {user_id}")


def main() -> None:
    root_key = required_hex_secret("OPENVIKING_ROOT_API_KEY")
    endpoint = os.environ.get("OPENVIKING_ENDPOINT", DEFAULT_ENDPOINT).rstrip("/")
    if endpoint != DEFAULT_ENDPOINT:
        fail(f"OPENVIKING_ENDPOINT must remain {DEFAULT_ENDPOINT}")

    credentials: list[tuple[str, str, str]] = []
    for user_id, seed_name, key_name in USER_SPECS:
        seed = required_hex_secret(seed_name)
        expected_key = derive_user_key(user_id, seed)
        configured_key = os.environ.get(key_name, "").strip()
        if not configured_key or not hmac.compare_digest(configured_key, expected_key):
            fail(f"{key_name} does not match {seed_name}")
        credentials.append((user_id, seed, expected_key))

    try:
        request_json(
            endpoint,
            root_key,
            "POST",
            "/api/v1/admin/accounts",
            {
                "account_id": ACCOUNT_ID,
                "admin_user_id": BOOTSTRAP_ADMIN_ID,
                "seed": credentials[0][1],
            },
        )
        account_created = True
    except RuntimeError as exc:
        if str(exc) != "HTTP 409":
            fail(f"could not create account ({exc})")
        account_created = False

    for user_id, seed, expected_key in credentials:
        provision_user(endpoint, root_key, user_id, seed, expected_key, account_created)

    print("OpenViking tenant bootstrap complete for hermes/hermes and hermes/codex (role=user)")


if __name__ == "__main__":
    main()
