# Japan Sea ROMS — I2/I3 independent nested-grid preprocessing

**Status: synthetic integration prototype, NOT an accepted Japan Sea ROMS grid or complete preprocessing.** Only `feature/japan-sea-nesting/ROMS_Nesting/` is changed; `main/Data_pre` and its existing single-grid production pipeline remain unchanged.

## Geometry and grids

- `ES3K` is a **rotated WGS84 Lambert-conformal candidate**. Kim et al. (2020) report an approximate geographical envelope, **not sufficient to recover the four corners/rotation**; `ROMS_Nesting/configs/es3k_geometry_template.json` therefore has intentionally **null** coordinates/angle/counts and **cannot run** until a provenance-backed or transparently approximate geometry is explicitly provided.
- `UD1K` is truly **unrotated geographic-axis-aligned** (constant longitude per xi column, constant latitude per eta row, `angle=0`). The existing [candidate config](../configs/ud1k_candidate.json) uses Kim et al.'s approximate envelope only; it is **not a paper-exact final grid**.
- `L3_300m` is blocked pending the user's area/corners. Nothing in this workflow invents it.
- `Data_pre/nesting/bathymetry_grid.py` creates `lon/lat/x/y` at RHO/U/V/PSI, WGS84 `pm/pn/dndx/dmde`, geodesic `angle`, real interpolated `h`, GEBCO+optional GSHHG `mask_rho/u/v/psi`, and metadata **`geometry_status=CANDIDATE_NOT_VALIDATED_FOR_ROMS`**.
- No silent fallback: the copied legacy `create_grid_from_bathymetry.py` **refuses JAPAN_SEA**, because it always writes `angle=0`. Use the new nesting CLI.

## Usage with local source files

First stage a GEBCO 2026 rectilinear NetCDF **including enough extra margin for the *actual rotated grid corners***. The old Japan Sea bbox can be insufficient for rotated candidate corners; the new generator explicitly fails if any target point lies outside the staged subset.

Generate a GSHHG-intersected, **unverified candidate** UD1K grid:

```bash
python ROMS_Nesting/Data_pre/scripts/nesting/create_bathymetry_grid.py \
  --geometry-json ROMS_Nesting/configs/ud1k_candidate.json \
  --bathymetry /workspace/GEBCO/gebco_japan_sea_subset_with_margin.nc \
  --gshhg-base /workspace/GSHHG/gshhg-shp-2/GSHHS_shp \
  --gshhg-resolution h \
  --min-depth-m 10 \
  --output /workspace/japan_sea/UD1K_grid_CANDIDATE.nc \
  --report-json /workspace/japan_sea/UD1K_grid_CANDIDATE_report.json
```

For ES3K, **first** fill an independently reviewed `es3k_geometry.json` with center, `width_points`, `height_points`, `dx_m`, `dy_m`, and signed `angle_deg`, then use the same command with its path. The output remains `CANDIDATE` until comparing the coastline, corners, grid metrics and hydrodynamic ROMS tests. Even a geodesic-quality PASS does not equal scientific equivalence to Kim (2020).

For **synthetic CI only**, `--allow-gebco-only-mask --synthetic-test-only` allows a fixture without a real GSHHG shapefile; its metadata explicitly says the shoreline has not been validated. Formal runs should supply the full GSHHG base path and then perform separate mask cleanup and review.

## Reproducible GitHub-hosted Ubuntu gate (2026-10-14)

- [Run #38523156039 — SUCCESS](https://github.com/RRain001/ROMS/actions/runs/38523156039): WGS84 metric, rotated coordinates, real NetCDF encoding of **synthetic** GEBCO-like elevations; end-to-end candidate ES3K/UD1K outputs. Separate tests exercise the **real GSHHG Shapefile parser with a generated synthetic polygon** and GEBCO-like signed int16 bathymetry. Neither test uses a real Japanese coastline.
- [Run #38523572015 — SUCCESS](https://github.com/RRain001/ROMS/actions/runs/38523572015): apply the pre-existing but now corrected **nesting-only** wet-mask-preserving bathymetry smoother to a rotated NetCDF candidate and check that `lon/lat`, `pm/pn`, `angle`, all four staggered masks remain unchanged. Synthetic example: unsmoothed `rx0=0.742703, rx1=27.576596`; one smoothing iteration yields `rx0=0.145978, rx1=4.341047`, meeting the *test's* preset `rx0<=0.35, rx1<=8` limits. The smoother now **fails closed** if requested slope thresholds cannot be reached and correctly copies scalar NetCDF variables (no compression for 0-D variables).
- Output artifact `i3-synthetic-es3k-ud1k-candidate` contains the synthetic bathymetry fixture, original ES3K/UD1K ROMS candidate NetCDF files, smoothed ES3K candidate and a JSON provenance report. All scientific grids are explicitly `CANDIDATE_NOT_VALIDATED_FOR_ROMS`; synthetic fixture `synthetic_test_only=TRUE`.
- The cited [Kim et al. (2020)](https://doi.org/10.9765/KSCOE.2020.32.6.587) used **KorBathy30s and ETOPO5** for its ES3K bathymetry and HYCOM for open boundary data. Choosing **GEBCO 2026 + GLORYS12V1** here is the user's deliberate scientific adaptation, **not a faithful reproduction of the paper's exact model inputs**. Original grid rotation and corners still require independent verification from publication assets or authors.

**Actual I3 status: NOT_RUN / BLOCKED_BY_REAL_DATA_AND_GEOMETRY.** These CI successes verify executable preprocessing logic and synthetic output artifacts only. No real GEBCO 2026 / GSHHG Japan Sea grid files, no physical ROMS I2 gate, no GLORYS/ERA5/TPXO forcing or ES3K→UD1K run have been generated in this repo.

## Remaining I3 acceptance barriers

1. Real ES3K rotated corners/rotation/actual wet domain versus Kim (2020), with any approximation clearly disclosed.
2. Actual staged GEBCO 2026 and GSHHG 2.3.7, full wet-mask topology/manual corrections. `GEBCO elevation < 0` alone is not adequate coast geometry.
3. Bathymetry slope (`rx0`, later `rx1`) and smoothing **using reviewed wet mask**; the unsmoothed rx0 here is diagnostic, not a PASS.
4. ROMS rotated grid reading, valid sigma layer thickness, 1h/6h/24h actual integrator, OBCs, restarts.
5. GLORYS12V1 initial/boundary, ERA5, TPXO9 real input generation; the legacy copied processors are **not** automatically valid for rotated grids. Vector rotation and C-grid interpolation must be audited.
6. ES3K→UD1K geographic and sigma-space water/flux conservative boundary transport; I5 NOT RUN.
7. 300 m child extent to be supplied by the user (I6 BLOCKED_BY_DOMAIN).

**GitHub Actions** workflow `japan-sea-nesting-i3-grid.yml` generates and uploads **small synthetic candidate .nc files and diagnostic JSON** for both grid orientations; artifact PASS is not a real Japanese Sea grid. Runs only GitHub-hosted Ubuntu.
