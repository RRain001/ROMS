# I8 — Thyng (2021) → ROMS 4.3 offline Eulerian HTO source port audit

**State (2026-10-14): BLOCKED_PORT_REQUIRED. ROMS full standard/offline-scaffold CMake compile and link PASS; actual offline HTO numerical integration NOT_RUN.**
**I8 driver binding (this commit):** the independent `nl_roms.h` dispatches `OFFLINE && OFFLINE_TPASSIVE` to newly introduced `main3d_offline.F`. The modern CMake source list includes it and `offline_tracer_stage.F`; GNU Make `Module.mk` already uses a wildcard to discover new `.F` files. The new routine **FAILS CLOSED** with `ROMS_NESTING_I8_BLOCKED_PORT_REQUIRED` because hydrodynamic snapshot input, tracer stepping and volume-budget synchronization remain unimplemented. It MUST NOT invoke normal `main3d` as a shortcut. `offline_tracer_stage.F` joins the two previously native-unit-tested ROMS routines as setup/midpoint stages; it is **not called by the guarded driver yet**. **Three-snapshot correction implemented:** in-place `set_massflux_avg` replaces the stored endpoint with the midpoint. A new `set_massflux_endpoint` (called by `offline_endpoint_stage`) restores the current interval's right-endpoint flux before the next interval. Two-tile, three-snapshot native gfortran tests PASS; integration with the actual main offline timestep remains blocked. The present stage is an interface scaffold, **not** a valid multistep solver.



**First modern Fortran port slice (NOT a full offline driver):** `ROMS_Nesting/roms_src/roms/ROMS/Nonlinear/set_zeta.F` now contains `set_avg_zeta`, gated behind both `OFFLINE` and `OFFLINE_TPASSIVE`. It selects `zeta(:,:,1)` during first initialization and `zeta(:,:,2)` during later snapshots and copies the result tile-by-tile into `COUPLING%Zt_avg1`. Unlike Thyng's old implementation, `FirstCall` is `intent(in)` and is not mutated inside a tile: the future **outer** offline driver must change that flag only after all tiles complete. A GitHub-hosted Ubuntu CI step compiles **the actual modified ROMS Fortran file** using minimal test-only stub modules in **both normal and offline modes**, exercising two separate tiles and testing default behavior unchanged. The adapter has **no live offline time-step caller yet**, so this step alone does not make I8 PASS.

The branch `feature/japan-sea-nesting` keeps all implementation code inside `ROMS_Nesting/`. This report documents successful **complete standard/offline-scaffold compilation and linking**, but remains **not** evidence of completed offline tracer physics or time stepping. No `main` or original single-grid code is modified.

## Pinned upstream evidence

- [Thyng et al., GMD 14, 391–407 (2021)](https://doi.org/10.5194/gmd-14-391-2021), Appendix B/C. The paper tested offline Eulerian tracer transport within **ROMS v3.6 r904** in COAWST, not this repository's ROMS 4.3.
- [COAWST-ROMS-OIL pinned commit](https://github.com/kthyng/COAWST-ROMS-OIL/tree/5488c3fd3865c567fa1833c8ed670c7dce0fc676) `5488c3fd3865c567fa1833c8ed670c7dce0fc676`. Individual upstream Git object hashes are stored in `thyng_offline_upstream.json`; GitHub Actions fetches these pinned files and checks SHA1 with Git blob encoding before auditing.
- [Paper-version archival snapshot](https://doi.org/10.5281/zenodo.4455738) (v1.1). **Caution:** the inspected GitHub commit is an explicitly pinned source reference, not yet demonstrated bit-for-bit identical to the Zenodo paper snapshot. That archival reproducibility comparison remains open.
- Associated [offline run configurations](https://github.com/kthyng/oil_off) and [online run configurations](https://github.com/kthyng/oil_03) need further review to establish a genuinely buildable ROMS 4.3 configuration.

## Verified source-level gaps (first audit)

| Relevant component | Thyng 2021 pinned source | Independent ROMS 4.3 copy | Implication |
| --- | --- | --- | --- |
| Nonlinear offline integration | `ROMS/Nonlinear/main3d_offline.F` includes `OFFLINE_TPASSIVE`, `set_avg_zeta`, `set_massflux_avg`, calls `step3d_t` | **Scaffold now exists, linked and routed through `nl_roms.h`; deliberately aborts before physical integration** | Need hydrodynamic snapshot load, actual `step3d_t`, output/restart and multi-tile synchronization, before I8 can PASS |
| Tracer mass transport | `set_massflux.F` contains `set_massflux_avg` and time-averages `Huon/Hvom` | **Added independently under offline macros, without full-grid scratch buffers**; outer time driver still absent | Native gfortran normal/offline tile contract now required; real sigma/time interpolation and ROMS runtime NOT_RUN |
| Moving free surface | `set_zeta.F` defines `set_avg_zeta` for offline surface/depth | **Now added behind `OFFLINE && OFFLINE_TPASSIVE` to the independent Fortran source**, but no offline caller exists yet | Time-dependent `Hz`/free surface must match transport scheme; a native mock-module source compile is necessary but not a full ROMS run |
| Vertical mixing | Upstream `AKSCLIMATOLOGY` and `Aks` pathway | Current ROMS 4.3 `varinfo.yaml` contains `AKs` but does not imply offline forcing works | Trace `get_data`/time records and connection to tracer mixing |
| Input metadata | Upstream `ROMS/External/varinfo-offline.dat` | Current ROMS has YAML `ROMS/External/varinfo.yaml` | Requires modern variable schema, **do not overwrite** it with upstream `varinfo.dat` |
| Driver & build | Upstream `nl_ocean.h` and older module layout | **Modern `nl_roms.h` dispatch and CMake + GNU Make source registration now implemented, both full configurations link** | Fail-closed scientific gate stays active until full offline physics executes |

**Architecture consequence:** neither `OFFLINE_TPASSIVE` in a paper header nor individual old Fortran routines can safely be dropped into a modern ROMS without source adaptation. **Only the isolated free-surface adapter has been applied.** Do not label I8 PASS.

**Second native port slice — face volume flux:** `ROMS_Nesting/roms_src/roms/ROMS/Nonlinear/set_massflux.F` now defines a guarded `set_massflux_avg` for `OFFLINE && OFFLINE_TPASSIVE`. It expects previous-snapshot `Huon/Hvom` to have been initialized by `set_massflux`, then forms current-snapshot face fluxes using updated `Hz`, `u/v(nnew)`, and `on_u/om_v` and replaces storage by their midpoint average. Unlike Thyng's temporary full-grid `Huonnew/Hvomnew`, it updates values directly per tile. The native two-tile gfortran test checks expected `20→40` and `60→90` face flux values on two synthetic sigma layers, plus **ordinary ROMS source behavior** without offline CPP. **Caution:** test-only stubs, no actual ROMS driver, parallel MPI, WEC, netCDF dynamics or real boundary flux integration has yet been exercised. Before I8 physics PASS must establish exact time-level/Hz sequencing, halo synchronization, and `Aks` integration. The audit retains `BLOCKED_PORT_REQUIRED` until the true offline driver is implemented.

## Full-build and input-contract validation evidence

- [I8 full ROMS native CMake compile run #38519504781](https://github.com/RRain001/ROMS/actions/runs/38519504781): GitHub-hosted Ubuntu 24.04, both the ordinary `UPWELLING` build and `OFFLINE/OFFLINE_TPASSIVE/T_PASSIVE` variant compiled and **linked** the full ROMS `romsS` executable, `SUCCESS`. This is a **build gate**, not a successful hydrodynamic or offline-tracer simulation.
- First run [#38519109733](https://github.com/RRain001/ROMS/actions/runs/38519109733) failed at **100% linkage**, because the copied upstream CMake parser mistakenly treated substrings `-linux-gnu` in a `-L/usr/lib/...linux-gnu` directory and `-lto-objects` inside a compiler flag as libraries. Fixed **only in `ROMS_Nesting/roms_src/roms/Compilers/roms_functions.cmake`**, using full shell token recognition. `main` stayed unchanged.
- [I0 regression #38519504793](https://github.com/RRain001/ROMS/actions/runs/38519504793): previous isolated code, rotated-grid, three-domain Bq ledger and native Fortran tests remain green.
- `ROMS_Nesting/offline_tracer/validate_hydro_inputs.py` + `tests/test_offline_hydro_contract.py` use generated **synthetic** NetCDF to reject missing/nonmonotonic `ocean_time`, wrong C-grid `u/v` dimensions, missing or negative `AKs` and omitted velocity fields. These checks do not prove real Japan Sea hydrodynamics exist or can be transported by offline ROMS.
- `offline_tracer_stage.F` implements setup, midpoint and endpoint **stage contracts** and native gfortran order tests; the fail-closed driver is not yet allowed to execute `step3d_t`. **Never remove the abort** until all input, tracer, conservation and restart dependencies are linked.

**Blocking I8 requirements remain**: actual ROMS climatology/history snapshot reader (including `AKs`), offline clock/time-level control, physical layer thickness/face flux chronology, `step3d_t` without recalculating water dynamics, restart/output, and native short-case comparison with online `T_PASSIVE`. **I8 physics: NOT RUN; I9: NOT RUN; I10 real cross-grid activity exchange: NOT RUN.**

## I8 native NetCDF history reader gate (2026-10-14)

A separate Fortran module, `ROMS_Nesting/roms_src/roms/ROMS/Nonlinear/offline_hydro_reader.F`, has been added to the independent CMake source list. It uses the **real NetCDF-Fortran API**, not mock data loaders or Python hydrodynamic interpolation. It reads specified records of `zeta` (rho), `u` (u), `v` (v), `ubar/vbar`, and `AKs` (s_w interfaces), validating exact C-grid dimensions, strictly ascending `ocean_time`, Fortran NetCDF dimension order, positive/nonnegative mixing, and finite values. The reader converts "days since" timestamps to seconds; "seconds since" remain seconds. No production `OCEAN/MIXING` state transfer yet exists.

- [Actions #38520736114 — SUCCESS](https://github.com/RRain001/ROMS/actions/runs/38520736114): full ordinary/offline ROMS compile/link plus native Fortran NetCDF integration tests; resolved `xi_v` versus `eta_v` dimension mix-up before PASS.
- [Actions #38521179471 — SUCCESS](https://github.com/RRain001/ROMS/actions/runs/38521179471): CPP evidence gates confirm the **actual generated** offline Fortran contains the fail-closed entry, whereas standard compilation excludes that routine. Merely linking a binary is not enough.
- [Actions #38521342606 — SUCCESS](https://github.com/RRain001/ROMS/actions/runs/38521342606): the native Fortran test now reads synthetic **nonuniform values across time, depth, latitude and longitude** and compares exact expected indices for `u/v/zeta/vbar/AKs`, including the third time record. Absent `AKs`, reversed timestamps, invalid U-grid dimensions and NaN velocities are rejected. Both full ROMS builds and the original Python suite remain separate gates.

**Important limitations:** this reader intentionally rejects grids with more than **100,000 rho cells** until tile/window streaming and MPI decomposition are implemented. It loads one whole small-domain record, not a production ES3K/UD1K/L3 history dataset. It does not automatically feed `OCEAN%u/v/zeta` or `MIXING%Akt`; `step3d_t`, surface/vertical-coordinate consistency, halo exchanges and actual offline numerical integration remain **NOT RUN**. For inert tracers, `step3d_t` selects `ltrc=MIN(NAT,itrc)`, so the HTO `AKs` mapping must explicitly target the correct salinity-group `MIXING%Akt` slot. No cross-grid Bq conservation follows from this single-grid file-read evidence.

**Next native integration gate:** write bounded tile-aware snapshot reads and a tested C-grid-to-ROMS state adapter that populates valid time slots and `MIXING%Akt`; verify 3+ consecutive windows, correct `Hz` and `Huon/Hvom` chronology, then replace the fail-closed main3d scaffold with an actual tracer-only single-grid run. Keep the main branch and legacy single-grid workflows untouched.

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

1. Replace the fail-closed `main3d_offline.F` scaffold with a modern ROMS offline time loop that actually loads frozen flow fields; trace `get_data/set_data`, `nrhs/nnew`, `Hz` and the correct snapshot/time-window boundaries. Retain a fail-closed gate until complete.
2. Integrate `offline_setup_stage/midpoint_stage/endpoint_stage` across tiles with real time barriers, then call `step3d_t` and verify `AKs` vertical tracer mixing without running momentum/heat/atmosphere dynamics.
3. Map ROMS 4.3 `varinfo.yaml`/climatology loading for `zeta,u,v,ubar,vbar,AKs`; supply physically valid small synthetic ROMS history and initial tracer NetCDF, not just schema checks.
4. Execute a **real** 1h/6h/24h offline single-grid ROMS smoke and compare online `T_PASSIVE` fields and Bq inventory before marking I8 physics PASS.
5. Later I10 must expose and conservatively exchange face-resolved activity fluxes between rotated parent and unrotated child; Thyng paper establishes no such three-domain guarantee.

**Input sources remain** GEBCO 2026, GSHHG, GLORYS12V1 by default (HYCOM opt-in), ERA5 and TPXO9; this audit does not change them or the one-way hydrodynamic architecture.
