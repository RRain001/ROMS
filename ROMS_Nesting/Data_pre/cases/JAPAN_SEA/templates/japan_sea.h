/* JAPAN_SEA ES3K external-forcing hydrodynamics, single grid executable.
 * Offline one-way nesting: NO NESTING/contact.nc and no source changes.
 * 41-level MY25, Smagorinsky, ERA5 bulk fluxes, SSH+UV TPXO tides.
 * Passive tracer retained as configured, with NO point release or decay.
 */
#define UV_ADV
#define UV_COR
#define UV_LDRAG
#define UV_VIS2
#define UV_SMAGORINSKY
#define MIX_S_UV
#define SPLINES_VDIFF
#define SPLINES_VVISC
#define DJ_GRADPS
#define TS_DIF2
#define TS_SMAGORINSKY
#define MIX_S_TS
#define CURVGRID
#define HDF5
#define SALINITY
#define SOLVE3D
#define MASKING
#define AVERAGES
#define DIAGNOSTICS_TS
#define DIAGNOSTICS_UV
#define T_PASSIVE
#define MY25_MIXING
#define KANTHA_CLAYSON
#define N2S2_HORAVG
#define RI_SPLINES
#define BULK_FLUXES
#define LONGWAVE_OUT
#define SOLAR_SOURCE
#define EMINUSP
#define SSH_TIDES
#define UV_TIDES
#define RAMP_TIDES
#define TIDES_DATE
#define ANA_BTFLUX
#define ANA_BSFLUX
#define ANA_SPFLUX
#define ANA_BPFLUX
