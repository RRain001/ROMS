# FDNPP Spin-up Data Ready Report

- case: `FDNPP`
- profile: `online_my25_uvtide`
- window: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00`
- status: `ready`
- can_generate_spinup_run_mode: `True`

## Inputs

- raw_ini: `/home/lhy/ROMS/projects/FDNPP/data/raw/ocean/glorys12v1/glorys12v1_initial_20241001.nc`
  time: `2024-10-01T12:00:00` -> `2024-10-01T12:00:00` (1 records)
  dims: `time=1, depth=50, latitude=18, longitude=21`
- raw_bdy: `/home/lhy/ROMS/projects/FDNPP/data/raw/ocean/glorys12v1/glorys12v1_boundary_20241001_20250101.nc`
  time: `2024-10-01T12:00:00` -> `2025-01-01T12:00:00` (93 records)
  dims: `time=93, depth=50, latitude=18, longitude=21`
- raw_atm: `/home/lhy/ROMS/projects/FDNPP/data/raw/atmosphere/era5_atm_fdnpp_20241001_20250101.nc`
  time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (2209 records)
  dims: `time=2209, lat=6, lon=7`
- raw_rad: `/home/lhy/ROMS/projects/FDNPP/data/raw/atmosphere/era5_rad_fdnpp_20241001_20250101.nc`
  time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (2209 records)
  dims: `time=2209, lat=6, lon=7`
- raw_tides: `/home/lhy/ROMS/projects/FDNPP/data/raw/tides/tpxo9_fdnpp_20241001_20250101.nc`
  dims: `tide_period=15, lat=28, lon=35`
- ini: `/home/lhy/ROMS/projects/FDNPP/input/roms_ini_fdnpp_20241001_online_my25_uvtide.nc`
  ocean_time: `2024-10-01T00:00:00` -> `2024-10-01T00:00:00` (1 records)
  dims: `ocean_time=1, s_rho=40, eta_rho=190, xi_rho=201, eta_u=190, xi_u=200, eta_v=189, xi_v=201`
- bdy: `/home/lhy/ROMS/projects/FDNPP/input/roms_bdy_fdnpp_20241001_20250101_online_my25_uvtide.nc`
  zeta_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (93 records)
  v2d_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (93 records)
  v3d_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (93 records)
  temp_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (93 records)
  salt_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (93 records)
  dye_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (93 records)
  dims: `zeta_time=93, v2d_time=93, v3d_time=93, temp_time=93, salt_time=93, dye_time=93, eta_rho=190, xi_rho=201, eta_u=190, xi_u=200, eta_v=189, xi_v=201, s_rho=40`
- atm: `/home/lhy/ROMS/projects/FDNPP/input/roms_atm_fdnpp_20241001_20250101.nc`
  wind_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (2209 records)
  pair_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (2209 records)
  tair_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (2209 records)
  qair_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (2209 records)
  rain_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (2209 records)
  swf_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (2209 records)
  dims: `wind_time=2209, pair_time=2209, tair_time=2209, qair_time=2209, rain_time=2209, swf_time=2209, eta_rho=190, xi_rho=201`
- rad: `/home/lhy/ROMS/projects/FDNPP/input/roms_rad_fdnpp_20241001_20250101.nc`
  srf_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (2209 records)
  lrf_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (2209 records)
  dims: `srf_time=2209, lrf_time=2209, eta_rho=190, xi_rho=201`
- tides: `/home/lhy/ROMS/projects/FDNPP/input/roms_tides_fdnpp_20241001_20250101_online_my25_uvtide.nc`
  dims: `tide_period=15, eta_rho=190, xi_rho=201`
- river: `/home/lhy/ROMS/projects/FDNPP/input/roms_rivers_fdnpp_online_spinup_3mo_my25_uvtide_zero_source.nc`
  river_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (2209 records)
  dims: `s_rho=40, river=1, river_time=2209`

## Checks

- tide_uv_complete: `True`
- source_is_zero: `True`
- overwrite_safe: `True`

## Blocking Issues

- none

## Next Step

- Generate and validate online_spinup_3mo_my25_uvtide run mode wiring.
