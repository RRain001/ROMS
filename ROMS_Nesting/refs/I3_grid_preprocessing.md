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

## Remaining I3 acceptance barriers

1. Real ES3K rotated corners/rotation/actual wet domain versus Kim (2020), with any approximation clearly disclosed.
2. Actual staged GEBCO 2026 and GSHHG 2.3.7, full wet-mask topology/manual corrections. `GEBCO elevation < 0` alone is not adequate coast geometry.
3. Bathymetry slope (`rx0`, later `rx1`) and smoothing **using reviewed wet mask**; the unsmoothed rx0 here is diagnostic, not a PASS.
4. ROMS rotated grid reading, valid sigma layer thickness, 1h/6h/24h actual integrator, OBCs, restarts.
5. GLORYS12V1 initial/boundary, ERA5, TPXO9 real input generation; the legacy copied processors are **not** automatically valid for rotated grids. Vector rotation and C-grid interpolation must be audited.
6. ES3K→UD1K geographic and sigma-space water/flux conservative boundary transport; I5 NOT RUN.
7. 300 m child extent to be supplied by the user (I6 BLOCKED_BY_DOMAIN).

**GitHub Actions** workflow `japan-sea-nesting-i3-grid.yml` generates and uploads **small synthetic candidate .nc files and diagnostic JSON** for both grid orientations; artifact PASS is not a real Japanese Sea grid. Runs only GitHub-hosted Ubuntu.
