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

**Completion:** source configuration frozen, trial source independent, comparison implemented; latest experimental outcome must be read from the actual CI job log/artifact, not inferred from the paper or historical run.
