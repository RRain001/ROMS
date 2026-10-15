# Japan Sea: light tests only and ERA5 credential migration

Status: **TEST-ONLY, NO REAL OCEAN INTEGRATION OR DATA DOWNLOAD**. 2026-10-15.
Draft PR #3 remains unmerged; frozen original ES3K / UD1K input bounds and grids remain unchanged.

## Computational scope and GitHub Actions costs

- Do **not** select a production year now. The `JAPAN_SEA` case's 2018 pilot dates and 2024–2025 production dates are **placeholders**, not approvals.
- The expensive `.github/workflows/japan-sea-es3k-online-native.yml` native GEBCO2026/GSHHG full 15″ grid rebuild (up to 55 minutes) is now **workflow_dispatch ONLY**, not run on routine pull requests.
- `.github/workflows/japan-sea-ud1k-bry-schema-contract.yml` automatically runs small, synthetic-only unit/NetCDF tests, including ERA5 credential resolution without any API request. Its real candidate-B 41-layer NetCDF geometry job now runs **workflow_dispatch ONLY**, reusing existing GitHub artifact data rather than downloading bathymetry.
- No ES3K spin-up, month/year simulation, real ocean/atmosphere downloads, or UD1K hydrodynamic integration is authorized by this test-only scope.

## ERA5 API credential migration

The legacy repository once contained `credentials/era5_key.txt`, a **tracked text file with an actual ERA5 key**. Deleting the file from this PR branch does **not** remove it from other branches, releases, clones, Actions caches or Git history. **Revoke/rotate this exposed key at Copernicus CDS** and never reuse the exposed key as a GitHub Secret. History rewriting and mutations of protected `main` were NOT performed.

This PR branch has deleted the tracked credentials file and updated root `.gitignore` to ignore `credentials/`, `.cdsapirc` and related local credential files. It has NOT stored a secret directly because the connected GitHub API tools do not expose an Actions repository-secrets write action.

**Repository administrator must configure the newly rotated key using the GitHub website**:

1. Open [RRain001/ROMS → Settings → Secrets and variables → Actions](https://github.com/RRain001/ROMS/settings/secrets/actions).
2. Click **New repository secret**; name it **`CDSAPI_KEY`**, and paste the **new, rotated** CDS personal API token. Do not share the token in chat, source files, issue text, or Actions logs.
3. `CDSAPI_URL` is optional; by default the wrapper uses the official `https://cds.climate.copernicus.eu/api`.
4. Once the new secret exists, manually dispatch `Japan Sea UD1K ROMS History and BRY Schema Contract` workflow on the current PR branch. The `era5-secret-presence-manual-check` job verifies **only existence**, never prints, echoes, downloads or publishes the secret.

In `ROMS_Nesting/Data_pre/impl/preprocessing/download_era5_staged.py`, the isolated nesting downloader now calls `resolve_era5_credentials`, which prioritizes `CDSAPI_KEY` and `CDSAPI_URL` from environment. When a GitHub Actions job runs without `CDSAPI_KEY`, it **fails closed**, rather than reading the historic tracked file. Local explicit `--credentials-file` is supported only when the credentials file is outside the Git working tree; secrets are never written into the generated NetCDF metadata or diagnostic output.

Example **future** authenticated download job in an opt-in private trusted workflow, once the secret has been rotated/set and a small ERA5 test window has been approved:

```yaml
env:
  CDSAPI_KEY: ${{ secrets.CDSAPI_KEY }}
  CDSAPI_URL: https://cds.climate.copernicus.eu/api
```

This PR intentionally does **NOT** add any download job: only offline-only credential resolver unit tests.

**Critical remaining risk:** the exposed token was in a Git-tracked file. Remove/rotate the key in the upstream CDS account immediately; consider a separate reviewed history-cleanup operation for the original repository. Never force-push history without explicit owner approval.

## Existing data source code reused

The original no-nesting `Data_pre` supports GLORYS12V1 via `copernicusmarine`, ERA5 via `cdsapi`, TPXO9 atlas tides, GEBCO2026 and GSHHG shoreline. The isolated `ROMS_Nesting/Data_pre` already contains copies. For test-only scopes, use small synthetic times/fields and previously verified real grid artifact from GitHub Actions #38680030642. No final calendar is required until a genuine ES3K model integration is planned.

**Expected status:** small synthetic contract tests PASS; ERA5 secret **NOT CONFIGURED BY ASSISTANT**; parent time-dependent actual ROMS history **NOT_RUN**; production nested physical forcing **NOT_RUN**.
