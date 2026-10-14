# Japan Sea ROMS — I2/I3 independent nested-grid preprocessing

**Status: synthetic integration prototype, NOT an accepted Japan Sea ROMS grid or complete preprocessing.** Only `feature/japan-sea-nesting/ROMS_Nesting/` is changed; `main/Data_pre` and its existing single-grid production pipeline remain unchanged.

## 2026-10-14: Angular resolution adopted and Fig. 1(a) rotation digitization

**Decision:** The final scientific ES3K / UD1K / L3 grids shall use **1/36°, 1/108°, 1/324° nominal angular resolution**, respectively, following [Kim et al. (2020)](https://doi.org/10.9765/KSCOE.2020.32.6.587), rather than identical `dx=dy=3000/1000/300 m` everywhere. The 41 vertical layers, user-selected one-way hydrodynamics, offline ROMS HTO tracer, GEBCO/GSHHG/GLORYS12V1/ERA5/TPXO sources remain unchanged.

**2026-10-14 override:** The user provided the authoritative four ES3K vertices (latitude north, longitude east): W=(37.821077,121.900000), S=(30.800000,131.471973), N=(52.000000,141.327943), E=(45.616255,150.400000); perimeter W→N→E→S→W. These inputs supersede all earlier paper-image corner estimates. The new W=121.9°E now agrees with Kim (2020) Table 1's reported westernmost longitude. The W-to-N geodesic edge orientation at W is ~51.36° CCW from due east, NOT a uniform `angle` for the entire domain. Four corners are confirmed as project input but the full curvilinear ROMS orthogonal grid, map projection, strict 1/36° mapping, wet mask and dynamical quality remain **NOT RUN**.

**ES3K I2 geometry prototype (2026-10-14):** The new `Data_pre/nesting/es3k_corners.py` generates a **four-corner-constrained** bilinear transfinite grid in a local WGS84 AEQD chart, preserving all four user vertices exactly. `scripts/nesting/render_es3k_corner_grid.py` exports a coarse SVG/PNG geometry diagnostic and JSON with per-cell WGS84 angle, orthogonality, metric spacing, full-resolution estimated dimensions, and boundary fidelity. The 1/36-degree spacing is a **local metric equivalent**, NOT strict equal angular spacing in a documented rotated coordinate system. The current candidate is a pilot: a production geometry failing the >1-degree orthogonality threshold is rejected by `bathymetry_grid.py`. No real GEBCO/GSHHG or hydrodynamic ROMS integration is implied.

**Critical software distinction:** `ROMS_Nesting/Data_pre/nesting/bathymetry_grid.py` currently builds a **METRIC** `rotated_lcc` grid and a **METRIC-SPACING** `axis_aligned_lonlat` candidate; passing its tests does **not** fulfill the angular-resolution decision. In particular, a longitude increment of 1/36° spans a latitude-dependent physical distance and cannot be represented by constant 3000 m `dx/dy` over this 20-degree latitude range. The new target requires implementing and testing a separate genuinely angular grid construction mode (and an explicit rotated-coordinate convention for ES3K) before producing accepted scientific grids. Existing synthetic CI, output artifacts and optional 1000 m UD1K candidate are **legacy synthetic evidence only**.

User input is **not required** for a reproducible approximate geometry candidate. Exact paper reproduction would require original `grid.nc`, author-provided grid-generation parameters or original grid scripts/metadata; if this is unavailable, Figure 1 digitization must carry explicit uncertainty. The third-domain placement remains user-defined unless they later elect the paper's reference envelope.

## 2026-10-14: user-defined southern Korean coast L3 square

**Frozen anchor points:** A=(35.545437°N,129.407703°E), B=(35.974688°N,129.522766°E). Treat AB as the L3 coastal side and construct the square to the **eastern offshore side (right of A→B)**, not into Korean land. WGS84 local AEQD square corners: C=(35.879499°N,130.050131°E), D=(35.450754°N,129.932388°E); AB=48.750849 km, planar area 2376.645 km², bearing A→B 12.291° clockwise from north. A/B are exact input anchors, C/D are derived candidate corners, not external observations.

The user selects Kim et al. (2020)'s nominal `1/36° / 1/108° / 1/324°`. The L3 square is a **physical square**, whose nominal angular **local metric equivalent** sampling yields candidate `rho_shape=(143,176)`, xi about 279 m / eta about 343 m; it does **NOT** make every rotated cell an exactly constant angular 1/324° longitude/latitude step. Such an exact angular rule requires an independently declared rotated spherical-coordinate definition and can conflict with a physically square prescribed AB/CD perimeter. The candidate metadata must disclose `ANGULAR_EQUIVALENT_LOCAL_METRIC_NOT_CONSTANT_DDEG`; no exact-Kim reproduction claim.

The original UD1K reference south boundary 35.5°N **excludes** L3's D at 35.450754°N by ~5.5 km. `configs/ud1k_candidate.json` adopts the **user-approved** southward extent of approximately 35.35°N; its **new geographic exact-1/108-degree generator** anchors the north at 39°N and snaps the actual south to 35.351852°N. The **geometric southward extension is approved**; scientific/physical acceptance remains **pending** parent-child wet-boundary interpolation and GSHHG/GEBCO shoreline validation. A/B may be coastal/terrestrial vertices; do not falsely assume all L3 boundary cells are wet/open ocean.

Source of truth: `ROMS_Nesting/configs/l3_coastal_square_candidate.json` and `Data_pre/nesting/l3_square.py`. L3 research domain now defined; **I6 geometry status candidate**, `BLOCKED_BY_DOMAIN` lifted, real `grid.nc`/forcing/hydrodynamics/cross-grid Bq conservation still `NOT_RUN`.

## Geometry and grids

- `ES3K` now has precise **user-supplied corner constraints**, stored in `configs/es3k_user_corners.json`. The previous Fig.1 corner estimates are retired. `es3k_geometry_template.json` still has no verified full-map grid/point count or angle, and the **exact** 1/36° curvilinear generator is NOT IMPLEMENTED (transfinite geometry pilot only).
- `UD1K` is truly **unrotated geographic-axis-aligned** (constant longitude per xi column, constant latitude per eta row, `angle=0`). The existing [candidate config](../configs/ud1k_candidate.json) uses Kim et al.'s approximate envelope only; it is **not a paper-exact final grid**.
- `L3_300m` now has two exact user-given AB vertices and offshore WGS84-derived C/D. Geographic square candidate only; **real wet grid and parent validation pending**.
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

For ES3K, respect the immutable four-corner inputs and develop the corner-constrained orthogonal 1/36° grid generator. Do NOT use the old metric `rotated_lcc` prototype as an author-equivalent result. The target bathymetry grid remains CANDIDATE pending GEBCO/GSHHG and ROMS integration.

For **synthetic CI only**, `--allow-gebco-only-mask --synthetic-test-only` allows a fixture without a real GSHHG shapefile; its metadata explicitly says the shoreline has not been validated. Formal runs should supply the full GSHHG base path and then perform separate mask cleanup and review.

## Official GEBCO_2026 NetCDF schema and safe staging

**ES3K staging minimum:** since the user's ES3K westernmost boundary is **121.900000°E**, the previous example `--west 121.5 --margin 0.25` would miss it and must **not** be used. The current approximate example starts `--west 120.5`; the final source window must be checked against every RHO node of the eventual curvilinear mesh, not merely its four corners.\n\nThe official [CEDA GEBCO_2026 NetCDF catalogue](https://data.ceda.ac.uk/bodc/gebco/global/gebco_2026/ice_surface_elevation/netcdf) lists the scientific variables `longitude`, `latitude`, **`height_above_mean_sea_level`**, and `crs`. Earlier copied staging code recognized only `z/elevation/Band1`; that would fail on the official file. The independent candidate reader and `stage_and_subset_bathymetry.py` now handle the CEDA source alias, validate dimensions and perform **bounded spatial-window extraction**. The staging script no longer calls unrestricted `ZipExtFile.read()` on the 7 GB NetCDF member; it uses an 8 MiB streaming copy and an atomic `.part` extraction target. Adequate on-disk space is still required for both compressed and extracted inputs.

When using the local official GEBCO ZIP or already extracted NetCDF:

```sh
python ROMS_Nesting/Data_pre/scripts/bathymetry/stage_and_subset_bathymetry.py \
  --case-name JAPAN_SEA \
  --global-file /workspace/GEBCO/GEBCO_2026.nc \
  --zip-file /workspace/GEBCO/GEBCO_2026.zip \
  --west 120.5 --east 150.8 --south 30.4 --north 52.4 --margin 0.25 \
  --max-source-cells 50000000 \
  --work-dir /workspace/JAPAN_SEA/GEBCO \
  --output gebco_2026_japan_sea_CANDIDATE.nc
```

**Those geographic bounds are an explicitly approximate initial download/staging envelope, not the final ES3K grid corners.** Before using the subset for the actual rotated ES3K, generate the candidate geometry and compare its full RHO-node extrema against the staged file; the grid builder rejects missing coverage. The streaming fix is not a statement that GitHub-hosted runners currently possess the 4 GB GEBCO ZIP or actual GSHHG shapes. `test_real_gebco_contract.py` uses a **generated synthetic** NetCDF with the genuine CEDA variable names and checks both the direct path and the staged path.

## GEBCO 2026 large-file contract and reproducibility

The official [GEBCO_2026 grid](https://www.gebco.net/data-products-gridded-bathymetry-data/gebco2026-grid) stores roughly 3.73 **billion** 15-arcsecond elevations as an approximately 7 GB uncompressed NetCDF grid (2-byte signed integer elevation). A naive `elevation[:]` causes uncontrolled memory consumption. The nesting candidate generator now reads only 1-D longitude/latitude axes from the full file, computes an interpolation-halo window from **actual rotated grid corners and all RHO points**, and reads just that 2-D `elevation[latitude_slice,longitude_slice]` section. This supports globally stored or official [user-selected GEBCO subsets](https://download.gebco.net/), reversed coordinate axes, and either `(lat,lon)` or `(lon,lat)` source variable order. The output includes `bathymetry_source_window` (file indices, source grid, extracted shape, sign/order) and preserves the file's provenance.

`--max-source-cells 50000000` is a **hard extracted-window limit**, not a claim of fixed peak process memory. Increase only after estimating per-run memory; for a full ES3K footprint at 15 arcseconds the subset itself may occupy hundreds of MB before interpolation work arrays. A too-small source bbox or larger-than-allowed window must FAIL rather than extrapolate, skip cells, or silently downsample. Longitudes crossing the antimeridian are not yet supported.

**Use a real source file; CI synthetic products are not inputs for publications:**

```bash
python ROMS_Nesting/Data_pre/scripts/nesting/create_bathymetry_grid.py \
  --geometry-json /path/to/verified_or_declared_approx_es3k_geometry.json \
  --bathymetry /data/GEBCO_2026.nc \
  --gshhg-base /data/GSHHG/GSHHS_shp \
  --gshhg-resolution h \
  --max-source-cells 50000000 \
  --output /data/JAPAN_SEA/ES3K_candidate.nc \
  --report-json /data/JAPAN_SEA/ES3K_window_report.json
```

The official GEBCO source requires attribution: GEBCO Bathymetric Compilation Group 2026, GEBCO_2026 Grid, DOI [10.5285/4f68d5c7-45eb-f999-e063-7086abc036fa](https://doi.org/10.5285/4f68d5c7-45eb-f999-e063-7086abc036fa). Note that 15-arcsecond bathymetry resolution is **source sampling**, distinct from ROMS ES3K/UD1K grid spacing.

## Published Kim et al. (2020) geometry versus this new experiment

The [open-access original paper, Table 1](https://www.jkscoe.or.kr/journal/view.php?number=358), specifies **angular** nominal resolutions, not WGS84 uniform distance: ES3K `1/36 degree` (~3 km), UD1K `1/108 degree` (~1 km), and UD300m `1/324 degree` (~300 m). Its printed *extrema*, not necessarily the four vertices of a rotated domain, are:

| Grid | Published longitude interval | Published latitude interval | Vertical layers |
|---|---|---|---|
| ES3K | 121.9–150.4 E | 30.8–52.0 N | 41 |
| UD1K | 127.5–134.0 E | 35.5–39.0 N | 41 |
| UD300m | 130.39–132.25 E | 36.85–37.89 N | 41 |

**Scientific distinction:** a `1/36°` geographic grid is not equivalent to a uniform `dx=dy=3000 m` projected Lambert-conformal rotated grid at all latitudes. The currently requested ES3K rotated `dx=dy=3000 m` candidate is a separately declared project grid, **not an exact reconstruction of Kim's mesh**. Do not report paper-equivalent grid spacing or rotation before recovering author/source grid data. The UD300m range is a **published reference region**, not automatic authorization to replace the user's still-undecided custom L3 area. A comparability study could later construct both angular-reference and projected candidates, but the current branch intentionally retains only the user-selected nested scheme.

## ES3K → UD1K nesting geometry preflight (I3/I5 prerequisite)

When both candidate ROMS grids are present, verify that the **entire UD1K curvilinear perimeter** is strictly enclosed by the ES3K wet-domain geometric footprint with a configurable number of parent RHO grid cells of buffer. The implementation projects both rings into the same WGS84 azimuthal-equidistant local map and evaluates **actual grid-edge polygons** using Shapely; bounding boxes are not sufficient because ES3K is rotated.

```sh
python ROMS_Nesting/Data_pre/scripts/nesting/validate_nesting_geometries.py \
  --parent-grid /data/JAPAN_SEA/ES3K_grid_CANDIDATE.nc \
  --child-grid /data/JAPAN_SEA/UD1K_grid_CANDIDATE.nc \
  --parent-margin-cells 2 --wet-search-cells 2.0 \
  --output-json /data/JAPAN_SEA/ES3K_UD1K_preflight.json
```

The checker records the geometric interior-ring gap in metres, parent/child nominal cell ratio, and whether each **wet child boundary RHO point** is near any parent wet RHO cell. It rejects children outside the buffered parent polygon and cases where a fine-grid wet boundary has no nearby parent wet cell. This does **not** prove hydrodynamic nesting: coast-aligned wet masks, real interpolation stencil availability, open boundaries, vertical remapping, conservative barotropic fluxes, tracer return/reentry and actual water continuity remain independent gates.

Synthetic CI artifacts now use an actually *contained* small UD1K rectangle within the rotated ES3K synthetic parent. The larger stand-alone UD1K candidate envelope `configs/ud1k_candidate.json` is unchanged and **must** be checked again against real ES3K geography.

## Reproducible GitHub-hosted Ubuntu gate (2026-10-14)

- [Run #38523156039 — SUCCESS](https://github.com/RRain001/ROMS/actions/runs/38523156039): WGS84 metric, rotated coordinates, real NetCDF encoding of **synthetic** GEBCO-like elevations; end-to-end candidate ES3K/UD1K outputs. Separate tests exercise the **real GSHHG Shapefile parser with a generated synthetic polygon** and GEBCO-like signed int16 bathymetry. Neither test uses a real Japanese coastline.
- [Run #38523572015 — SUCCESS](https://github.com/RRain001/ROMS/actions/runs/38523572015): apply the pre-existing but now corrected **nesting-only** wet-mask-preserving bathymetry smoother to a rotated NetCDF candidate and check that `lon/lat`, `pm/pn`, `angle`, all four staggered masks remain unchanged. Synthetic example: unsmoothed `rx0=0.742703, rx1=27.576596`; one smoothing iteration yields `rx0=0.145978, rx1=4.341047`, meeting the *test's* preset `rx0<=0.35, rx1<=8` limits. The smoother now **fails closed** if requested slope thresholds cannot be reached and correctly copies scalar NetCDF variables (no compression for 0-D variables).
- Output artifact `i3-synthetic-es3k-ud1k-candidate` contains the synthetic bathymetry fixture, original ES3K/UD1K ROMS candidate NetCDF files, smoothed ES3K candidate and a JSON provenance report. All scientific grids are explicitly `CANDIDATE_NOT_VALIDATED_FOR_ROMS`; synthetic fixture `synthetic_test_only=TRUE`.
- The cited [Kim et al. (2020)](https://doi.org/10.9765/KSCOE.2020.32.6.587) used **KorBathy30s and ETOPO5** for its ES3K bathymetry and HYCOM for open boundary data. Choosing **GEBCO 2026 + GLORYS12V1** here is the user's deliberate scientific adaptation, **not a faithful reproduction of the paper's exact model inputs**. Original grid rotation and corners still require independent verification from publication assets or authors.

**Actual I3 status: NOT_RUN / BLOCKED_BY_REAL_DATA_AND_GEOMETRY.** These CI successes verify executable preprocessing logic and synthetic output artifacts only. No real GEBCO 2026 / GSHHG Japan Sea grid files, no physical ROMS I2 gate, no GLORYS/ERA5/TPXO forcing or ES3K→UD1K run have been generated in this repo.

## GLORYS12V1 initial/boundary sigma-depth correctness (I4 preflight)

The copied single-grid GLORYS preprocessing computes `sigma_depths(h,vertical)` with **zero sea-surface height**, which is inaccurate when the real GLORYS `zos` is nonzero or time-dependent. In ROMS Vtransform=2, both RHO-depth and interface thickness depend on local `h+zeta`. The **isolated nesting copy only** now computes interpolated `zeta` first, validates the wet water column, recomputes `z_r/Hz` with the selected initial timestamp, and then interpolates GLORYS `temp/salt/u/v` vertically and depth-averages staggered `ubar/vbar`.

For the open boundaries, sigma geometry is recomputed **for each GLORYS source time and two-cell RHO boundary strip**, rather than once at `zeta=0` for the entire 3D ES3K domain. This avoids allocating full-domain `N*ny*nx` `z_r/Hz` merely to generate four narrow boundary strips. Geometry and wind/current vector rotation are separate concerns; east/north GLORYS velocities are explicitly transformed using the ROMS `angle` field.

The new `test_glorys_dynamic_sigma.py` uses an explicitly **synthetic**, time-changing and nonzero free surface, an analytic depth-dependent temperature field, and a rotated ES3K candidate grid; it tests the real copied preprocessing routines for all four boundary edges as well as a complete synthetic initial-condition NetCDF output. Scientific I4 remains **NOT RUN** until actual CMEMS source, approved coastline/geometry, initial+boundary time continuity and a ROMS integrator smoke.

## I4 further input-I/O efficiency fix

The independent GLORYS source accessor `roms_preprocessing_utils.read_dimensional_variable()` previously loaded `var[:]` **for every time record** before applying `np.take(...,time_index)`. The copied nesting implementation now applies the time integer index directly to the NetCDF variable **before** loading data. This keeps initial-condition/boundary records bounded to **one source timestamp** in memory, regardless of whether the source time dimension is first or last; it does not yet subset the entire *horizontal* CMEMS source extent. The new test `test_glorys_bounded_time.py` uses recording-variable stubs that deliberately reject any full-time `var[:]` read; it verifies 3D and 2D fields, swapped axis order, missing values, and invalid time indexing. This is a performance/interface gate only, not proof of real GLORYS compatibility or a physical ROMS run.

## Remaining I3 acceptance barriers

1. ES3K four user-given corners are now accepted; complete corner-constrained curve-fitting, true geographic rotation/angle field, 1/36° mapping, wet bathymetry and model-run acceptance.
2. Actual staged GEBCO 2026 and GSHHG 2.3.7, full wet-mask topology/manual corrections. `GEBCO elevation < 0` alone is not adequate coast geometry.
3. Bathymetry slope (`rx0`, later `rx1`) and smoothing **using reviewed wet mask**; the unsmoothed rx0 here is diagnostic, not a PASS.
4. ROMS rotated grid reading, valid sigma layer thickness, 1h/6h/24h actual integrator, OBCs, restarts.
5. GLORYS12V1 initial/boundary, ERA5, TPXO9 real input generation; the legacy copied processors are **not** automatically valid for rotated grids. Vector rotation and C-grid interpolation must be audited.
6. ES3K→UD1K geographic and sigma-space water/flux conservative boundary transport; I5 NOT RUN.
7. 300 m child extent to be supplied by the user (I6 BLOCKED_BY_DOMAIN).

**GitHub Actions** workflow `japan-sea-nesting-i3-grid.yml` generates and uploads **small synthetic candidate .nc files and diagnostic JSON** for both grid orientations; artifact PASS is not a real Japanese Sea grid. Runs only GitHub-hosted Ubuntu.
