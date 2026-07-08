# Formal Online Passive Tracer Workflow

## Generic Definition

- spin-up duration: `3 months`
- spinup_start: `2024-10-01T00:00:00`
- spinup_end / production_start: `2025-01-01T00:00:00`
- production_end: `2026-01-01T00:00:00`
- spin-up is hydrodynamic adjustment before formal online tracer production.
- formal production source and optional radioactive decay are enabled only in production.
- workflow genericized: `true`
- FDNPP role: `configuration instance only; shared workflow logic is case-driven`

## History And Restart

- spin-up hot-start state comes from restart, not history.
- formal spin-up can use `history off + restart 5 d + diagnostics off` because restart is the complete model state used by production.
- required restart variables: `zeta`, `ubar`, `vbar`, `u`, `v`, `temp`, `salt`, `dye_01`, `ocean_time`, plus turbulence variables when required by the compiled physics.

## Run Modes

- spin-up: `online_spinup_3mo_my25_uvtide`
- production no-decay: `online_production_1y_my25_uvtide_from_spinup`
- production decay: `online_production_1y_my25_uvtide_decay_from_spinup`

## Actual Spin-up Output

- infile: `/home/lhy/ROMS/projects/FDNPP/run/ocean_fdnpp_online_spinup_3mo_my25_uvtide.in`
- NHIS: `0`
- NAVG: `0`
- NRST: `43200`
- NDIA: `0`
- history_will_write: `False`
- history variables enabled: `none`
- diagnostics_will_write: `False`
- diagnostics variables enabled: `none`
- source file: `../input/roms_rivers_fdnpp_online_spinup_3mo_my25_uvtide_zero_source.nc`
- restart file: `../output/rst_fdnpp_online_spinup_3mo_my25_uvtide.nc`

## Actual Production Output

- no-decay infile: `/home/lhy/ROMS/projects/FDNPP/run/ocean_fdnpp_online_production_1y_my25_uvtide_from_spinup.in`
- decay infile: `/home/lhy/ROMS/projects/FDNPP/run/ocean_fdnpp_online_production_1y_my25_uvtide_decay_from_spinup.in`
- NHIS: `360`
- NAVG: `8640`
- NRST: `43200`
- NDIA: `0`
- NRREC: `-1`
- ININAME: `../output/rst_fdnpp_online_spinup_3mo_my25_uvtide.nc`
- history variables enabled: `zeta`
- average variables enabled: `ubar, u, vbar, v, dye_01`
- diagnostics_will_write: `False`
- diagnostics variables enabled: `none`
- no-decay/decay output config identical: `True`
- hourly `dye_01`: `disabled`
- supported visualization: `daily mean plume maps / daily mean animation`
- unsupported visualization: `hourly dye_01 plume animation`

## Validation

- status: `ready`
- validation phase: `pre-run`
- no-decay and decay production supported: `True`
- output_config_can_be_modified_now: `True`
- spinup_can_run_now: `False`

## Current Flow Audit

- spinup_flow_supported: `partial`
- data_window_rule_supported: `true`
- zero_source_spinup_supported: `true`
- restart_hotstart_supported: `true`
- formal_minimal_output_supported: `true`
- case_specific_hardcoding_found: `False`
- note: `FDNPP may appear in case config/docs; shared workflow logic is case-driven.`

## Blocking Issues

- none

## Spin-up Input Data Blocking Issues

- raw_tides missing tide_Eamp
- raw_tides missing tide_Ephase
- raw_tides missing tide_Cmax
- raw_tides missing tide_Cmin
- raw_tides missing tide_Cangle
- raw_tides missing tide_Cphase

## Next Step

- Fix spin-up tide staging for formal online workflow
