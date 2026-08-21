# FDNPP_202501 historical workflow notes

> Historical snapshot: this archived January 2025 case is not the current
> authoritative FDNPP configuration. Use `Data_pre/cases/FDNPP` for the active
> formal case. The original status and blocker statements below are preserved.

This document records the archived FDNPP workflow contract across `Data_pre`,
`ROMS_Build`, and `ROMS_Run`.

Runtime configuration is authoritative in:

```text
/home/lhy/ROMS/Data_pre/cases/FDNPP_202501/config
```

Generated products live under:

```text
/home/lhy/ROMS/projects/FDNPP_202501
```

`projects/FDNPP_202501/config` is a legacy/generated snapshot location and must not be
used as the source of truth.

## Case Settings

- case name: `FDNPP_202501`
- research domain: `140.88-142.00E`, `37.00-37.84N`
- default ocean source: GLORYS12V1
- active vertical levels: `N=40`
- build jobs: `56`
- MPI ranks: `56`
- ROMS tiles: `NtileI=7`, `NtileJ=8`
- active grid: `input/roms_grid_bathy_500m_maskclean_smoothed.nc`

FDNPP uses a land/sea mask. The case CPP header must define `MASKING`, otherwise
ROMS ignores `mask_rho` and can integrate masked land cells as shallow ocean.

## Formal Online Passive Tracer Workflow

The formal online passive tracer workflow is generic. FDNPP is a configuration
instance, not a hard-coded workflow target.

Formal periods:

- spin-up: `2024-10-01T00:00:00` to `2025-01-01T00:00:00`
- production: `2025-01-01T00:00:00` to `2026-01-01T00:00:00`

Current status:

- workflow layer: ready
- pre-run validation: passed
- output configuration: confirmed for generated `.in` files
- zero-source spin-up source: generated
- production hot start: configured to use the final spin-up restart
- spin-up input data: blocked by tide staging

Do not claim the 3-month spin-up is runnable until the tide staging blocker below
is resolved.

## Tide Staging Blocker

Current blocking issue:

```text
raw_tides missing tide_Eamp/tide_Ephase/tide_Cmax/tide_Cmin/tide_Cangle/tide_Cphase
```

Follow-up task:

```text
Fix spin-up tide staging for formal online workflow
```

## Output Contract

Spin-up 3 months:

- history: off
- restart: every 5 days
- diagnostics: off
- source: zero-source
- recommended tracer setting: keep `T_PASSIVE` / `NPT=1` so restart contains
  `dye_01=0`

Production 1 year:

- hourly history: `zeta` only
- daily average: `dye_01`, `u`, `v`, `ubar`, `vbar`
- restart: full restart every 5 days
- diagnostics: off
- no-decay and decay production output settings must stay identical; only the
  radioactive decay switch and matching executable/profile should differ

This output plan supports daily mean dispersion maps and daily mean animations.
It does not support hourly `dye_01` dispersion animation.

## Validation Commands

Run from `/home/lhy/ROMS`:

```bash
python3 Data_pre/scripts/validation/validate_formal_online_workflow.py --case-name FDNPP_202501 --profile online_my25_uvtide --phase pre-run
python3 Data_pre/scripts/validation/validate_spinup_inputs.py --case-name FDNPP_202501
python3 ROMS_Run/scripts/checks/validate_run_prereqs.py --case-name FDNPP_202501 --mode online_spinup_3mo_my25_uvtide
python3 ROMS_Run/scripts/checks/validate_run_prereqs.py --case-name FDNPP_202501 --mode online_production_1y_my25_uvtide_from_spinup
python3 ROMS_Run/scripts/checks/validate_run_prereqs.py --case-name FDNPP_202501 --mode online_production_1y_my25_uvtide_decay_from_spinup
```

Expected today:

- formal workflow pre-run validation passes
- run prerequisite checks pass for configuration/files that already exist
- `validate_spinup_inputs.py` remains blocked by the raw tide variable issue

## Build And Run

Build plan:

```bash
python3 ROMS_Build/scripts/build/show_build_plan.py --case-name FDNPP_202501
```

Build:

```bash
python3 ROMS_Build/scripts/build/build_roms_case.py --case-name FDNPP_202501
```

Standard executable location:

```text
/home/lhy/ROMS/projects/FDNPP_202501/bin/romsM_fdnpp
```

Real Intel MPI/Hydra runs should be launched outside the Codex sandbox, or with
approved non-sandbox execution, because local socket creation can be blocked by
sandboxing.

## Reports

Keep current formal/spin-up blocker reports tracked:

- `projects/FDNPP_202501/reports/formal_online_spinup_output_flow.md`
- `projects/FDNPP_202501/reports/formal_online_spinup_output_flow.json`
- `projects/FDNPP_202501/reports/fdnpp_spinup_20241001_20250101_data_ready.md`
- `projects/FDNPP_202501/reports/fdnpp_spinup_20241001_20250101_data_ready.json`

Historical 7-day, month, decay, and reconfiguration reports are archived in the
working tree or ignored output area and should not be treated as current formal
workflow status.
