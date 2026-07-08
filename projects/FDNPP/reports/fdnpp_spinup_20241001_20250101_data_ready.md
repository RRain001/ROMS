# FDNPP Spin-up Data Ready Report

- case: `FDNPP`
- profile: `online_my25_uvtide`
- window: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00`
- status: `blocked`
- can_generate_spinup_run_mode: `False`

## Inputs

- raw_ini: `/home/lhy/ROMS/projects/FDNPP/data/raw/ocean/glorys12v1/glorys12v1_initial_20241001.nc`
  missing_variables: `zos, uo, vo, thetao, so`
- raw_bdy: `/home/lhy/ROMS/projects/FDNPP/data/raw/ocean/glorys12v1/glorys12v1_boundary_20241001_20250101.nc`
  missing_variables: `zos, uo, vo, thetao, so`
- raw_atm: `/home/lhy/ROMS/projects/FDNPP/data/raw/atmosphere/era5_atm_fdnpp_20241001_20250101.nc`
  time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (2209 records)
  dims: `time=2209, lat=6, lon=7`
- raw_rad: `/home/lhy/ROMS/projects/FDNPP/data/raw/atmosphere/era5_rad_fdnpp_20241001_20250101.nc`
  time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (2209 records)
  dims: `time=2209, lat=6, lon=7`
- raw_tides: `/home/lhy/ROMS/projects/FDNPP/data/raw/tides/tpxo9_fdnpp_20241001_20250101.nc`
  missing_variables: `tide_Eamp, tide_Ephase, tide_Cmax, tide_Cmin, tide_Cangle, tide_Cphase`
- ini: `/home/lhy/ROMS/projects/FDNPP/input/roms_ini_fdnpp_20241001_online_my25_uvtide.nc`
  ocean_time: `2024-10-01T00:00:00` -> `2024-10-01T00:00:00` (1 records)
  dims: `ocean_time=1, s_rho=40, eta_rho=190, xi_rho=201, eta_u=190, xi_u=200, eta_v=189, xi_v=201`
- bdy: `/home/lhy/ROMS/projects/FDNPP/input/roms_bdy_fdnpp_20241001_20250101_online_my25_uvtide.nc`
  zeta_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (737 records)
  v2d_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (737 records)
  v3d_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (737 records)
  temp_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (737 records)
  salt_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (737 records)
  dye_time: `2024-10-01T00:00:00` -> `2025-01-01T00:00:00` (737 records)
  dims: `zeta_time=737, v2d_time=737, v3d_time=737, temp_time=737, salt_time=737, dye_time=737, eta_rho=190, xi_rho=201, eta_u=190, xi_u=200, eta_v=189, xi_v=201, s_rho=40`
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

- raw_ini: missing variable zos
- raw_ini: missing variable uo
- raw_ini: missing variable vo
- raw_ini: missing variable thetao
- raw_ini: missing variable so
- raw_bdy: missing variable zos
- raw_bdy: missing variable uo
- raw_bdy: missing variable vo
- raw_bdy: missing variable thetao
- raw_bdy: missing variable so
- raw_tides: missing variable tide_Eamp
- raw_tides: missing variable tide_Ephase
- raw_tides: missing variable tide_Cmax
- raw_tides: missing variable tide_Cmin
- raw_tides: missing variable tide_Cangle
- raw_tides: missing variable tide_Cphase
- glorys12v1_initial_20241001.nc: missing time variable time
- glorys12v1_boundary_20241001_20250101.nc: missing time variable time

## Next Step

- Resolve the blocking issues above before creating online_spinup_3mo_my25_uvtide.
