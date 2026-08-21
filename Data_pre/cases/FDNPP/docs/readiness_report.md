# FDNPP Readiness Report

Case identity:

- case name: `FDNPP`
- project root: `/home/lhy/ROMS/projects/FDNPP`
- simulation window: `2025-01-01 00:00:00` to `2026-01-01 00:00:00`
- ocean source: `GLORYS12V1`
- vertical levels: `N=40`

Upstream data status:

- bathymetry: offline GEBCO subset from `/workspace/GEBCO/GEBCO_2026.nc`
- ocean: GLORYS12V1 raw static, initial, and boundary products are staged
- atmosphere: ERA5 staged products present under `data/raw/atmosphere/`
- tides: TPXO staged product present under `data/raw/tides/`
- source discharge: staged CSV present under `data/raw/source/`

Staged raw status:

- expected `data/raw/...` products present: `yes for staged source products`
- `validate_staged_data.py`: `pass for GLORYS12V1 ocean products`
- `validate_staged_data_deep.py`: `pass for GLORYS12V1 ocean products`

ROMS-ready status:

- grid generated: `yes`
- smoothing or bathymetry audit completed: `not recorded here`
- initial condition generated: `yes; canonical source-suffixed output generated`
- boundary condition generated: `yes; canonical source-suffixed output verified`
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

- source-unsuffixed ocean inputs are retained compatibility products; the active run configuration uses canonical GLORYS filenames
- the radioactive-decay branch still needs its decay executable
- the default `pilot_1day` mode still needs its short-window forcing files and default executable
- `staged_download_config.json` and `staged_data_manifest.csv` describe the explicit HYCOM fallback chain, not the active default

Handoff rule:

- this report marks the end of `Data_pre` for workflow verification
- ROMS compilation and actual model execution belong to the downstream run layer
