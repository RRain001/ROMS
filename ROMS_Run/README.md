# ROMS_Run

`ROMS_Run` is the shared ROMS execution layer that sits beside `Data_pre` and `ROMS_Build`.

Responsibilities:

- resolve cases with the same `--case-name` / `--case-root` style used by `Data_pre`
- load runtime settings from `Data_pre/cases/<case_name>/config/roms_run_config.json`
- validate run layout, executable presence, `.in` file metadata, and input-file references
- launch smoke, pilot, or production runs
- manage run logs and archive run summaries

Non-goals:

- compiling ROMS source code
- generating ROMS-ready forcing files
- deciding scientific tuning strategy after a runtime instability

Case products remain under `projects/<case_name>/`.
