# Japan Sea UD1K Option B: archived REAL grid source manifests + synthetic dynamic 41-level sections

**Date** 2026-10-15. **Working branch** `codex/es3k-i3-wet-domain-audit-20261014`, [Draft PR #3](https://github.com/RRain001/ROMS/pull/3); base `feature/japan-sea-nesting`. No production year approved, no GEBCO/GSHHG regeneration, no original masks/geometry modified, no real ES3K ROMS hydrodynamic history.

## Real scientific input provenance

This audit reuses the **previously successful** [GEBCO2026/GSHHG I3 Actions #38680030642](https://github.com/RRain001/ROMS/actions/runs/38680030642), artifact **`ud1k-27-wet-boundary-mapping-small-json`** (artifact id 11948485400; about 2.3 MB zipped), which contains:

- `UD1K_CONNECTED_CORE_SHORELINE_CLEAR_COMPARISON_CANDIDATE.nc` **actual 290 × 438 RHO** derived from real bathymetry and coastline: 96,104 wet RHO in one connected component, original scientific active grid unmodified.
- `ud1k_core_shoreline_clear_1011_rho_map.json`: **1,011** independently GSHHG coast-clear RHO perimeter source stencil records preserved as a subset of the original full 1,017 wet RHO mapped records.
- `ud1k_core_shoreline_clear_native_uv_boundary_map.json`: **1,005 U** and **1,010 V** independently mapped, actual wet child staggered boundary receivers with upstream certification that each source parent RHO donor supports **both native wet U and native wet V**. Records are *not* reconstructed by copying RHO target weights.

The [read-only manifest contract](../Data_pre/nesting/ud1k_real_optionb_manifest_contract.py) checks actual NetCDF dimensions, wet masks RHO/U/V, exact nearest-neighbor C-grid wet-face logic, positive wet bathymetry, finite positive wet `pm/pn`, angle, all unique row-major physical wet perimeter receivers, coast-visible source certification flags, donor source index bounds for the expected **732×464 parent RHO shape**, distinct donor nodes, nonnegative finite weights summing to one, original-source-preservation flag and zero unresolved native donor cases. It checks the **actual target native normal wet faces**:

| Boundary | Child native normal component | Wet faces |
| --- | --- | ---: |
| South | V | 382 |
| North | V | 364 |
| West | U | 0 |
| East | U | 266 |
| Total | | **1,012** |

**Scope limit:** the full real ES3K parent grid and land/wet mask were NOT downloaded for this light-stage rerun. These source wet/native donor certifications originate in the *earlier* I3 full-parent audit; this recheck validates their flags, data structure and receiver association but does NOT independently recompute shoreline intersections or parent mask/native U/V donor wetness from the 157MB archived parent-grid source artifact. Status deliberately says `NOT_RECHECKED_HERE_PRIOR_SOURCE_MANIFEST_CERTIFICATION_ONLY`.

## Actual child geometry, synthetic time-varying flow and 2D/3D native flux

[`ud1k_optionb_synthetic_dynamic_section.py`](../Data_pre/nesting/ud1k_optionb_synthetic_dynamic_section.py) reads REAL Option B child `h`, `angle`, `pm/pn` and wet native U/V masks. It generates **synthetic geographic vector flow** that varies with physical depth `z`, and time `t`, and a synthetic sea-level change:

```
target seconds = [0,1800,3600]
synthetic zeta [m] = [0.4,1.0,1.6]
child sigma n = 41, Vtransform=2, Vstretching=4, hc=50m, theta_s=5, theta_b=1
east(z,t)  =  0.20 + 0.0002*z + 1e-5*t  [m/s]
north(z,t) = -0.10 + 0.0001*z + 2e-5*t  [m/s]
```

For each actual wet child open native face, the physical face depth is the mean adjacent actual RHO bathymetry and free surface, and the local grid angle is obtained by an angular wrap-safe `atan2(mean sin,mean cos)`. The geographic synthetic E/N field is independently rotated into the child's actual local U **or** V component. Physical `z_r` and `z_w`/Hz recomputed at each actual face and each free-surface time. `ubar/vbar` is integrated by the target face layer thickness. Each of **1,012** real native normal wet faces × **3** times = **3,036** face-time samples contributes to outward Q3D and Q2D. Checks reject malformed geometry, nonfinite or negative Hz, incorrect tangential component use, invalid pm/pn and both per-face and whole-side Q2D-vs-Q3D mismatch. This is a **synthetic-velocity numerical consistency check on real child geometry** — not parent ES3K history interpolation and not a mass conservation proof.

## Executed evidence

[**GitHub Actions #38696848420**](https://github.com/RRain001/ROMS/actions/runs/38696848420) — both synthetic fast suite and the real archived Option B 2.3MB-mapping-only job completed **SUCCESS**.

- **15 new fast unit tests PASS** (11 donor-manifest malformed/duplicate/missing/weight/coast cases + 4 changing analytical flow safety cases).
- Previously established **70 synthetic history/schema/physics-preview/forcing converter unit tests** still PASS; total **85** bounded automatic synthetic tests PASS.
- Actual archived NetCDF + manifests: RHO=1011, U=1005, V=1010, real normal counts south=382/north=364/west=0/east=266. Candidate still `COMPARISON_CANDIDATE_NOT_ACTIVE`.
- Real Option B h/angle/pm/pn, synthetic changing `zeta` and 41-level analytic shear over 3 times: **3,036 face-time samples**; max relative section Q2D-vs-Q3D difference **`1.9302399274567954e-16`**.
- Output logs explicitly mark `real_ES3K_hydrodynamic_history=NOT_AVAILABLE`, `actual_time_dependent_bry_and_parent_child_mass_flux=NOT_RUN`, `real_UD1K_ocean_model_integration=NOT_RUN`.
- The archive-based real geometry job is now **workflow_dispatch only**, because its prior GitHub artifact expires; automatic PR CI continues only the **85 small synthetic unit tests**. The older full GEBCO/GSHHG workflows also remain manual-only.

## Remaining crucial physics work

1. True ES3K history `zeta,temp,salt,u,v,ubar,vbar` source, not synthetic profiles, with known time epoch, sigma setup and hour-wise full wet source audit; none exists yet.
2. Source face native wetness/coastline certification is currently trusted from previous I3, not directly re-validated in this light archival audit. Need the real parent grid for independent re-audit if donor map changes.
3. Real parent-to-child open boundary `bry.nc` production, including time calendar, parent/child sigma remap and conservative source/target volume flux coupling, plus tide/volume storage and real ROMS startup integration are all `NOT_RUN`.
4. This is NOT approval to activate comparison Option B or merge PR #3. Frozen original grids and non-nested source trees are unchanged.

**Conclusion:** actual real candidate-B geometry, independent certified native receiver source maps and synthetic 41-level 3-time normal-flux arithmetic are now connected and tested with a small archived artifact. Physical one-way ROMS nesting remains **HOLD**.
