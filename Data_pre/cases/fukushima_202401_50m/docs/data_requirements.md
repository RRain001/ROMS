# Data Requirements For Fukushima ROMS Project

## Forcing Categories

You are right that the model needs more than a release number. The required fields should be separated into atmospheric forcing, ocean initial/boundary forcing, tide, and source term.

For this Fukushima HTO project, the practical rule is:

- Atmospheric forcing: wind, pressure, air temperature, humidity, radiation, precipitation and evaporation/freshwater flux.
- Ocean forcing: sea surface height, 3D temperature, salinity, current velocity and depth-integrated current at open boundaries and initial time.
- Tide forcing: tidal elevation and tidal current constituents.
- Source forcing: HTO concentration or activity flux converted through a water discharge/effective volume flux.

Wind speed/direction, pressure, precipitation and evaporation are meteorological fields. Sea temperature, salinity and ocean current are not meteorological forcing in ROMS; they are ocean state fields for initial and boundary conditions.

## Atmospheric Forcing

These drive surface momentum, heat and freshwater fluxes.

| Field | ROMS variable examples | Why needed | Candidate source |
| --- | --- | --- | --- |
| 10 m wind speed/components | `Uwind`, `Vwind` | surface momentum, plume advection via wind-driven current | ERA5 or NCEP FNL |
| Wind direction | derived from `Uwind`, `Vwind` | diagnostics; ROMS usually uses vector components | ERA5 or NCEP FNL |
| Sea level pressure | `Pair` | inverse barometer and bulk flux | ERA5 or NCEP FNL |
| Air temperature | `Tair` | heat flux / bulk formula | ERA5 or NCEP FNL |
| Relative/specific humidity | `Qair` | latent heat and evaporation | ERA5 or NCEP FNL |
| Shortwave radiation | `swrad` | heat flux | ERA5 |
| Longwave radiation | `lwrad`, `lwrad_down` | heat flux | ERA5 |
| Precipitation | `rain` | freshwater flux | ERA5 or GPM |
| Evaporation | `EminusP` or derived by bulk flux | freshwater/salinity tendency | ERA5 or ROMS bulk flux calculation |

The current `my_roms_tools` NCEP script writes wind, pressure, air temperature, humidity and `rain`, but sets `rain(:)=0`. For a Fukushima plume project, precipitation and evaporation should not be silently omitted if salinity or surface freshwater effects matter.

## Ocean Initial And Boundary Conditions

These are not meteorology; they define the 3D ocean state entering and surrounding the model domain.

| Field | ROMS variable examples | Why needed | Candidate source |
| --- | --- | --- | --- |
| Sea surface height | `zeta` | pressure gradient and boundary sea level | HYCOM or CMEMS |
| 3D ocean current | `u`, `v`, `ubar`, `vbar` | dominant tracer advection | HYCOM or CMEMS |
| Sea temperature | `temp` | density and stratification | HYCOM or CMEMS |
| Salinity | `salt` | density and stratification | HYCOM or CMEMS |
| Optional mixing fields | model dependent | turbulence/stratification checks | usually diagnosed in ROMS |

For tracer transport, ocean current is the key driver. Temperature and salinity still matter because they affect density, stratification and circulation.

Minimum production fields:

- `zeta`, `ubar`, `vbar`, `u`, `v`, `temp`, `salt` at initial time.
- Boundary values for the same fields over 2024-01-01 to 2024-01-31.
- Time units, calendar, vertical coordinate and horizontal interpolation metadata recorded in the preprocessing log.

For a first technical dry run, these may be replaced by idealized or climatological placeholders only if the run is explicitly labeled non-scientific.

## Tide

| Field | ROMS variable examples | Candidate source |
| --- | --- | --- |
| tidal elevation amplitude/phase | `tide_Eamp`, `tide_Ephase` | TPXO9 |
| tidal current ellipse | `tide_Cmax`, `tide_Cmin`, `tide_Cangle`, `tide_Cphase` | TPXO9 |

For a nearshore Fukushima domain, tide should be included unless the project explicitly tests a no-tide sensitivity case.
Current implementation phase uses elevation-only TPXO forcing with `SSH_TIDES` enabled and `UV_TIDES` disabled; current ellipses are deferred until `u_*`/`v_*` atlas files are staged and wired into preprocessing.

## HTO Source Term

Known:

- Annual release: 22 TBq/year.
- Constant-rate conversion for 2024: about 695,709 Bq/s.
- January 2024 inventory under constant release: about 1.863e12 Bq.

Pilot assumption:

- The current pilot uses an explicit nominal discharge of `1 m3/s` only to create a ROMS-readable source file.
- This `1 m3/s` transport is a numerical carrier, not a measured discharge.
- This converts `695709.371 Bq/s` to `695709.371 Bq/m3` in `river_dye_01`.
- The pilot `.in` file is generated with `LwSrc=T` and `LtracerSrc=F F T`, so only `dye_01` is sourced from the point-source file; temperature and salinity source values are placeholders required by the ROMS source-file structure.

Still needed for scientific use:

- Real discharge or effective water flux, m3/s.
- Exact release location and depth.
- Whether release is continuous, monthly varying, or event-based.
- Whether HTO is treated as conservative passive tracer. This skeleton assumes yes.

For ROMS river/source style input:

```text
river_dye_01 [Bq/m3] = release_Bq_s / discharge_m3_s
```

If the real discharge is unknown, treat the current `1 m3/s` value as a sensitivity placeholder, not as a factual release condition.

## Minimum Real Run Inputs

Before production run:

- Real `roms_grid.nc` with bathymetry and land mask.
- `roms_ini.nc`, `roms_bdy.nc`, `roms_clm.nc` from HYCOM/CMEMS.
- `roms_atom.nc` and radiation/freshwater forcing from ERA5 or NCEP/ERA5 mix.
- `roms_tides.nc` from TPXO9.
- Source file with HTO concentration after selecting discharge.
- ROMS `.in` file with `NPT=1`, `T_PASSIVE` compile option and inert tracer output enabled.
