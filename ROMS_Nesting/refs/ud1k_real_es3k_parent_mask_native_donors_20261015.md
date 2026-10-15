# Real ES3K parent wet/native-U/V face independent audit for candidate-B UD1K stencils

Date: 2026-10-15. [Draft PR #3](https://github.com/RRain001/ROMS/pull/3), branch `codex/es3k-i3-wet-domain-audit-20261014`, base `feature/japan-sea-nesting`.

**Result: actual source mask donor admission PASS**, **physical one-way nesting still HOLD**.

## Important distinction from previous tests

The earlier end-to-end test ran the actual Option B UD1K 290×438 C-grid and the original coastline-audited 1,011 RHO / 1,005 U / 1,010 V independent donor mappings through physical-depth/CF time/rotation/28-variable BRY production-format **synthetic-only fixture**. Its parent ES3K was deliberately **all wet** and therefore could not independently establish whether the *original* actual GEBCO/GSHHG ES3K parent grid was truly wet at every donor, with actual usable native U **and** V faces.

This stage independently checks that missing physical prerequisite against **the archived authentic real parent source grid**, not the synthetic parent:

- Actual archive: [native ES3K and UD1K I3 Actions #38680030642](https://github.com/RRain001/ROMS/actions/runs/38680030642), `es3k-real-public-gebco2026-native15s-gshhg237` (~157 MB compressed) with `ES3K_JAPAN_SEA_CORE_SMOOTHED_I3_CANDIDATE.nc`. The historical artifact is reused, **not regenerated** using GEBCO/GSHHG downloads.
- Original independently generated child/grid source material: same run's `ud1k-27-wet-boundary-mapping-small-json` (~2.3 MB), `UD1K_CONNECTED_CORE_SHORELINE_CLEAR_COMPARISON_CANDIDATE.nc`, `ud1k_core_shoreline_clear_1011_rho_map.json`, and `ud1k_core_shoreline_clear_native_uv_boundary_map.json`.
- Auditor implementation: [`ud1k_real_es3k_parent_mask_audit.py`](../Data_pre/nesting/ud1k_real_es3k_parent_mask_audit.py) accepts these existing NetCDF/JSON inputs **read-only**; never alters the frozen source, approved original grids, Option B comparison candidate, donor records or main branch.

## Actual checks performed

1. First pass the unchanged child Option B **strict real-grid and certified-manifest contract**: 290×438 RHO, 96,104 wet child RHO, independently mapped **RHO=1011/U=1005/V=1010** perimeter receivers, 1,012 wet child normal faces (south V 382; north V 364; west U 0; east U 266), weight normalization and GSHHG visibility flags.
2. Open the **original real ES3K smoothed I3 parent** NetCDF and independently re-read its native binary `mask_rho` (expected 732×464), `mask_u` (732×463), `mask_v` (731×464). Require source native masks to be identical to the actual wet-neighbor C-grid definitions, not just to the original audit's claims.
3. Validate finite real wet-parent `h`, `angle`, `lon_rho`, `lat_rho` and strictly positive actual wet `h` (no fictitious source depth accepted).
4. For **every single donor reference in all three original JSON manifests**, including zero-weight listed donors, require actual parent `mask_rho[j,i]=1`. For every U or V receiver mapping donor, independently require both at least one genuinely wet **native parent U face** adjacent to the donor RHO and at least one genuinely wet **native parent V face**, as well as matching `mask_u/mask_v` values. Refuse dry donors even when the previously certified JSON flag says `native_parent_U_and_V_wet_face_support=true`.
5. Report per-kind donor-reference counts, unique source nodes by kind, all-source unique source count, real parent depth min/max and a deterministic SHA256 of sorted original parent RHO (eta,xi) donor indices for reproducibility. No hydrodynamic source `his.nc` is read.

## Confirmed Actions evidence

[**GitHub Actions #38701634361**](https://github.com/RRain001/ROMS/actions/runs/38701634361): independent real source mask job **SUCCESS**, and separate fast unit suite **SUCCESS**.

Actual source-mask job log:

```
REAL_ES3K_PARENT_MASK_OPTION_B_NATIVE_SOURCE_DONORS {
  "actual_parent_history":"NOT_AVAILABLE",
  "child_receiver_counts":{"rho":1011,"u":1005,"v":1010},
  "real_parent_unique_donors":909,
  "result":"REAL_ES3K_PARENT_MASK_ALL_OPTIONB_RHO_U_V_DONORS_PASS"
}
REAL_ES3K_PARENT_WET_NATIVE_DONOR_INDEPENDENT_PASS
```

**909 distinct original ES3K real parent RHO donor nodes**, shared across the independently mapped 1,011/1,005/1,010 child receivers, now have actual source RHO wet/native U+V support verified **from the authentic real parent grid**. The numerical evidence is stored in the small 30-day artifact `real-ES3K-parent-mask-optionb-donor-independent-audit` from this run (artifact ID **11956352862**; ~990 bytes zipped), with counts and original-source donor fingerprint.

Also **8 new small fail-closed unit tests** verify dry real source RHO even with claimed certification, absent U neighborhood, absent V neighborhood, invalid nonbinary mask, mismatch to the RHO neighbor wet C-grid definition, nonpositive real parent depth, zero-weight dry donor and successful correct support. The fast job now totals **117/117 PASS** (109 previous + 8 new).

This 157MB read-only archival audit was executed **once**. Its workflow `.github/workflows/japan-sea-ud1k-bry-schema-contract.yml` has been restored to **`workflow_dispatch` only** for the archival parent mask job after PASS; routine PR tests remain small/offline. No ocean reanalysis downloads, no new GEBCO processing, no model integration, no production time selection.

## What this does NOT establish

- **GSHHG segment/intersection checks** were certified in the original previous full-native I3 construction and are trusted in the original JSON; this audit does not recompute raw shoreline line intersections. That is separate from the newly independent parent real wet/native U+V mask confirmation.
- The ES3K *actual hydrodynamic* `zeta/temp/salt/u/v/ubar/vbar` source time-dependent `his.nc` has **NOT** been produced or checked. The earlier all-wet history-to-`bry.nc` integration remains an explicitly synthetic test of the numerical code, not real physics.
- Parent-to-child **normal transport equality**, mass balance including `zeta` storage, tides, density gradients, forcing/seasonal climatology, full valid ROMS runtime input and actual ES3K/UD1K model simulation remain **NOT_RUN**.
- Option B remains a **comparison-only candidate**, not promoted to the officially accepted active UD1K grid; original frozen geometry, science masks, outer ES3K configuration, `main` and prior top-level no-nesting source code remain unchanged. Draft PR #3 is not ready for merge on hydrodynamic readiness grounds.

**Milestone:** REAL_ES3K_PARENT_RHO_U_V_DONOR_MASK_ADMISSION=PASS; PHYSICAL_ONE_WAY_NESTING_READY=FALSE.
