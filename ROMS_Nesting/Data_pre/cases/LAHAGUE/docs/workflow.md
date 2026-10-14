# LAHAGUE workflow

Runtime configuration is authoritative in:

```text
/home/lhy/ROMS/Data_pre/cases/LAHAGUE/config
```

Generated data and inputs belong under:

```text
/home/lhy/ROMS/projects/LAHAGUE
```

## Design contract

- active rebuild domain: `-3.00` to `-1.55 E`, `49.27` to `50.05 N`
- boundary-mask acceptance rule: each outer edge must be all wet/all dry or contain at most one wet/dry transition; `wet → dry → wet` and `dry → wet → dry` are rejected
- horizontal grid: `500 m`
- vertical grid: `N=40`, `Vtransform=2`, `Vstretching=4`
- ocean: `GLORYS12V1`
- atmosphere: ERA5
- tides: TPXO9 elevation plus UV ellipse variables
- source model: nearest eligible final ROMS wet RHO cell

The source reference point is provisional. It must not be interpreted as a
confirmed marine outfall. Re-run source placement after any final-grid,
mask-cleaning, or smoothing change.

## Formal online continuous workflow

The default formal mode is one uninterrupted integration from
`2024-10-01T00:00:00` through `2026-01-01T00:00:00`. The first three months
are a configurable preproduction window, not a separate spin-up task:

- GLORYS initial and boundary fields cover the full continuous window
- the passive-tracer source is exactly zero before `2025-01-01`
- the source switches to `11.15 PBq/year` at `2025-01-01`
- `NRREC=0` and the initial field is the `2024-10-01` GLORYS initial file
- `RAMP_TIDES` is applied once at the beginning by the same executable
- history, daily averages, and 5-day restart checkpoints cover the full run

Restart files are recovery checkpoints only. They are not a formal stage
handoff, and no manual production launch is required. Post-processing selects
`2025-01-01` through `2026-01-01` from the continuous outputs.

This is a physical GLORYS-initialized start, not a motionless ocean. Only the
passive tracer starts at zero during spin-up.

## Local preparation

The global GEBCO, GSHHG, and TPXO resources already present on the host are
staged locally. Do not redownload them. Prepare them in this order:

```bash
python3 Data_pre/scripts/bathymetry/stage_and_subset_bathymetry.py --case-name LAHAGUE
python3 Data_pre/scripts/bathymetry/create_grid_from_bathymetry.py --case-name LAHAGUE --resolution-key pilot
python3 Data_pre/scripts/bathymetry/clean_roms_mask.py --case-name LAHAGUE
python3 Data_pre/scripts/bathymetry/smooth_bathymetry.py --case-name LAHAGUE
```

After the final smoothed grid exists, regenerate the continuous source and
corrected TPXO tide inputs:

```bash
python3 Data_pre/scripts/source/create_river_source_production.py --case-name LAHAGUE --formal-continuous --profile online_my25_uvtide
python3 Data_pre/scripts/tides/stage_tpxo_elevation_atlas.py --case-name LAHAGUE --include-uv \
  --output projects/LAHAGUE/data/raw/tides/tpxo9_lahague_20241001_20260101.nc
python3 Data_pre/scripts/tides/create_tides_from_tpxo.py --case-name LAHAGUE \
  --src projects/LAHAGUE/data/raw/tides/tpxo9_lahague_20241001_20260101.nc \
  --profile online_my25_uvtide --require-uv \
  --output projects/LAHAGUE/input/roms_tides_lahague_online_my25_uvtide.nc
```

## Remote data preparation

GLORYS, atmosphere, and radiation data must cover the single window
`2024-10-01` to `2026-01-01`. Run the staged downloader with this explicit
window and `--resume`; its static product is shared by the run.

GLORYS daily means are centered at `12:00:00`; ROMS-ready files use the
`daily_mean_to_day_start` conversion and therefore start model days at
`00:00:00`.

The canonical staged TPXO subset is
`data/raw/tides/tpxo9_lahague_20241001_20260101.nc`. It contains the TPXO
complex constants, uses the OTPS `-angle(Re+i Im)` phase convention, and is
interpolated in complex space before ROMS fields are reconstructed.

## Source amount and units

The configured amount is `11.15 PBq/year`, converted centrally to:

```text
3.535641806e8 Bq/s
```

The first version treats this as one total-activity-equivalent tracer with no
decay. The `1 m3/s` transport is only a numerical carrier for converting
activity flux to concentration. A later study may replace it with measured or
scenario-based carrier transport.

## Validation and dry-run

```bash
python3 Data_pre/scripts/validation/validate_staged_data.py --case-name LAHAGUE
python3 Data_pre/scripts/validation/validate_staged_data_deep.py --case-name LAHAGUE
python3 Data_pre/scripts/validation/validate_roms_ready_inputs.py --case-name LAHAGUE
python3 Data_pre/scripts/validation/validate_formal_online_workflow.py --case-name LAHAGUE --profile online_my25_uvtide --phase pre-run
python3 ROMS_Build/scripts/build/show_build_plan.py --case-name LAHAGUE --variant online_my25_uvtide
python3 ROMS_Run/scripts/checks/validate_run_prereqs.py --case-name LAHAGUE --mode online_continuous_my25_uvtide
python3 ROMS_Run/scripts/run/run_case.py --case-name LAHAGUE --mode online_continuous_my25_uvtide --dry-run
```

The decay build and input are explicit alternatives only:

```bash
python3 Data_pre/scripts/run_support/create_pilot_infile.py \
  --case-name LAHAGUE --ocean-source glorys12v1 --forcing-mode external \
  --mode online_production_1y_my25_uvtide_decay_from_spinup
python3 ROMS_Build/scripts/build/build_roms_case.py \
  --case-name LAHAGUE --variant online_my25_uvtide_decay
```

These commands validate and prepare the run; this preparation workflow does
not start the LAHAGUE calculation. The decay build remains a separate legacy
alternative and is not the default continuous executable.
