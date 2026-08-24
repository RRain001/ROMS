# WOLSONG workflow

Runtime configuration is authoritative in:

```text
/home/lhy/ROMS/Data_pre/cases/WOLSONG/config
```

Generated data and inputs belong under:

```text
/home/lhy/ROMS/projects/WOLSONG
```

## Design contract

- domain: `129.30` to `130.40 E`, `35.268` to `36.168 N`
- horizontal grid: `500 m`
- vertical grid: `N=40`, `Vtransform=2`, `Vstretching=4`
- ocean: `GLORYS12V1`
- atmosphere: `ERA5`
- tides: `TPXO9` elevation plus UV ellipse variables
- source: nearest eligible final ROMS wet RHO cell

The final grid currently has `xi_rho=201`, `eta_rho=203`, `Lm=199`, `Mm=201`.
The selected range keeps the facility near the west side of the water domain;
land cells are excluded by the mask.

## Formal online continuous workflow

The default formal mode is one uninterrupted integration from
`2024-10-01T00:00:00` through `2026-01-01T00:00:00`. The first three months
are a configurable preproduction window, not a separate spin-up task:

- GLORYS initial and boundary fields cover the full continuous window
- the passive-tracer source is exactly zero before `2025-01-01`
- the source switches to `38.7 TBq/year` at `2025-01-01`
- `NRREC=0` and the initial field is the `2024-10-01` GLORYS initial file
- `RAMP_TIDES` is applied once at the beginning by the same executable
- history, daily averages, and 5-day restart checkpoints cover the full run

Restart files are recovery checkpoints only. They are not a formal stage
handoff, and no manual production launch is required. Post-processing selects
`2025-01-01` through `2026-01-01` from the continuous outputs.

The carrier transport is `1 m3/s` and is a numerical placeholder used to turn
the activity flux into a source concentration. The passive tracer has no
decay in the active profile.

## Local preparation

The host-provided GEBCO, GSHHG, and TPXO resources are reused. The bathymetry
and grid sequence is:

```bash
python3 Data_pre/scripts/bathymetry/stage_and_subset_bathymetry.py --case-name WOLSONG
python3 Data_pre/scripts/bathymetry/create_grid_from_bathymetry.py --case-name WOLSONG --resolution-key target
python3 Data_pre/scripts/bathymetry/clean_roms_mask.py --case-name WOLSONG
python3 Data_pre/scripts/bathymetry/smooth_bathymetry.py --case-name WOLSONG
```

After the final grid exists, regenerate grid-dependent files:

```bash
python3 Data_pre/scripts/source/create_source_timeseries.py --case-name WOLSONG
python3 Data_pre/scripts/source/create_river_source_production.py --case-name WOLSONG --formal-continuous --profile online_my25_uvtide
python3 Data_pre/scripts/tides/stage_tpxo_elevation_atlas.py --case-name WOLSONG --include-uv \
  --output projects/WOLSONG/data/raw/tides/tpxo9_wolsong_20241001_20260101.nc
python3 Data_pre/scripts/tides/create_tides_from_tpxo.py --case-name WOLSONG \
  --src projects/WOLSONG/data/raw/tides/tpxo9_wolsong_20241001_20260101.nc \
  --profile online_my25_uvtide --require-uv \
  --output projects/WOLSONG/input/roms_tides_wolsong_online_my25_uvtide.nc
```

The current source placement is `xi=34`, `eta=101`, at
`129.487000 E, 35.718000 N`, depth `21.066 m`, with a snap distance of
`1.027 km`.

## Remote data preparation

GLORYS, atmosphere, and radiation data must cover the single window
`2024-10-01` to `2026-01-01`. Logs are stored in `projects/WOLSONG/logs/`;
reruns should use `--resume` so completed chunks are preserved.

GLORYS daily means are centered at `12:00:00`; the ROMS-ready conversion must
apply the configured `daily_mean_to_day_start` policy. Do not infer time
coverage from filenames alone.

Once raw files exist, create one ROMS-ready file for each forcing type covering
the full window. There is no production restart prerequisite.

## Validation and build handoff

Run these after the raw and ROMS-ready files have been generated:

```bash
python3 Data_pre/scripts/validation/validate_staged_data.py --case-name WOLSONG
python3 Data_pre/scripts/validation/validate_staged_data_deep.py --case-name WOLSONG
python3 Data_pre/scripts/validation/validate_roms_ready_inputs.py --case-name WOLSONG
python3 Data_pre/scripts/validation/validate_formal_online_workflow.py --case-name WOLSONG --profile online_my25_uvtide --phase pre-run
python3 ROMS_Build/scripts/build/show_build_plan.py --case-name WOLSONG --variant online_my25_uvtide
python3 ROMS_Run/scripts/checks/validate_run_prereqs.py --case-name WOLSONG --mode online_continuous_my25_uvtide
python3 ROMS_Run/scripts/run/run_case.py --case-name WOLSONG --mode online_continuous_my25_uvtide --dry-run
```

These commands validate and prepare the run; this preparation workflow does
not start the WOLSONG calculation.
