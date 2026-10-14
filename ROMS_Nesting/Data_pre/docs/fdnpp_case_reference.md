# FDNPP Case Experience Reference

This document records the reusable design experience from the active FDNPP
case. It is a reference for creating new research-region cases, not a source
for copying Fukushima-specific scientific values.

The authoritative case configuration is
`Data_pre/cases/FDNPP/config/project_parameters.json`. Generated grids, ROMS
inputs, run files, and reports live under `projects/FDNPP`; generated products
must not replace the case configuration as the source of truth.

## 1. Case in one sentence

FDNPP is a coastal ROMS dynamical case with one online passive tracer
(`dye_01`) representing an HTO-like release. The formal workflow initializes
the ocean from GLORYS12V1 and performs one continuous 15-month integration:
three months of zero-source preproduction followed by one year of active
production. The first three months are selected during post-processing, not
handed off through a separate hot-start task.

## 2. Configuration snapshot

| Component | Active FDNPP setting | Lesson for a new case |
| --- | --- | --- |
| Ocean source | GLORYS12V1 | Use the shared default unless a case has a documented reason to select HYCOM explicitly. |
| Vertical grid | `N=40`, `Vtransform=2`, `Vstretching=4` | Keep the framework default unless scientific validation supports an override. |
| Horizontal grid | Active grid is about `500 m`; `target_resolution_m=50` is not the active grid | Record target, pilot, and production resolutions separately. |
| Formal period | Continuous `2024-10-01` to `2026-01-01`; production results `2025-01-01` to `2026-01-01` | Keep the integration window and post-processing window explicit. |
| Initial state | GLORYS-derived physical fields; tracer starts at zero | A ROMS cold/new start does not mean a motionless ocean. |
| Production start | Same continuous task at `2025-01-01`; source switches from zero to active | Treat restart files as recovery checkpoints, not stage-handoff inputs. |
| Atmosphere | ERA5 wind/heat/radiation forcing | All forcing families must cover the complete model window. |
| Tides | TPXO elevation and current/UV ellipse data | Match generated tide variables to `SSH_TIDES` and `UV_TIDES`. |
| Parallel layout | `56` MPI ranks, `NtileI=7`, `NtileJ=8` | Choose tiles from the actual rank count; require `NtileI*NtileJ=np`. |
| Passive tracer | `T_PASSIVE`, `NPT=1`, `dye_01` | Keep tracer count, CPP options, `varinfo`, source file, and output flags synchronized. |

The release amount, Fukushima domain, source location, bathymetry, 56-core
layout, and 500 m grid are case-specific. They are examples of fields that
must be re-derived for a new region rather than copied unchanged.

## 3. Spatial domain and grid

The nominal research domain is:

```text
longitude: 140.88–142.00 E
latitude:  37.00–37.84 N
```

The active grid is
`projects/FDNPP/input/roms_grid_bathy_500m_maskclean_smoothed.nc`:

- RHO dimensions: `xi_rho=201`, `eta_rho=190`;
- physical size: approximately `99.02 km × 93.51 km`;
- grid spacing: approximately `497.6 m × 497.4 m`;
- wet RHO points: `33496` of `38190`;
- bathymetry range after the `Hmin=10 m` constraint: approximately `10–1318 m`;
- shoreline and mask processing: GSHHG-assisted cleanup followed by bathymetry
  smoothing with the land/sea mask held fixed.

The active grid is land-masked. The CPP header must define `MASKING`, and the
generated ROMS input must use the same grid that was used to create the
initial, boundary, tide, atmosphere, and source files. If the mask or grid is
changed, regenerate all downstream products.

### Source-point lesson

The configured source point is:

```text
141.0320 E, 37.4210 N
```

It falls on land in the active mask. The source-generation workflow therefore
snaps it to the nearest wet RHO cell:

```text
actual point: 141.0424 E, 37.4222 N
grid index:   xi=29, eta=95
depth:        10.86 m
distance:     about 929 m from configured point
```

For a new case, check source placement against `mask_rho` before generating a
source file. Prefer a scientifically justified wet-cell location or a clearly
documented snapping rule; do not silently assume the nominal coordinate is a
valid ROMS source location.

## 4. Formal time and data time axes

The formal workflow is:

```text
2024-10-01 00:00 ─────────────── 2025-01-01 00:00
              zero-source spin-up

2025-01-01 00:00 ─────────────────────────── 2026-01-01 00:00
                         source-active production
```

GLORYS12V1 daily means are centered at `12:00:00`. ROMS-ready files use the
configured `daily_mean_to_day_start` policy so model records are aligned to
calendar-day starts at `00:00:00`. The original source timestamp should remain
in NetCDF metadata for traceability.

For a new case, define and validate all of the following independently:

1. the requested model start and end;
2. the source dataset time window;
3. the spin-up start and end;
4. the production start and end;
5. the timestamp conversion policy between source and ROMS files.

## 5. Continuous integration and recovery

### 5.1 One continuous task

The active FDNPP continuous input uses:

```text
NRREC = 0
```

This means ROMS does not restore a previous ROMS restart. The physical fields
are initialized from GLORYS12V1 at `2024-10-01 00:00:00`; only the passive
tracer is initialized at zero. One continuous source file keeps the numerical
carrier transport but sets tracer release to zero before `2025-01-01` and
switches to the configured release at that time.

Continuous-run settings:

- duration: three-month configurable preproduction window plus one-year production;
- hourly history output: `zeta` only;
- daily average output: `dye_01`, `u`, `v`, `ubar`, `vbar`;
- diagnostics: off;
- restart output: every five days for recovery;
- tidal ramp: once at the beginning of the continuous integration;
- time step: `DT=60 s`, `NDTFAST=20`.

The formal result is the `2025-01-01` to `2026-01-01` slice of the continuous
NetCDF output. No production task is started after a preproduction milestone.

### 5.2 Recovery restart

Restart files remain enabled so an interrupted task can be recovered. They are
not the normal production input and should not be used to create a second
executable or a stage handoff. A recovery procedure must preserve the same
forcing window, tide reference date, and output naming contract.

The legacy split spin-up and production inputs remain available for reading or
reproducing historical results, but they are not the FDNPP default workflow.

## 6. Ocean, atmospheric, tide, and source inputs

The active FDNPP handoff contains:

- GLORYS12V1 initial and open-boundary fields;
- ERA5 atmospheric and radiation forcing;
- TPXO tidal elevation and current/UV ellipse forcing;
- a one-river/source NetCDF containing temperature, salinity, transport, and
  `river_dye_01`;
- a staged hourly source CSV used to derive the activity source.

The source settings are case-specific:

- annual release: `22 TBq/year`;
- release mode: constant over one calendar year;
- activity flux: derived from the annual amount;
- carrier transport: `1 m3/s` numerical value, explicitly not a measured
  discharge;
- source vertical location: surface layer;
- standard profile: radioactive decay disabled;
- optional decay profile: HTO half-life `12.32 years`.

The important reusable principle is to distinguish activity flux from the
numerical carrier transport. A new case must document the physical meaning,
units, vertical placement, and conversion formula instead of treating the
carrier flow as an observed river discharge.

## 7. Boundary, physics, and parallel settings

The active online profile uses:

- `MY25_MIXING` vertical mixing;
- Smagorinsky horizontal mixing with coefficient `0.2`;
- `SSH_TIDES` and `UV_TIDES`;
- `RAMP_TIDES` once from the continuous task's initial time;
- west boundary closed;
- east, south, and north boundaries open with radiation/nudging treatment for
  three-dimensional momentum and tracers;
- `56` MPI ranks partitioned as `7 × 8` tiles.

These values are useful as a complete example of a coupled online profile, but
the boundary layout, mixing, time step, and rank count must be reassessed for
each new domain.

## 8. Known implementation lessons

### Separate active and target resolution

FDNPP records a `50 m` target resolution but currently generates and runs with
the `500 m` active grid. New cases should place the active grid filename and
resolution in the readiness report and should not infer resolution from a
planning field alone.

### Check continuous initial-file alignment

The contract is that the continuous initial file, `DSTART`, and all forcing
starts equal `2024-10-01 00:00:00`. The formal result window is selected later
from the same output files.

This is a general rule: validation must compare the time stored inside the
initial NetCDF with `DSTART`, not only check that the filename exists.

### Do not confuse Data_pre readiness with run readiness

FDNPP's GLORYS, ERA5, tide, source, and ROMS-ready input checks can pass while
a mode is still blocked by a missing executable or short-window forcing file.
Readiness should be reported separately for:

1. staged raw data;
2. ROMS-ready input files;
3. build artifacts;
4. mode-specific run prerequisites;
5. actual model execution.

### Keep compatibility products visibly separate

Unsuffixed ocean products and the old HYCOM manifest are retained for
compatibility or fallback use. Active GLORYS products use source-aware names.
New cases should use canonical source-aware filenames from the beginning.

## 9. New-case checklist derived from FDNPP

Before copying the FDNPP pattern to another region, answer these questions:

- Is the nominal source point on a wet ROMS cell?
- What are the target, pilot, and active production resolutions?
- Does the active grid have a documented mask and bathymetry audit?
- Does the initial NetCDF time exactly match `DSTART`?
- Does the ocean source cover the complete continuous window?
- Has the source-time-to-ROM-time conversion been recorded?
- Are atmosphere, radiation, tide, boundary, and source files all aligned to
  the same time window?
- Is the preproduction tracer source zero by construction and active at the
  formal start?
- Is the restart treated only as an interruption-recovery checkpoint?
- Do `NtileI*NtileJ` and the MPI rank count agree?
- Are source flux units, carrier transport, and vertical placement documented?
- Are raw-data, ROMS-ready, build, and run-layer readiness reported separately?

## 10. Reference files

- `Data_pre/cases/FDNPP/config/project_parameters.json`
- `Data_pre/cases/FDNPP/config/data_sources_required.csv`
- `Data_pre/cases/FDNPP/config/roms_run_config.json`
- `Data_pre/cases/FDNPP/docs/workflow.md`
- `Data_pre/cases/FDNPP/docs/readiness_report.md`
- `Data_pre/docs/adding_a_case.md`
