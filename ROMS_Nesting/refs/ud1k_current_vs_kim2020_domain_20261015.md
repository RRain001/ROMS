# UD1K boundary provenance and Kim 2020 domain comparison

**Frozen 2026-10-15. Do not replace the active user scope without explicit authorization.**

## A. Baseline: current user-approved UD1K (2026-10-14)

- Canonical active config: [ud1k_candidate.json](../configs/ud1k_candidate.json), original blob SHA `8323d52d14a6b4a2743471829050ab68457f80f3`.
- Exact frozen byte-for-byte copy: [ud1k_user_20261014_frozen.json](../configs/ud1k_user_20261014_frozen.json) (same blob SHA).
- User-input labels: **W 128°21′55.9″ E, S 34°57′55.7″ N, E 132°24′42.6″ E, N 37°38′29.0″ N**.
- Mathematical 1/108° grid anchored W/S; `[eta_rho,xi_rho] = [290,438]` (289 eta / 437 xi intervals). Realized **W 128.36552777777777° E, E 132.41182407407408° E, S 34.965472222222225° N, N 37.64139814814815° N**. Realized E/N differ by 0.03333″ from rounded DMS.
- Real-data baseline: GEBCO 2026 native 15″ + GSHHG 2.3.7 L1 high, same candidate ES3K parent conformal grid retaining dominant contiguous Japan-Sea wet component. [GitHub Actions #38654151016](https://github.com/RRain001/ROMS/actions/runs/38654151016) finished SUCCESS on full-quad static audit; RHO wet boundary **1,017**, all-wet quad **990**, unresolved **27** (south **21**, north **2**, west **0**, east **4**).
- Baseline's nearest-wet-cell preflight PASS is not ocean dynamics acceptance; no sigma, velocity rotation, dry coastal fallback or mass-conserving `bry.nc` validation.

## B. Published trial: Kim et al. (2020), Table 1

- Reference: D. Kim et al., *Simulation of the Ocean Circulation Around Ulleungdo and Dokdo Using a Numerical Model of High-Resolution Nested Grid*, *Journal of Korean Society of Coastal and Ocean Engineers* **32**(6):587–601 (2020), DOI [10.9765/KSCOE.2020.32.6.587](https://doi.org/10.9765/KSCOE.2020.32.6.587), paper PDF [jkscoe-32-6-587.pdf](https://jkscoe.or.kr/upload/pdf/jkscoe-32-6-587.pdf), **Table 1, printed page 589**.
- Paper UD1K: **W 127.5° E, E 134.0° E, S 35.5° N, N 39.0° N**, grid step **1/108°**. A straightforward inclusive coordinate endpoint realization yields **379 × 703 RHO**. The paper lists *boundaries and nominal resolution*, not these explicit RHO integer counts, so shape is our derived implementation, not a number claimed by the paper.
- Independent trial config: [ud1k_kim2020_table1_trial.json](../configs/ud1k_kim2020_table1_trial.json). **Do not overwrite** baseline.
- Published paper used an ES3K configuration and hydrography distinct from this candidate, so even exact UD1K lat/lon bounds here are *a controlled grid geometry experiment*, not an exact replication of their historical ROMS experiment.

## C. Controlled test

1. Preserve existing candidate ES3K 3km full geometry, connected sea-water component, smoothed bathymetry, and GEBCO/GSHHG data, including parent mask.
2. Build the current and paper trial UD1K with the **same** real GEBCO 2026 native 15″ and GSHHG 2.3.7 high Level 1 inputs; check the expected distinct RHO dimensions and actual corners.
3. Compare only true wet receiver **boundary RHO** points to the **exact same parent** using `validate_nesting_geometries.check_pair`: inside buffered parent, nearest parent wet and exhaustive four-wet-vertex quadrilateral candidates, side counts and representative coordinates.
4. Run via [native 15″ CI workflow](../../.github/workflows/japan-sea-es3k-online-native.yml) using [compare_ud1k_domains.py](../Data_pre/scripts/nesting/compare_ud1k_domains.py) and upload JSON file `ud1k_current_vs_kim2020_table1_real_comparison.json`.
5. Result may be **worse** than the current domain; do not assume the paper boundaries resolve the 27-gap issue. A completely all-wet stencil does not prove no coastline crossings. No native ROMS physics is run.

## D. Verified outcome: Native 15″ real-data comparison (2026-10-15)

**GitHub-hosted Ubuntu success:** [Actions #38660448988](https://github.com/RRain001/ROMS/actions/runs/38660448988), job `116180176178`; in-run comparison printed `PAPER_BOUNDARY_COMPARISON`. The full point-level static comparison report is permanently checked in at [ud1k_kim2020_20261015_real_comparison_evidence.json](ud1k_kim2020_20261015_real_comparison_evidence.json); original full GEBCO/GSHHG candidate grids and report were also uploaded to the successful run's 14-day artifact. Both child grids use identical GEBCO 2026 native 15″ and GSHHG v2.3.7 high L1 shoreline data and exactly the same connected ES3K parent candidate.

| Metric | Frozen user bounds | Kim 2020 Table 1 bounds |
| --- | ---: | ---: |
| Domain lon E / lat N | 128.365528–132.411824 E; 34.965472–37.641398 N | 127.5–134.0 E; 35.5–39.0 N |
| RHO shape eta×xi | 290×438 | 379×703 |
| RHO wet points | **96,127** | **201,639** |
| RHO land points | **30,893** | **64,798** |
| Wet boundary RHO points | **1,017** | **1,426** |
| Valid all-wet ES3K RHO quadrilaterals | **990** | **1,406** |
| Uncovered child wet RHO points | **27** | **20** |
| Fully supported wet boundary rate | **97.3451%** | **98.5975%** |
| Uncovered south/north/west/east | **21 / 2 / 0 / 4** | **13 / 5 / 0 / 2** |
| Buffered parent footprint + nearest parent-wet preflight | `PASS_PRELIMINARY_ONLY` | `PASS_PRELIMINARY_ONLY` |
| Max nearest parent wet (m) | 4427.17 | 4042.96 |
| Min buffered-parent ring clearance (m) | 140931.97 | 132114.56 |
| ROMS water dynamics / vector & sigma / tracer flux | **NOT_RUN** | **NOT_RUN** |

**Interpretation:** the reference paper bounds *reduce* static missing quadrilaterals **27→20**, and the unsupported fraction **2.6549%→1.4025%**, despite a larger wet boundary count. But the coastal interpolation gap is **not eliminated**. This is not a paper method validation or a demonstration that either candidate's physical boundary conditions are correct. The results depend on the real GEBCO/GSHHG mask and the selected approximate ES3K geometry; Kim et al.'s original bathymetry and model grid are not identical to those used here.

**Important geographic evidence:** among the **13 paper-south** uncovered points at **35.5°N**, three lie at **129.388889–129.444444°E**, seven at **132.740741–132.814815°E**, two at **133.268519–133.277778°E**, and one at **133.453704°E**. The **5 paper-north** points are at **39°N, 127.861111–127.898148°E**; the **2 paper-east** points are at **134°E, 35.537037–35.546296°N**. Both the count and all zero-based `eta,xi`/lon/lat coordinates are in the JSON evidence. Remarkably, Kim et al. (2020) separately discuss coastal bathymetry/land-versus-sea discrepancies along their southern **35.5°N** boundary, including **132.7–134°E**, in the paper near Fig. 6 (print page 592–593). That supports further coastal-source interrogation, *not* forcing wet points to land.

**Decision:** Keep the current user UD1K `ud1k_candidate.json` intact and treat the paper trial as a comparison only. Do not silently promote it on the basis of one static metric; assess the physics/research extent differences and the 20 coastal stencil points (plus RHO/U/V staggered checks) before deciding whether to select or adjust a domain.

