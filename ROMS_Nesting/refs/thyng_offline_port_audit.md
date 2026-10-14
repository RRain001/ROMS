# I8 — Thyng (2021) → ROMS 4.3 offline Eulerian HTO source port audit

**State (2026-10-14): BLOCKED_PORT_REQUIRED, source-level inspection only.**
**I8 driver binding (this commit):** the independent `nl_roms.h` dispatches `OFFLINE && OFFLINE_TPASSIVE` to newly introduced `main3d_offline.F`. The modern CMake source list includes it and `offline_tracer_stage.F`; GNU Make `Module.mk` already uses a wildcard to discover new `.F` files. The new routine **FAILS CLOSED** with `ROMS_NESTING_I8_BLOCKED_PORT_REQUIRED` because hydrodynamic snapshot input, tracer stepping and volume-budget synchronization remain unimplemented. It MUST NOT invoke normal `main3d` as a shortcut. `offline_tracer_stage.F` joins the two previously native-unit-tested ROMS routines as setup/midpoint stages; it is **not called by the guarded driver yet**. **Crucial new caveat:** the in-place `set_massflux_avg` destroys the previous unaveraged endpoint flux. Prior to multistep driving, a dedicated previous-snapshot flux buffer or equivalent must be implemented and tested, otherwise 3+ windows will average the previous midpoint instead of previous endpoint. The present stage is an interface scaffold, **not** a valid multistep solver.



**First modern Fortran port slice (NOT a full offline driver):** `ROMS_Nesting/roms_src/roms/ROMS/Nonlinear/set_zeta.F` now contains `set_avg_zeta`, gated behind both `OFFLINE` and `OFFLINE_TPASSIVE`. It selects `zeta(:,:,1)` during first initialization and `zeta(:,:,2)` during later snapshots and copies the result tile-by-tile into `COUPLING%Zt_avg1`. Unlike Thyng's old implementation, `FirstCall` is `intent(in)` and is not mutated inside a tile: the future **outer** offline driver must change that flag only after all tiles complete. A GitHub-hosted Ubuntu CI step compiles **the actual modified ROMS Fortran file** using minimal test-only stub modules in **both normal and offline modes**, exercising two separate tiles and testing default behavior unchanged. The adapter has **no live offline time-step caller yet**, so this step alone does not make I8 PASS.

The branch `feature/japan-sea-nesting` keeps all implementation code inside `ROMS_Nesting/`. This report is **not** evidence of successful offline compilation or transport physics. No `main` or original single-grid code is modified.

## Pinned upstream evidence

- [Thyng et al., GMD 14, 391–407 (2021)](https://doi.org/10.5194/gmd-14-391-2021), Appendix B/C. The paper tested offline Eulerian tracer transport within **ROMS v3.6 r904** in COAWST, not this repository's ROMS 4.3.
- [COAWST-ROMS-OIL pinned commit](https://github.com/kthyng/COAWST-ROMS-OIL/tree/5488c3fd3865c567fa1833c8ed670c7dce0fc676) `5488c3fd3865c567fa1833c8ed670c7dce0fc676`. Individual upstream Git object hashes are stored in `thyng_offline_upstream.json`; GitHub Actions fetches these pinned files and checks SHA1 with Git blob encoding before auditing.
- [Paper-version archival snapshot](https://doi.org/10.5281/zenodo.4455738) (v1.1). **Caution:** the inspected GitHub commit is an explicitly pinned source reference, not yet demonstrated bit-for-bit identical to the Zenodo paper snapshot. That archival reproducibility comparison remains open.
- Associated [offline run configurations](https://github.com/kthyng/oil_off) and [online run configurations](https://github.com/kthyng/oil_03) need further review to establish a genuinely buildable ROMS 4.3 configuration.

## Verified source-level gaps (first audit)

| Relevant component | Thyng 2021 pinned source | Independent ROMS 4.3 copy | Implication |
| --- | --- | --- | --- |
| Nonlinear offline integration | `ROMS/Nonlinear/main3d_offline.F` includes `OFFLINE_TPASSIVE`, `set_avg_zeta`, `set_massflux_avg`, calls `step3d_t` | **Absent**; current `main3d.F` exists | Need new version-aware offline driver plus correct build and `nl_roms.h` dispatch |
| Tracer mass transport | `set_massflux.F` contains `set_massflux_avg` and time-averages `Huon/Hvom` | **Added independently under offline macros, without full-grid scratch buffers**; outer time driver still absent | Native gfortran normal/offline tile contract now required; real sigma/time interpolation and ROMS runtime NOT_RUN |
| Moving free surface | `set_zeta.F` defines `set_avg_zeta` for offline surface/depth | **Now added behind `OFFLINE && OFFLINE_TPASSIVE` to the independent Fortran source**, but no offline caller exists yet | Time-dependent `Hz`/free surface must match transport scheme; a native mock-module source compile is necessary but not a full ROMS run |
| Vertical mixing | Upstream `AKSCLIMATOLOGY` and `Aks` pathway | Current ROMS 4.3 `varinfo.yaml` contains `AKs` but does not imply offline forcing works | Trace `get_data`/time records and connection to tracer mixing |
| Input metadata | Upstream `ROMS/External/varinfo-offline.dat` | Current ROMS has YAML `ROMS/External/varinfo.yaml` | Requires modern variable schema, **do not overwrite** it with upstream `varinfo.dat` |
| Driver & build | Upstream `nl_ocean.h` and older module layout | Current `nl_roms.h` and `Nonlinear/CMakeLists.txt` | Need explicit dispatch/compilation changes; blind copying will not compile |

**Architecture consequence:** neither `OFFLINE_TPASSIVE` in a paper header nor individual old Fortran routines can safely be dropped into a modern ROMS without source adaptation. **Only the isolated free-surface adapter has been applied.** Do not label I8 PASS.

**Second native port slice — face volume flux:** `ROMS_Nesting/roms_src/roms/ROMS/Nonlinear/set_massflux.F` now defines a guarded `set_massflux_avg` for `OFFLINE && OFFLINE_TPASSIVE`. It expects previous-snapshot `Huon/Hvom` to have been initialized by `set_massflux`, then forms current-snapshot face fluxes using updated `Hz`, `u/v(nnew)`, and `on_u/om_v` and replaces storage by their midpoint average. Unlike Thyng's temporary full-grid `Huonnew/Hvomnew`, it updates values directly per tile. The native two-tile gfortran test checks expected `20→40` and `60→90` face flux values on two synthetic sigma layers, plus **ordinary ROMS source behavior** without offline CPP. **Caution:** test-only stubs, no actual ROMS driver, parallel MPI, WEC, netCDF dynamics or real boundary flux integration has yet been exercised. Before I8 physics PASS must establish exact time-level/Hz sequencing, halo synchronization, and `Aks` integration. The audit retains `BLOCKED_PORT_REQUIRED` until the true offline driver is implemented.

## CI audit — exact reproduction

The branch workflow `.github/workflows/japan-sea-nesting-i0.yml` runs:

```sh
cd ROMS_Nesting
python3 scripts/audit_thyng_offline.py \
  --verify-upstream --expect-gap \
  --output "$RUNNER_TEMP/thyng-i8-report"
```

It emits `compatibility.json` and `compatibility.md` artifacts with pinned upstream SHA, local source SHA, missing integration symbols, and ordered actions. **A green audit means source gap checking succeeded; it explicitly reports `BLOCKED_PORT_REQUIRED` rather than a successful physics test.** Any unexpected loss of an upstream pin or change in expected baseline status must FAIL the audit.

## Next implementation gate (before adding more physics)

1. Study `main3d_offline.F` and the original `nl_ocean.h` dispatcher versus local `nl_roms.h`; write a minimal integration diagram and CPP contract. Check local `CMakeLists.txt` and `Module.mk`, rather than patching obsolete makefile names.
2. Move the required `set_avg_zeta` / `set_massflux_avg` behavior into an isolated modern ROMS 4.3 implementation, with original-time-layer semantics preserved.
3. Map modern `varinfo.yaml` and climatology-loading paths for `zeta,u,v,ubar,vbar,Aks`, derive online forcing data contract and selection flags.
4. Build and **actually run** the offline single-grid ROMS small synthetic smoke in GitHub-hosted Ubuntu; compare with same online case. Only then mark I8's physical gate PASS.
5. Later I10 must expose and conservatively exchange face-resolved activity fluxes between rotated parent and unrotated child; Thyng paper establishes no such three-domain guarantee.

**Input sources remain** GEBCO 2026, GSHHG, GLORYS12V1 by default (HYCOM opt-in), ERA5 and TPXO9; this audit does not change them or the one-way hydrodynamic architecture.
