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
  dims: `tide_period=15, lat=28, lon=35`
- ini: `/home/lhy/ROMS/projects/FDNPP/input/roms_ini_fdnpp_20241001_online_my25_uvtide.nc`
  missing_variables: `zeta, u, v, ubar, vbar, temp, salt, dye_01`
- bdy: `/home/lhy/ROMS/projects/FDNPP/input/roms_bdy_fdnpp_20241001_20250101_online_my25_uvtide.nc`
  missing_variables: `zeta_west, zeta_east, zeta_south, zeta_north, ubar_west, ubar_east, ubar_south, ubar_north, vbar_west, vbar_east, vbar_south, vbar_north, u_west, u_east, u_south, u_north, v_west, v_east, v_south, v_north, temp_west, temp_east, temp_south, temp_north, salt_west, salt_east, salt_south, salt_north, dye_west_01, dye_east_01, dye_south_01, dye_north_01`
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
- ini: missing variable zeta
- ini: missing variable u
- ini: missing variable v
- ini: missing variable ubar
- ini: missing variable vbar
- ini: missing variable temp
- ini: missing variable salt
- ini: missing variable dye_01
- bdy: missing variable zeta_west
- bdy: missing variable zeta_east
- bdy: missing variable zeta_south
- bdy: missing variable zeta_north
- bdy: missing variable ubar_west
- bdy: missing variable ubar_east
- bdy: missing variable ubar_south
- bdy: missing variable ubar_north
- bdy: missing variable vbar_west
- bdy: missing variable vbar_east
- bdy: missing variable vbar_south
- bdy: missing variable vbar_north
- bdy: missing variable u_west
- bdy: missing variable u_east
- bdy: missing variable u_south
- bdy: missing variable u_north
- bdy: missing variable v_west
- bdy: missing variable v_east
- bdy: missing variable v_south
- bdy: missing variable v_north
- bdy: missing variable temp_west
- bdy: missing variable temp_east
- bdy: missing variable temp_south
- bdy: missing variable temp_north
- bdy: missing variable salt_west
- bdy: missing variable salt_east
- bdy: missing variable salt_south
- bdy: missing variable salt_north
- bdy: missing variable dye_west_01
- bdy: missing variable dye_east_01
- bdy: missing variable dye_south_01
- bdy: missing variable dye_north_01
- roms_ini_fdnpp_20241001_online_my25_uvtide.nc: missing time variable ocean_time
- glorys12v1_initial_20241001.nc: missing time variable time
- roms_bdy_fdnpp_20241001_20250101_online_my25_uvtide.nc: missing time variable zeta_time
- glorys12v1_boundary_20241001_20250101.nc: missing time variable time
- ini: missing file /home/lhy/ROMS/projects/FDNPP/input/roms_ini_fdnpp_20241001_online_my25_uvtide.nc
- bdy: missing file /home/lhy/ROMS/projects/FDNPP/input/roms_bdy_fdnpp_20241001_20250101_online_my25_uvtide.nc

## Next Step

- Resolve the blocking issues above before creating online_spinup_3mo_my25_uvtide.
