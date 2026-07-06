# git_commit_plan_online_my25_uvtide

## 1. Initial git status summary

Audit commands run before any commit:

```bash
git status --short
git diff --stat
git diff --check
git diff --name-status
```

Initial result:

- 27 code changes in scope:
  - 23 modified tracked files
  - 4 untracked validation/report scripts
- `git diff --check` was clean.
- No large runtime outputs were present in tracked changes.
- `projects/` is ignored by `.gitignore`, so `projects/FDNPP/output`, `logs`, `build`, `bin`, and `projects/FDNPP/reports` were not accidentally staged.

Ignored large outputs confirmed under `projects/FDNPP/output` included:

- `dia_fdnpp_online_7d_online_my25_uvtide.nc` about 50.8 GB
- `dia_fdnpp_online_month_online_my25_uvtide.nc` about 35.2 GB at audit time
- `avg_fdnpp_online_7d_online_my25_uvtide.nc` about 16.7 GB
- `his_fdnpp_online_7d_online_my25_uvtide.nc` about 11.6 GB

These were intentionally left untracked.

## 2. Classification of the 27 changes

### A. General reusable code and script changes

- `Data_pre/core/case_naming.py`
- `Data_pre/core/roms_preprocessing_utils.py`
- `Data_pre/docs/case_schema.md`
- `Data_pre/docs/workflow_generic.md`
- `Data_pre/impl/preprocessing/create_ocean_bry_from_hycom.py`
- `Data_pre/impl/preprocessing/create_ocean_ini_from_hycom.py`
- `Data_pre/impl/preprocessing/create_pilot_infile.py`
- `Data_pre/impl/preprocessing/create_river_source_production.py`
- `Data_pre/impl/preprocessing/create_source_timeseries.py`
- `ROMS_Run/core/run_context.py`
- `Data_pre/cases/_template/config/project_parameters.json`
- `Data_pre/cases/_template/config/roms_build_config.json`
- `Data_pre/cases/_template/config/roms_run_config.json`
- `Data_pre/cases/fukushima_202401_50m/config/project_parameters.json`
- `Data_pre/cases/fukushima_202401_50m/config/roms_build_config.json`
- `Data_pre/cases/fukushima_202401_50m/config/roms_run_config.json`

### B. ROMS source-level change

- `roms_src/roms/ROMS/Nonlinear/hmixing.F`

This changes `SmagorCoef` from `0.1_r8` to `0.2_r8` and affects all ROMS cases built from this source tree.

### C. FDNPP case configuration changes

- `Data_pre/cases/FDNPP/config/project_parameters.json`
- `Data_pre/cases/FDNPP/config/roms_build_config.json`
- `Data_pre/cases/FDNPP/config/roms_run_config.json`

### D. New or updated input metadata / validation helpers

- `Data_pre/impl/preprocessing/create_tides_from_tpxo.py`
- `Data_pre/impl/preprocessing/stage_tpxo_elevation_atlas.py`
- `Data_pre/impl/preprocessing/validate_roms_ready_inputs.py`
- `Data_pre/impl/preprocessing/audit_online_profile.py`
- `Data_pre/impl/preprocessing/validate_online_7d.py`
- `Data_pre/scripts/validation/audit_online_profile.py`
- `Data_pre/scripts/validation/validate_online_7d.py`

### E. Reports

Selected report outputs committed with force-add because `projects/` is ignored:

- `projects/FDNPP/reports/fdnpp_online_my25_uvtide_reconfig.md`
- `projects/FDNPP/reports/fdnpp_online_my25_uvtide_reconfig.json`
- `projects/FDNPP/reports/fdnpp_online_my25_uvtide_7d_validation.md`
- `projects/FDNPP/reports/fdnpp_online_my25_uvtide_7d_validation.json`

Additional ignored reports left uncommitted:

- `projects/FDNPP/reports/fdnpp_online_reconfig_preread.md`
- `projects/FDNPP/reports/fdnpp_online_reconfig_preread.json`
- `projects/FDNPP/reports/online_my25_uvtide_uv_tides_blocked.md`
- `projects/FDNPP/reports/online_my25_uvtide_uv_tides_blocked.json`
- older `fdnpp_case_config_audit.*`

### F. Explicitly non-committed content

- all files under `projects/FDNPP/output/`
- all files under `projects/FDNPP/logs/`
- all files under `projects/FDNPP/build/`
- all files under `projects/FDNPP/bin/`
- all `__pycache__/`
- `.pydeps/`
- `.venv_fukushima/`

### G. Other / unable to classify

- none

## 3. Content and safety checks

- No large NetCDF runtime outputs were staged.
- No `output/`, `logs/`, `build/`, or `bin/` products were staged.
- No `*.pyc`, `__pycache__`, or scratch files were staged.
- The TPXO atlas path is intentionally referenced through `/workspace/tpxo9_atlas_v5`.
- FDNPP `22 TBq/year` did not enter shared defaults. It remains case-scoped in FDNPP configuration and source products. A hardcoded source-rate constant that appeared in the 7-day validation script was removed before commit; the script now derives the rate from the river file.

## 4. Commits created

1. `5c2d2a3` `Add reusable online MY25 UV-tide tracer profile`
2. `2222c88` `Generate TPXO UV tide forcing for online tracer cases`
3. `55569b3` `Set default Smagorinsky coefficient for tracer profiles`
4. `a8da3d3` `Add FDNPP online MY25 UV-tide tracer case configuration`
5. `0b62123` `Document FDNPP online tracer validation results`

## 5. What each commit contains

### `5c2d2a3` Add reusable online MY25 UV-tide tracer profile

Contains:

- reusable `online_my25_uvtide` naming/profile support
- default `N=40`, `theta_s=7.0`, `theta_b=0.1`, `Tcline=200`
- generic MY25 / Smagorinsky / SSH+UV tide config defaults
- profile-aware `.in`, ini, bdy, source naming
- run prereq content validation
- template and `fukushima_202401_50m` adoption

### `2222c88` Generate TPXO UV tide forcing for online tracer cases

Contains:

- TPXO `u_*_tpxo9_atlas_30_v5` current atlas ingestion
- `tide_Cmax`, `tide_Cmin`, `tide_Cangle`, `tide_Cphase`
- blocked-report behavior when UV tide data is missing
- `--require-uv-tides` ready-input validation

### `55569b3` Set default Smagorinsky coefficient for tracer profiles

Contains:

- ROMS source-level `SmagorCoef = 0.2_r8`

Impact:

- global to all cases built from this source tree
- not case-local
- kept separate on purpose for review and rollback

### `a8da3d3` Add FDNPP online MY25 UV-tide tracer case configuration

Contains:

- FDNPP project parameter defaults for the online profile
- FDNPP build variant `online_my25_uvtide`
- FDNPP run modes `online_6h`, `online_3d`, `online_month`

### `0b62123` Document FDNPP online tracer validation results

Contains:

- audit and 7-day validation scripts
- script entrypoints
- reconfiguration and 7-day validation reports
- this git commit planning report

## 6. Validation commands run

### Global validation before commit split

```bash
python3 Data_pre/scripts/validation/validate_staged_data.py --case-name FDNPP --ocean-source hycom
python3 Data_pre/scripts/validation/validate_roms_ready_inputs.py --case-name FDNPP --profile online_my25_uvtide --require-uv-tides
python3 ROMS_Build/scripts/build/show_build_plan.py --case-name FDNPP --variant online_my25_uvtide
python3 ROMS_Run/scripts/checks/validate_run_prereqs.py --case-name FDNPP --mode online_6h
python3 ROMS_Run/scripts/checks/validate_run_prereqs.py --case-name FDNPP --mode online_3d
python3 ROMS_Run/scripts/checks/validate_run_prereqs.py --case-name FDNPP --mode online_month
```

Observed status:

- staged data validation: OK
- ROMS-ready inputs: completed and printed expected time ranges
- build plan for `online_my25_uvtide`: OK
- run prereqs for `online_6h`, `online_3d`, `online_month`: OK, with overwrite warnings for already existing output files

### Per-commit minimum checks

Before each commit:

- `git diff --check`

Additional static checks:

```bash
python3 -m py_compile \
  Data_pre/core/case_naming.py \
  Data_pre/core/roms_preprocessing_utils.py \
  Data_pre/impl/preprocessing/create_ocean_bry_from_hycom.py \
  Data_pre/impl/preprocessing/create_ocean_ini_from_hycom.py \
  Data_pre/impl/preprocessing/create_pilot_infile.py \
  Data_pre/impl/preprocessing/create_river_source_production.py \
  Data_pre/impl/preprocessing/create_source_timeseries.py \
  ROMS_Run/core/run_context.py

python3 -m py_compile \
  Data_pre/impl/preprocessing/create_tides_from_tpxo.py \
  Data_pre/impl/preprocessing/stage_tpxo_elevation_atlas.py \
  Data_pre/impl/preprocessing/validate_roms_ready_inputs.py

python3 -m py_compile \
  Data_pre/impl/preprocessing/audit_online_profile.py \
  Data_pre/impl/preprocessing/validate_online_7d.py \
  Data_pre/scripts/validation/audit_online_profile.py \
  Data_pre/scripts/validation/validate_online_7d.py
```

## 7. Files intentionally not committed

- all live month-run outputs and logs
- all build and binary artifacts
- preread and transient blocked UV-tide reports

Reason:

- too large, generated, transient, or redundant with the final reports

## 8. Remaining uncommitted files after commit sequence

- expected to be none in tracked scope
- ignored runtime products remain under `projects/`

## 9. Follow-up on `online_month`

- `online_month` was left running in the background during this cleanup
- a later follow-up commit may be appropriate for month-scale validation results once the run finishes and the final report is written

## 10. Manual attention items

- The Smagorinsky coefficient change is global. Reviewers should confirm that a ROMS source-level default is acceptable for all active cases in this branch.
- `projects/FDNPP/reports/*` had to be force-added because `projects/` is globally ignored.
- Existing output files mean rerunning `online_6h`, `online_3d`, or `online_month` with the same names will overwrite products unless the operator renames or archives them first.
