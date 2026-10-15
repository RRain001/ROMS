"""Resolve ERA5 CDS API credentials without committing or printing secrets.

For GitHub Actions, configure repository Actions secret CDSAPI_KEY and
optionally CDSAPI_URL. Local runs may provide these same environment
variables, or a credentials file OUTSIDE the Git working tree.
Never read a key from this repository's tracked credentials directory.
This module does not retrieve data or make any network connection.
"""
from __future__ import annotations

import os
from pathlib import Path
from collections.abc import Mapping

DEFAULT_CDS_API_URL = "https://cds.climate.copernicus.eu/api"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def resolve_era5_credentials(
    credentials_file: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, str, str]:
    """Return (url, key, source) without ever writing key to stdout/logs.

    Full environment credential takes precedence and should be provided
    through GitHub Secrets -> env: CDSAPI_KEY.
    A local file is supported only outside the Git working tree, as a
    manual/offline developer fallback. Never accept a half-set env key.
    """
    env = os.environ if environ is None else environ
    key = (env.get("CDSAPI_KEY") or "").strip()
    url = (env.get("CDSAPI_URL") or DEFAULT_CDS_API_URL).strip()
    if not url.startswith("https://"):
        raise SystemExit("CDSAPI_URL must use HTTPS")
    if key:
        if any(c.isspace() for c in key):
            raise SystemExit("CDSAPI_KEY contains unexpected whitespace")
        return url, key, "environment"

    if env.get("GITHUB_ACTIONS", "").lower() == "true":
        raise SystemExit("CDSAPI_KEY repository Actions Secret is missing; ERA5 download disabled")

    if credentials_file is None:
        raise SystemExit("CDSAPI_KEY is required or provide an external local --credentials-file")

    p = Path(credentials_file).expanduser().resolve()
    if p.is_relative_to(_REPOSITORY_ROOT):
        raise SystemExit("ERA5 credentials inside the Git working tree are forbidden; use GitHub Secrets or an external local file")
    if not p.is_file():
        raise SystemExit("external ERA5 credentials file not found")
    values: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        k,v = line.split(":", 1)
        values[k.strip().lower()] = v.strip()
    local_key = values.get("key", "")
    local_url = values.get("url", url)
    if not local_key:
        raise SystemExit("external ERA5 credential file is missing key")
    if not local_url.startswith("https://"):
        raise SystemExit("ERA5 credentials URL must use HTTPS")
    if any(c.isspace() for c in local_key):
        raise SystemExit("external ERA5 key contains unexpected whitespace")
    return local_url, local_key, "external_local_file"
