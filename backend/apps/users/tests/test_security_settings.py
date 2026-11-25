import os
import subprocess
import sys
from pathlib import Path
from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[3]


class ProductionSettingsSecurityTestCase(SimpleTestCase):
    """Issue 1: Production settings must reject insecure secrets, wildcards, and default DB passwords."""

    def _run_settings_import(self, env_overrides: dict) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env.update({
            "DEBUG": "False",
            "USE_SQLITE": "True",
            "SECRET_KEY": "valid-production-secret-key-with-sufficient-length-123456",
            "JWT_SECRET_KEY": "valid-production-jwt-key-with-sufficient-length-654321",
            "ALLOWED_HOSTS": "api.hotellinkex.com",
        })
        env.update(env_overrides)
        return subprocess.run(
            [sys.executable, "-c", "import config.settings"],
            cwd=str(BACKEND_DIR),
            env=env,
            capture_output=True,
            text=True,
        )

    def test_rejects_default_or_short_secret_key_in_production(self):
        for bad_key in ("", "short", "django-insecure-local-development-only-key"):
            res = self._run_settings_import({"SECRET_KEY": bad_key})
            self.assertNotEqual(res.returncode, 0, f"Expected failure for SECRET_KEY={bad_key!r}")
            self.assertIn("SECRET_KEY", res.stderr)

    def test_rejects_default_or_short_jwt_secret_key_in_production(self):
        for bad_jwt in ("", "short-jwt", "hotel-linkex-jwt-secret-key-2026"):
            res = self._run_settings_import({"JWT_SECRET_KEY": bad_jwt})
            self.assertNotEqual(res.returncode, 0, f"Expected failure for JWT_SECRET_KEY={bad_jwt!r}")
            self.assertIn("JWT_SECRET_KEY", res.stderr)

    def test_rejects_wildcard_allowed_hosts_in_production(self):
        res = self._run_settings_import({"ALLOWED_HOSTS": "*"})
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("ALLOWED_HOSTS", res.stderr)

    def test_rejects_default_postgres_password_in_production(self):
        res = self._run_settings_import({"USE_SQLITE": "False", "DB_PASSWORD": "hotel_pass123"})
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("DB_PASSWORD", res.stderr)

    def test_accepts_valid_production_configuration(self):
        res = self._run_settings_import({"USE_SQLITE": "False", "DB_PASSWORD": "StrongProdPassword!987654"})
        self.assertEqual(res.returncode, 0, res.stderr)
