# WOLSONG case

This is the WOLSONG coastal ROMS passive-tracer case, constructed by reusing
the LAHAGUE workflow while keeping WOLSONG-specific configuration and outputs
independent.

Case contract:

- domain: `129.30` to `130.40 E`, `35.268` to `36.168 N`
- horizontal resolution: `500 m` (formal grid, not a pilot coarsening)
- vertical levels: `N=40`
- default ocean source: `GLORYS12V1`
- continuous formal integration: `2024-10-01` to `2026-01-01`
- formal result window: `2025-01-01` to `2026-01-01`
- source: `38.7 TBq/year` total-activity-equivalent passive tracer
- carrier transport: `1 m3/s` numerical concentration-conversion placeholder

The selected extent intentionally places the WOLSONG facility near the west
edge of the computational water domain. Land cells are excluded by the final
ROMS mask.

The configured facility coordinate is only a reference. The active source is
snapped after final grid generation to the nearest eligible `mask_rho=1`,
`h >= Hmin` RHO cell. The current final-grid placement is `xi=34, eta=101`,
`129.487000 E, 35.718000 N`, depth `21.066 m`, snap distance `1.027 km`.

The source rate is centrally converted to approximately
`1.22716895e6 Bq/s` using 365 days/year. The first version has one passive
tracer and no radioactive decay.

The first three months are a zero-source preproduction window in the same
task; restart files are recovery checkpoints, not a production handoff. See
`docs/workflow.md` for the preparation sequence and
`docs/readiness_report.md` for the current data state.
