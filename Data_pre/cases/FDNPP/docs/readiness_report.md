# FDNPP Readiness Report

Case identity:

- case name: `FDNPP`
- project root: `/home/lhy/ROMS/projects/FDNPP`
- simulation window: `2025-01-01 00:00:00` to `2025-02-01 00:00:00`

Upstream data status:

- bathymetry: offline GEBCO subset from `/workspace/GEBCO/GEBCO_2026.nc`
- ocean: HYCOM staged products present under `data/raw/ocean/`
- atmosphere: ERA5 staged products present under `data/raw/atmosphere/`
- tides: TPXO staged product present under `data/raw/tides/`
- source discharge: staged CSV present under `data/raw/source/`

Staged raw status:

- expected `data/raw/...` products present: `yes`
- `validate_staged_data.py`: `pass`
- `validate_staged_data_deep.py`: `pass`

ROMS-ready status:

- grid generated: `yes`
- smoothing or bathymetry audit completed: `not recorded here`
- initial condition generated: `yes`
- boundary condition generated: `yes`
- atmosphere forcing generated: `yes`
- radiation forcing generated: `yes`
- tides forcing generated: `yes`
- source or river forcing generated: `yes`
- `validate_roms_ready_inputs.py`: `pass`

Run handoff status:

- `.in` file generated: `yes`
- key run-layer input filenames listed: `yes`
- known limitations listed: `yes`

Known limitations:

- the current HYCOM boundary workflow proof uses short-window boundary coverage rather than a finalized production monthly boundary product

Handoff rule:

- this report marks the end of `Data_pre` for workflow verification
- ROMS compilation and actual model execution belong to the downstream run layer
