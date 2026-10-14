# WOLSONG readiness report

Status snapshot: `continuous online run ready; calculation not started`

## Case identity

- case name: `WOLSONG`
- project root: `/home/lhy/ROMS/projects/WOLSONG`
- domain: `129.30` to `130.40 E`, `35.268` to `36.168 N`
- active grid: `input/roms_grid_bathy_500m_smoothed.nc`
- grid: `xi_rho=201`, `eta_rho=203`, `Lm=199`, `Mm=201`
- ocean source: `GLORYS12V1`
- vertical levels: `N=40`
- formal continuous window: `2024-10-01T00:00:00` to `2026-01-01T00:00:00`
- formal result window: `2025-01-01T00:00:00` to `2026-01-01T00:00:00`
- source amount: `38.7 TBq/year` (`1.22716895e6 Bq/s`)

## Prepared inputs

- smoothed 500 m ROMS grid: `ready` (`Hmin=10 m`)
- GLORYS initial and boundary forcing: `ready` for the full continuous window
- ERA5 atmosphere and radiation: `ready` for the full continuous window
- corrected TPXO9 complex elevation and UV subset: `ready`
- ROMS tide file with OTPS phase metadata: `ready`
- continuous source: `ready`; exactly zero before `2025-01-01`
- continuous ROMS `.in`: `ready`; `NRREC=0`, initial time `2024-10-01`

## Source placement

- rule: `nearest_final_roms_wet_cell`
- reference: provisional WOLSONG facility coordinate
- snapped RHO cell: `xi=34`, `eta=101`
- snapped location: `129.487000 E`, `35.718000 N`
- snapped depth: `21.066 m`
- snap distance: `1.027 km` (below the `5 km` warning threshold)

## Tide and build status

- `SSH_TIDES`: enabled
- `UV_TIDES`: enabled
- `RAMP_TIDES`: enabled once at the start of the continuous task
- `TIDES_DATE`: enabled
- online executable: `/home/lhy/ROMS/projects/WOLSONG/bin/romsM_wolsong_online_my25_uvtide`
- calculation: not started by this preparation task

## Validation records

- staged data and deep staged data: `passed`
- ROMS-ready inputs: `passed`
- formal online pre-run workflow: `passed`
- run prerequisites: `passed`
- build plan and online executable rebuild: `passed`
- `git diff --check` and full Python compilation: `passed`

## Workflow contract

The first three months are a configurable preproduction window inside one
continuous task, not a separate cold-start job. Restart files are recovery
checkpoints only; there is no production handoff or second executable. The
continuous output is post-processed from `2025-01-01` through `2026-01-01`.

The `1 m3/s` carrier transport is a numerical placeholder, and the source
coordinate remains provisional. Raw external data and generated products are
not committed to Git.
