"""Offline-only ERA5 Actions Secret resolver regressions. No real keys."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"core"))
from era5_action_credentials import (
    DEFAULT_CDS_API_URL, resolve_era5_credentials, _REPOSITORY_ROOT)


class ERA5ActionsSecrets(unittest.TestCase):
    def test_actions_environment_key_preferred_over_missing_default_file(self):
        url,key,source=resolve_era5_credentials(
            "/path/does/not/exist",
            environ={"CDSAPI_KEY":"synthetic_token_123","GITHUB_ACTIONS":"true"})
        self.assertEqual(url,DEFAULT_CDS_API_URL)
        self.assertEqual(key,"synthetic_token_123")
        self.assertEqual(source,"environment")

    def test_custom_https_url_from_environment(self):
        u,k,src=resolve_era5_credentials(
            environ={"CDSAPI_KEY":"synthetic_token_123",
                     "CDSAPI_URL":"https://cds.example.invalid/api"})
        self.assertEqual(u,"https://cds.example.invalid/api")
        self.assertEqual(src,"environment")

    def test_actions_missing_secret_fails_closed_without_file_fallback(self):
        with self.assertRaisesRegex(SystemExit,"Actions Secret is missing"):
            resolve_era5_credentials("/workspace/era5-local.txt",
                                     environ={"GITHUB_ACTIONS":"true"})

    def test_root_tracked_secret_file_rejected(self):
        with self.assertRaisesRegex(SystemExit,"inside the Git working tree"):
            resolve_era5_credentials(
                _REPOSITORY_ROOT/"credentials"/"era5_key.txt",
                environ={})

    def test_local_external_file_only_and_does_not_log_secret(self):
        with tempfile.TemporaryDirectory() as work:
            external=Path(work)/"era5_cds_credentials.txt"
            external.write_text("url: https://cds.example.invalid/api\nkey: fake_synthetic_local_token\n")
            u,k,src=resolve_era5_credentials(external,environ={})
            self.assertEqual(u,"https://cds.example.invalid/api")
            self.assertEqual(k,"fake_synthetic_local_token")
            self.assertEqual(src,"external_local_file")

    def test_env_wins_over_local_file(self):
        with tempfile.TemporaryDirectory() as work:
            external=Path(work)/"not-read.txt"
            external.write_text("key: synthetic_file_token")
            _,key,src=resolve_era5_credentials(
                external,environ={"CDSAPI_KEY":"synthetic_env_token"})
            self.assertEqual(key,"synthetic_env_token")
            self.assertEqual(src,"environment")

    def test_invalid_http_url_rejected(self):
        with self.assertRaisesRegex(SystemExit,"HTTPS"):
            resolve_era5_credentials(environ={"CDSAPI_KEY":"synthetic",
                                             "CDSAPI_URL":"http://bad.invalid"})

    def test_whitespace_key_rejected_without_echoing_key(self):
        with self.assertRaisesRegex(SystemExit,"whitespace") as cm:
            resolve_era5_credentials(environ={"CDSAPI_KEY":"synthetic bad"})
        self.assertNotIn("synthetic bad",str(cm.exception))

    def test_missing_local_file_fails(self):
        with self.assertRaisesRegex(SystemExit,"file not found"):
            resolve_era5_credentials("/tmp/nonexistent_era5_credentials_3833944.txt",environ={})

    def test_empty_env_and_no_file_fails(self):
        with self.assertRaisesRegex(SystemExit,"CDSAPI_KEY is required"):
            resolve_era5_credentials(environ={})


if __name__=="__main__":
    unittest.main()
