# Readiness Report

`Data_pre` ends by handing a case off to the ROMS run layer.

That handoff should be recorded as a case-level readiness report. The report can be Markdown, plain text, or another lightweight human-readable format kept under the case docs or run directory.

Minimum contents:

- case identity
  - case name
  - project root
  - simulation start and stop time
- upstream data status
  - bathymetry source
  - ocean source
  - atmosphere source
  - tides source
  - source discharge input
- staged raw status
  - expected `data/raw/...` products present
  - staged validation passed
  - deep staged validation passed
- ROMS-ready status
  - grid generated
  - bathymetry smoothing or audit status
  - `ini/bry/atm/rad/tides/source` products generated
  - ROMS-ready validation passed
- run handoff status
  - `.in` file generated
  - important output filenames listed explicitly
  - known limitations listed explicitly

Completion rule:

- a case is considered complete inside `Data_pre` when raw data are downloaded or staged, ROMS-ready inputs are generated, validations pass, and the run file has been assembled
- a case is not considered complete merely because a download started
- a case can still be complete inside `Data_pre` even though ROMS has not yet been compiled or run

Out of scope for the readiness report:

- ROMS executable build status
- MPI launch commands
- runtime blow-up diagnosis
- timestep or stability tuning during actual integration
