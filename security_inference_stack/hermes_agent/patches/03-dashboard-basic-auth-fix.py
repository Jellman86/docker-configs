#!/opt/hermes/.venv/bin/python
"""Apply the released-image workaround for Hermes password-only dashboard auth.

Hermes v2026.7.7.2 automatically redirects its sole interactive provider to
the OAuth login route. That is invalid when the sole provider is the bundled
password-only Basic provider. Upstream fixed the defect in commit 3e24b16 by
excluding providers that advertise ``supports_password`` from automatic SSO.

This startup patch is deliberately exact and fail-closed. Remove it, its
Compose mount, and its tests once the pinned Hermes image contains that
upstream commit.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile


DEFAULT_MIDDLEWARE_PATH = Path(
    "/opt/hermes/hermes_cli/dashboard_auth/middleware.py"
)
RELEASE_BLOCK = """\
    provider = providers[0]
    prefix = prefix_from_request(request)
"""
FIXED_BLOCK = """\
    provider = providers[0]
    if getattr(provider, "supports_password", False):
        return None

    prefix = prefix_from_request(request)
"""


def patch_middleware(path: Path) -> str:
    """Patch *path* atomically, returning ``applied`` or ``already-applied``."""
    source = path.read_text(encoding="utf-8")
    if FIXED_BLOCK in source:
        return "already-applied"

    matches = source.count(RELEASE_BLOCK)
    if matches != 1:
        raise RuntimeError(
            "refusing to patch unexpected Hermes middleware: "
            f"expected one release block, found {matches}"
        )

    metadata = path.stat()
    updated = source.replace(RELEASE_BLOCK, FIXED_BLOCK, 1)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(updated)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name

        os.chmod(temporary_name, metadata.st_mode)
        if os.geteuid() == 0:
            os.chown(temporary_name, metadata.st_uid, metadata.st_gid)
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)

    return "applied"


def main() -> None:
    """Patch the configured middleware file before s6 starts Hermes services."""
    path = Path(
        os.environ.get("HERMES_AUTH_MIDDLEWARE_PATH", DEFAULT_MIDDLEWARE_PATH)
    )
    result = patch_middleware(path)
    print(f"[hermes-auth-fix] password-provider auto-SSO fix {result}")


if __name__ == "__main__":
    main()
