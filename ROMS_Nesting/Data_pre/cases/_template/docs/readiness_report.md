# Case Readiness Report Template

Case identity:

- case name: `<case_name>`
- project root: `/home/lhy/ROMS/projects/<case_name>`
- simulation window: `<start>` to `<stop>`
- ocean source: `<GLORYS12V1 or explicit override>`
- vertical levels: `<N>`

Upstream data status:

- bathymetry: `<dataset and path>`
- ocean: `<dataset and staged files>`
- atmosphere: `<dataset and staged files>`
- tides: `<dataset and staged files>`
- source discharge: `<csv or other source input>`

Staged raw status:

- expected `data/raw/...` products present: `yes/no`
- `validate_staged_data.py`: `pass/fail`
- `validate_staged_data_deep.py`: `pass/fail`

ROMS-ready status:

- grid generated: `yes/no`
- smoothing or bathymetry audit completed: `yes/no`
- initial condition generated: `yes/no`
- boundary condition generated: `yes/no`
- atmosphere forcing generated: `yes/no`
- radiation forcing generated: `yes/no`
- tides forcing generated: `yes/no`
- source or river forcing generated: `yes/no`
- `validate_roms_ready_inputs.py`: `pass/fail`

Run handoff status:

- `.in` file generated: `yes/no`
- key run-layer input filenames listed: `yes/no`
- known limitations listed: `yes/no`

Known limitations:

- `<write any remaining scientific or operational limitation here>`

Handoff rule:

- this report marks the end of `Data_pre`
- ROMS compilation and actual model execution start after this handoff
