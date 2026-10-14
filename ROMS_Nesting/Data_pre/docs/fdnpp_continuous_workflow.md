# FDNPP Continuous Workflow

The authoritative runtime configuration is
`Data_pre/cases/FDNPP/config/project_parameters.json`. The active default is
`online_continuous_my25_uvtide`: one executable, one input file, and one
continuous integration from `2024-10-01 00:00:00` through `2026-01-01 00:00:00`.

## Contract

- `preproduction_months` defaults to `3`; changing it moves the integration
  start without creating a new spin-up/production handoff.
- The preproduction source is exactly zero before `2025-01-01`; the configured
  release becomes active at `2025-01-01`.
- `NRREC=0` and the GLORYS initial file are used at the continuous start.
- `RAMP_TIDES` runs once at the beginning; it is not restarted at the formal
  production boundary.
- Restart files are recovery checkpoints only.
- Formal post-processing selects `2025-01-01` through `2026-01-01` from the
  continuous history/average output.

The canonical tide file is
`projects/FDNPP/input/roms_tides_fdnpp_online_my25_uvtide.nc`. Its
`zero_phase_date` is fixed at `20241001.0`, and TPXO complex components are
interpolated before deriving OTPS elevation phase and the ROMS current ellipse.

## Validation and Launch

Run these checks from `/home/lhy/ROMS`:

```bash
python3 Data_pre/scripts/validation/validate_staged_data.py \
  --case-name FDNPP --ocean-source glorys12v1
python3 Data_pre/scripts/validation/validate_roms_ready_inputs.py \
  --case-name FDNPP --ocean-source glorys12v1 \
  --infile projects/FDNPP/run/ocean_fdnpp_online_continuous_my25_uvtide_glorys12v1.in
python3 Data_pre/scripts/validation/validate_formal_online_workflow.py \
  --case-name FDNPP
python3 ROMS_Run/scripts/checks/validate_run_prereqs.py \
  --case-name FDNPP --mode online_continuous_my25_uvtide
```

Launch the single task only after those checks pass:

```bash
python3 ROMS_Run/scripts/run/run_case.py \
  --case-name FDNPP --mode online_continuous_my25_uvtide
```

For a detached launch, redirect the launcher output outside the ROMS log and
keep the ROMS log at
`projects/FDNPP/logs/online_continuous_my25_uvtide.log`:

```bash
nohup python3 ROMS_Run/scripts/run/run_case.py \
  --case-name FDNPP --mode online_continuous_my25_uvtide \
  > projects/FDNPP/logs/launch_online_continuous_my25_uvtide.out 2>&1 &
```

The old split modes remain in the run configuration for compatibility with
historical results. They are not part of the normal FDNPP acceptance path.
