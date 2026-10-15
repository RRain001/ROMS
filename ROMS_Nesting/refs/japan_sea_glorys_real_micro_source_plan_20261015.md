# Japan Sea GLORYS12V1: repaired case config and **bounded real-data micro request** (test-only)

**Date:** 2026-10-15; **working PR:** [#3](https://github.com/RRain001/ROMS/pull/3) remains Draft. The official ES3K/UD1K original grids, main branch and scientific production year remain **unchanged/unselected**. User requires limited testing only, not long runs or expensive automatic GitHub Actions.

## Repository finding and fix

The inherited original *single-grid* ROMS preprocessor already knows how to download and stage GLORYS12V1 through the `copernicusmarine` CLI, handling `thetao/so/uo/vo/zos`, optional 2D/3D separate subset fallback, CF source daily mean time center, and ocean initial/outer boundary conversion. However, the isolated `ROMS_Nesting/Data_pre/cases/JAPAN_SEA/config` **did not contain** `glorys12v1_download_config.json`. Therefore a standard actual `ROMS_CASE_NAME=JAPAN_SEA` call to `load_glorys_config()` was blocked before any data could be requested. This was a real configuration gap, not an excuse to reimplement the ocean download system.

Added the case-specific [`glorys12v1_download_config.json`](../Data_pre/cases/JAPAN_SEA/config/glorys12v1_download_config.json) with the same Copernicus reanalysis dataset ID, 3D/2D fields, static dataset parts and timestamp semantics as the existing non-nested cases; it sets `boundary_download_strategy=edge_bands` for future efficient ES3K outer boundary retrieval. It **does not activate a simulation** and does not select the project's eventual year. The original top-level `Data_pre` remains untouched. A fast **fresh-process subprocess test** with `ROMS_CASE_NAME=JAPAN_SEA` uses the actual legacy `ocean_source_utils.load_glorys_config()` entry point and verifies the new config is loadable.

## Explicitly capped **real** data micro sample (future opt-in only)

[`japan_sea_glorys_micro_plan.py`](../Data_pre/nesting/japan_sea_glorys_micro_plan.py) defaults to **PLAN ONLY**; never uses the full-domain downloader and never accesses an API unless `--execute` is explicitly provided.

| Parameter | Strict limit |
| --- | --- |
| Data provider | Copernicus Marine GLORYS12V1 `GLOBAL_MULTIYEAR_PHY_001_030` |
| Dataset | `cmems_mod_glo_phy_my_0.083deg_P1D-m` |
| Place | Japan Sea offshore center near (130°E, 37°N) |
| Longitude / latitude | **129.75–130.25°E, 36.75–37.25°N** (0.5×0.5°) |
| Time window | **2018-01-01 12:00 – 2018-01-03 12:00** (two-day span, three daily means; **TEST FIXTURE DATES ONLY**) |
| Depth | 0–300 m |
| Variables | `thetao,so,uo,vo,zos` |
| Maximum accepted NetCDF | **5 MiB** |
| ROMS integration | **NOT RUN** |
| Existing source-stage logic | `download_glorys12v1_staged.merged_subset_with_2d3d_fallback()` with official `copernicusmarine subset`, not a newly invented provider client |
| Case simulation dates | **NOT SET** |

A successful explicit small download produces staged CF `time/depth/latitude/longitude` with five data variables, and independent strict checks for ordering, bounds, physically meaningful units, finite offshore wet sample, cap on saved bytes, actual historical day range and number of source frames. These checks validate only **file format and metadata**, not the provenance's independent scientific authenticity; future actual observed files should be traceable to their external source request log.

This micro window is too small to force the complete 732×464 ES3K outer domain, and should **never** be used as real full-boundary forcing. It exists only to exercise a real Copernicus request and the file staging contract without making a computationally costly domain-wide request.

Default (safe and offline):
```bash
python ROMS_Nesting/Data_pre/nesting/japan_sea_glorys_micro_plan.py \
  --plan-json /tmp/JAPAN_SEA_GLORYS_MICRO_NOT_DOWNLOADED.json
```

Separate manual-only workflow:
[`.github/workflows/japan-sea-glorys-tiny-real-sample.yml`](../../.github/workflows/japan-sea-glorys-tiny-real-sample.yml) is **`workflow_dispatch` only**, with boolean `execute_real_tiny_download=false` by default. Only explicit true, and available Copernicus Marine service username/password, install the Marine toolbox and call the existing source downloader on the bounded request. It has an 8-minute explicit download step timeout and a 12-minute job timeout. Saves at most a small 5MiB NetCDF/plan bundle as a 3-day Actions artifact.

## Authentication distinction and non-readiness

**Copernicus CDS `CDSAPI_KEY` (ERA5) is NOT Copernicus Marine GLORYS service credentials.** The official [Copernicus Marine Toolbox credential documentation](https://help.marine.copernicus.eu/en/articles/8185007-copernicus-marine-toolbox-credentials-configuration) specifies separate service `COPERNICUSMARINE_SERVICE_USERNAME` and `COPERNICUSMARINE_SERVICE_PASSWORD`, documented in [the Toolbox CLI reference](https://toolbox-docs.marine.copernicus.eu/en/stable/command-line-interface.html). This PR has **not** set or read Marine secrets; no credential values are stored in the repository. The manual workflow expects those two dedicated GitHub Secrets **only when real remote retrieval is later enabled**. Do not send credentials in chat or source code. The previous user's ERA5 CDS Secret remains untouched.

Official reanalysis product and dataset ID: [Global Ocean Physics Reanalysis](https://data.marine.copernicus.eu/product/GLOBAL_MULTIYEAR_PHY_001_030/services). The 2018 test dates fall within the product's published time coverage.

## Confirmed local-source tests (not real downloaded GLORYS)

- [`test_japan_sea_glorys_micro_plan.py`](../Data_pre/tests/test_japan_sea_glorys_micro_plan.py) tests strict safe source plans, rejection of entire ES3K region, extra time/depth, bad dates/coordinates/variables, missing central ocean values, damaged NetCDF, source units, no remote fetch without a separate Marine login, non-overwrite of existing files, and default CLI operation that produces **only an informational JSON plan**, without downloading anything. Tests use an unmistakably synthetic NetCDF for parser/schema checks, **not a disguised real ocean sample**.
- Automatic short [`japan-sea-ud1k-bry-schema-contract.yml`](../../.github/workflows/japan-sea-ud1k-bry-schema-contract.yml) uploads `japan-sea-glorys-REAL-request-plan-NOT-downloaded` as proof that the planned request is bounded and *has not been executed*.
- All previous 117 light tests for actual archived ES3K source wet support and Option B child donor geometry remain unchanged. No long GEBCO/ROMS run and no full ocean data request was started.

**Status:** `JAPAN_SEA_GLORYS_CASE_CONFIG_REPAIRED` and `BOUNDED_MARINE_MICRO_REQUEST_PLAN_PASS`. **Real GLORYS NetCDF retrieval:** `NOT_RUN` pending separate Marine credentials and explicit opt-in. **Real ES3K ROMS history / physical parent→child transport / UD1K ROMS integration:** `NOT_RUN`. **PR #3:** Draft.
