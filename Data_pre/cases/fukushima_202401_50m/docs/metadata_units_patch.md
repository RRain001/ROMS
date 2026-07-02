# HTO Tracer Metadata Patch

Date: 2026-06-25

Remote project:

- `/home/lhy/ROMS/projects/fukushima_202401_50m`

## Change

The project-local `run/varinfo.yaml` was patched so inert tracer metadata describes HTO activity concentration rather than generic dye mass concentration.

Backup retained on the remote host:

- `run/varinfo.yaml.before_bq_units_20260625`

Patched entries:

- `river_dye_`
- `dye_`
- `dye_west_`
- `dye_east_`
- `dye_south_`
- `dye_north_`

## Verification

The 5-step smoke run was rerun after the patch:

- command: `./run/run_smoke.sh`
- latest completion: `ROMS: DONE... Thursday - June 25, 2026 -  4:42:13 PM`
- output: `output/his_fukushima_smoke.nc`

Verified `dye_01` output attributes:

```text
standard_name = activity_concentration_of_HTO_01
long_name = HTO activity concentration, type 01
units = Bq meter-3
field = HTO activity concentration01
shape = (2, 21, 448, 358)
min = -0.04503560811281204
max = 802.3632202148438
```

## Remaining Caveat

The metadata is now aligned with the HTO source unit, but the current run remains an idealized plumbing pilot. The negative minimum is small and appears in the technical smoke output; production interpretation requires realistic advection, mixing, bathymetry, boundary conditions and numerical diagnostics.
