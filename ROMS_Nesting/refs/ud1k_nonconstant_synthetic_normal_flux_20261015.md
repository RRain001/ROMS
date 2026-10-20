# UD1K source-driven nonconstant C-grid interpolation / outward 2D–3D flux audit

**Date:** 2026-10-15. **Status:** `NONCONSTANT_SYNTHETIC_CHILD_NATIVE_FACE_NUMERICAL_PASS`; actual ES3K ROMS history and operational UD1K boundary are **NOT_RUN**. Draft [PR #3](https://github.com/RRain001/ROMS/pull/3); frozen source/child grids and original non-nested ROMS code unchanged.

## Scope and provenance

The previous ES3K→UD1K history-based boundary preview passed simple constant-field and linear-time source fixtures, but did not explicitly integrate outward wet native normal-face transport across each of the four physical sides. This incremental micro-stage retains the **small, synthetic-only** NetCDF fixtures; it does NOT run ocean hydrodynamics, retrieve Copernicus/ERA5 data or create accepted physical `bry.nc`.

The implementation and tests are:
- [`ud1k_boundary_normal_flux_preview.py`](../Data_pre/nesting/ud1k_boundary_normal_flux_preview.py): independent **2D/3D normal-face** section accounting from actual wet child staggered U/V, local C-grid metrics and depth `h+zeta`.
- [`ud1k_boundary_remap_preview.py`](../Data_pre/nesting/ud1k_boundary_remap_preview.py): optional integration of the numerical flux accounting when both child `pm` and `pn` are present; reports explicit **`NOT_RUN_MISSING_CHILD_PM_PN_GRID_METRICS`** otherwise.
- [`test_ud1k_nonconstant_boundary_flux_preview.py`](../Data_pre/tests/test_ud1k_nonconstant_boundary_flux_preview.py): ten small ROMS NetCDF tests; the source parent has **3 sigma layers**, target child **4 sigma layers**, and child grid is a rotated **6×7 RHO** synthetic grid. Neither source geometry nor donor maps are to be treated as certified GSHHG results: GSHHG-compliance flags are fixture values.

## Analytical nonconstant signal and remapping oracle

The synthetic history has independent sea surface frames at 0 seconds `zeta=0.4m` and 3600 seconds `zeta=1.6m`. The independent 1800-second expected state has `zeta=1.0m`. Ocean temperature, salinity and native parent staggered velocities are functions of physical depth `z` (positive upward) and time `t`:

- `temp(z,t)=16 + 0.013 z + 1e−4 t`
- `salt(z,t)=34 − 0.003 z + 3e−5 t`
- `u_native(z,t)=0.23 + 0.002 z + 1e−5 t`
- `v_native(z,t)=−0.05 − 0.001 z + 2e−5 t`

All units follow standard ROMS (Celsius, practical salinity, m/s). Source velocities are set at native U/V sigma cell depths. Native `ubar/vbar` are computed by independently integrating source 3D profiles with layer `Hz`. Parent angle varies by `xi`; child angle varies by `eta` and `xi`. The fixture's two positive source donor weights each equal 0.5; analytical expected east/north components are calculated independently from the two parent donor angles, and then rotated into the **actual child U/V face angle**. Parent profile endpoints are explicitly clamped before analysis; the vertical out-of-range counts are checked, rather than claiming extrapolated deep physics.

Tests verify the independent analytical temperature/salinity profiles at **all three target times**, child native U/V shear profiles, source and child angles, sigma physical depths, and the child barotropic averages obtained from target `z_w`.

## Four wet normal sections and flux-accounting definitions

For each time and each physical side, only true **normal** native child face velocities contribute:

| Boundary | Normal velocity | Outward sign | Face width |
|---|---|---|---|
| South | `v` on `mask_v` | −1 | average neighboring `1/pm` |
| North | `v` on `mask_v` | +1 | average neighboring `1/pm` |
| West | `u` on `mask_u` | −1 | average neighboring `1/pn` |
| East | `u` on `mask_u` | +1 | average neighboring `1/pn` |

Using **the same independently remapped native-face sea level** that constructed target `z_w` and `ubar/vbar`, compare:

```
Q3D_face = outward_sign × face_width × sum_k(U_or_V_k × Hz_k)
Q2D_face = outward_sign × face_width × ubar_or_vbar × (h_face + zeta_face)
```

Both **individual wet-face** relative closure and accumulated section relative closure must be `<=1e−10`. No tangential velocity is accepted as a normal flux. Correct `Hz>0`, depth=sum(Hz), finite metrics and positive metric denominators are mandatory. A separate test deliberately injects two equal/opposite errors that cancel when summed: the new **individual-face gate rejects this false section pass**.

In the 6×7 synthetic receiver grid, each of the **3 timestamps** has 6 south wet V normal faces, 6 north wet V normal faces, 0 west wet U normal faces and 6 east wet U normal faces: **54 total normal wet face samples**. The zero-west case explicitly verifies all-dry side handling. North and south section totals are **not assumed opposite-signed**: local child U/V rotations and spatial velocity shear can make section flow directions differ; numerical flux is checked against the actual side's independently computed native barotropic values instead.

This target-side equality follows directly from the target `ubar/vbar` reconstruction and is therefore **internal numerical self-consistency, not an independent physical conservation proof**. Parent source `ubar/vbar` vs 3D-mean differences remain an explicit **diagnostic only**. Parent-to-child flux equality, 2D free-surface storage, tidal phase/volume budgets and actual ROMS integration remain **NOT_RUN**.

## Concrete verified CI

[**GitHub Actions #38695139302**](https://github.com/RRain001/ROMS/actions/runs/38695139302) – fast Ubuntu hosted suite **SUCCESS**. Per-suite counts: 10 strict parent-history contract tests, 7 complete BRY schema tests, 15 existing RHO/U/V preview tests, 10 new nonconstant and native flux tests, 10 ERA5 auth resolver tests without any real Secret access, 12 GLORYS/ERA5/TPXO staged interface tests and 6 actual original converter micro-tests, totaling **70 PASS**.

The new suite also writes nonconstant source-history-remapped output into **28-field synthetic-only ROMS BRY NetCDF**, then reopens and numerically compares each of 4×7 field/time arrays; file carries `SYNTHETIC_SCHEMA_TEST_ONLY_NOT_ROMS_PHYSICS` marking. CI does not run the previously expensive online GEBCO workflow, original full 41-level real-grid job or any ocean model.

### Limitations before real one-way nesting

1. Source velocity samples are collocated by mean of existing **wet native parent U/V faces at parent RHO donor nodes**. This is a defensible interpolation prototype, **not a volume-conservative parent face-to-child face flux transfer**.
2. Coastline certification on the real Option B perimeter donor manifests has been independently audited in prior GEBCO2026/GSHHG runs; the **current small synthetic tests use only manifest-like rows**, not real 15″ shoreline geometry.
3. A real ES3K ROMS history must have aligned timestamps, physical vertical metadata and full `zeta/temp/salt/u/v/ubar/vbar`, then pass source admission; the source should not silently regrid independent velocity/level fields.
4. Still need actual normal transport comparison, dynamic free-surface/tidal storage, barotropic mismatch thresholds and eventually real ROMS UD1K runs. Do not promote `PHYSICAL_ONE_WAY_NESTING_READY` from `FALSE`.

**No production year or user action is needed for the completed tests.**
