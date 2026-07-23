"""Tests for the temporary Hermes dashboard Basic-auth compatibility patch."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest


PATCH_PATH = Path(__file__).with_name("03-dashboard-basic-auth-fix.py")
SPEC = importlib.util.spec_from_file_location("dashboard_basic_auth_fix", PATCH_PATH)
assert SPEC is not None and SPEC.loader is not None
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)


class DashboardBasicAuthFixTests(unittest.TestCase):
    def _middleware(self, content: str) -> Path:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        directory = Path(temporary_directory.name)
        path = directory / "middleware.py"
        path.write_text(content, encoding="utf-8")
        path.chmod(0o640)
        return path

    def test_applies_upstream_fix_and_preserves_permissions(self) -> None:
        path = self._middleware(f"before\n{PATCH.RELEASE_BLOCK}after\n")

        result = PATCH.patch_middleware(path)

        self.assertEqual(result, "applied")
        self.assertEqual(
            path.read_text(encoding="utf-8"),
            f"before\n{PATCH.FIXED_BLOCK}after\n",
        )
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)

    def test_is_idempotent(self) -> None:
        path = self._middleware(f"before\n{PATCH.FIXED_BLOCK}after\n")

        result = PATCH.patch_middleware(path)

        self.assertEqual(result, "already-applied")
        self.assertEqual(
            path.read_text(encoding="utf-8"),
            f"before\n{PATCH.FIXED_BLOCK}after\n",
        )

    def test_refuses_unknown_source_without_modifying_it(self) -> None:
        content = "def unrelated():\n    return True\n"
        path = self._middleware(content)

        with self.assertRaisesRegex(RuntimeError, "unexpected Hermes middleware"):
            PATCH.patch_middleware(path)

        self.assertEqual(path.read_text(encoding="utf-8"), content)


if __name__ == "__main__":
    unittest.main()
