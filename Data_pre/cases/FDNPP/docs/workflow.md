# FDNPP Workflow

Case:

- case name: `FDNPP`
- project root: `/home/lhy/ROMS/projects/FDNPP`
- domain: `140.88-142.00E`, `37.00-37.84N`
- time window: `2025-01-01 00:00:00` to `2025-02-01 00:00:00`

Current completed steps:

1. Bathymetry subset created:
   - `data/raw/bathymetry/gebco_fdnpp.nc`
2. Ocean staged raw created:
   - `data/raw/ocean/hycom_initial_20250101.nc`
   - `data/raw/ocean/hycom_boundary_202501.nc`
3. Atmosphere staged raw created:
   - `data/raw/atmosphere/era5_atm_fdnpp_202501.nc`
   - `data/raw/atmosphere/era5_rad_fdnpp_202501.nc`
4. Tidal staged raw created:
   - `data/raw/tides/tpxo9_fdnpp_202501.nc`
5. Source discharge staged:
   - `data/raw/source/fdnpp_source_discharge.csv`
6. Pilot grid created:
   - `input/roms_grid_bathy_500m.nc`
7. Grid cleanup and smoothing products created:
   - `input/roms_grid_bathy_500m_maskclean.nc`
   - `input/roms_grid_bathy_500m_maskclean_smoothed.nc`
8. ROMS-ready products created:
   - `input/roms_ini_fdnpp_20250101.nc`
   - `input/roms_bdy_fdnpp_202501.nc`
   - `input/roms_atm_fdnpp_202501.nc`
   - `input/roms_rad_fdnpp_202501.nc`
   - `input/roms_tides_fdnpp_202501.nc`
   - `input/fdnpp_source_hourly.csv`
   - `input/roms_rivers_production.nc`
9. Pilot `.in` file created:
   - `run/ocean_fdnpp_pilot_1day.in`
10. Validation status:
   - staged validation passed
   - deep staged validation passed
   - ROMS-ready validation passed

Current `Data_pre` status:

- `Data_pre` workflow has been demonstrated end-to-end for this case
- the active pilot grid now points to the mask-cleaned and smoothed grid
- downstream ROMS-ready forcing and ocean input files should be regenerated against the new active grid before the next run
- the remaining downstream work belongs to the ROMS run layer, not the preprocessing layer
- one important scientific limitation should still be recorded in the handoff report:
  - the current HYCOM boundary product used for workflow proof is short-window coverage rather than a fully representative monthly ocean boundary for production integration

Recommended readiness-report items for this case:

1. Explicitly list the raw products under `data/raw/...`
2. Explicitly list the ROMS-ready products under `input/...`
3. Record that staged and ROMS-ready validations passed
4. Record the current HYCOM boundary duration limitation before handing off to ROMS runtime work
