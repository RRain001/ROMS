# WOLSONG HTO 4000 Bq/L scenario

This independent scenario retains the WOLSONG baseline's **38.7 TBq/year**
liquid-tritium activity and changes the ROMS carrier transport so the source
concentration is **4000 Bq/L**. The 4000 Bq/L value is supplied by the user
for this sensitivity experiment; it has not been verified as the applicable
legal discharge limit. A 2024 Korean Nuclear Safety and Security Commission
Wolsong meeting record instead describes 40000 Bq/L as the tritium
discharge-management concentration criterion:
https://www.nssc.go.kr/attach/namo/files/000002/20240925181804117_2J8H7Q4X.pdf

## Source calculation

For a constant 365-day release:

```
activity rate = 38.7e12 Bq / (365 * 86400 s) = 1,227,168.9497716895 Bq/s
source concentration = 4000 Bq/L = 4,000,000 Bq/m3
carrier transport = activity rate / source concentration
                  = 0.3067922374429224 m3/s = 1104.4520547945206 m3/h
```

The parent WOLSONG case uses 1 m3/s and 1227.1689497716895 Bq/L for the
same activity rate. The carrier transport is a modeling assumption, not a
verified plant effluent flow. Changing it also changes the water-source term,
so local hydrodynamics and near-source concentrations can differ. The active
tracer represents HTO with no radioactive decay, as in the parent case.

The source remains at the nearest final-grid wet cell, zero-based
`xi=34, eta=101`. The continuous source is zero from 2024-10-01 until
2025-01-01, then holds the activity rate and concentration above through
2026-01-01. Annual release is 38.7 TBq over the 2025 production interval.

## Case organization and rerun

Authoritative configuration: `Data_pre/cases/WOLSONG_H3_4000BQL/config`.
Generated inputs and outputs: `projects/WOLSONG_H3_4000BQL`.
The grid, ocean, atmosphere, radiation and tide NetCDF inputs are symlinks
to the parent WOLSONG case. The source NetCDF files, ROMS `.in` files, logs,
and outputs belong to this scenario. The copied executable uses the same
ROMS CPP physics as the parent; it does not need source-code changes.

The full continuous `.in` file integrates 2024-10-01 to 2026-01-01.
This case is prepared for validation and a one-day pilot. The earlier user
instruction to hold the full 2025 calculation remains in force; do not run
`online_continuous_my25_uvtide` until that instruction is lifted.

```bash
python3 Data_pre/scripts/source/create_river_source_production.py --case-name WOLSONG_H3_4000BQL --formal-continuous --profile online_my25_uvtide --scenario-tag scenario_baseline
python3 Data_pre/scripts/source/create_river_source_production.py --case-name WOLSONG_H3_4000BQL --profile online_my25_uvtide --start 2025-01-01T00:00:00 --stop 2026-01-01T00:00:00 --scenario-tag scenario_baseline
python3 Data_pre/scripts/validation/validate_roms_ready_inputs.py --case-name WOLSONG_H3_4000BQL
python3 ROMS_Run/scripts/checks/validate_run_prereqs.py --case-name WOLSONG_H3_4000BQL --mode pilot_1day
python3 ROMS_Run/scripts/run/run_case.py --case-name WOLSONG_H3_4000BQL --mode pilot_1day --dry-run
```

To reproduce a legal-compliance scenario, first verify the applicable
concentration criterion and obtain the actual effluent discharge flow and
release schedule. The present setup is a controlled source-term comparison.
