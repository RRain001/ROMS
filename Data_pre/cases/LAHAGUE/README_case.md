# LAHAGUE case

This is the independent La Hague core-region ROMS case. It is parallel to
FDNPP and does not use FDNPP runtime files.

Case contract:

- active rebuild domain: `-3.00` to `-1.55 E`, `49.27` to `50.05 N`
- boundary rule: west/north all wet; east `dry → wet`; south `wet → dry`
- horizontal resolution: `500 m`
- vertical levels: `N=40`
- default ocean source: `GLORYS12V1`
- continuous formal integration: `2024-10-01` to `2026-01-01`
- formal result window: `2025-01-01` to `2026-01-01`
- source: `11.15 PBq/year` total-activity-equivalent passive tracer

The configured source coordinate is only a reference location. Source files
must be generated after the final ROMS grid is fixed and must use the nearest
eligible `mask_rho=1`, `h >= Hmin` RHO cell. The snapped source location and
grid path are recorded in source NetCDF metadata.

The `1 m3/s` carrier is a numerical concentration-conversion placeholder,
following the current FDNPP workflow. It is not a claim about the actual
marine outfall flow.

The first three months are a zero-source preproduction window in the same
task; restart files are recovery checkpoints, not a production handoff. See
`docs/workflow.md` for the continuous staged-data and run preparation sequence.
