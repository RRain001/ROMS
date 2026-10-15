# Sourced by the existing build/run frameworks, never by frozen ROMS sources.
[ "$(uname -s)" = Linux ] || { echo 'Use the separate macOS toolchain profile' >&2; return 1; }
export PATH=/usr/bin:/bin
unset LD_LIBRARY_PATH LD_PRELOAD LIBRARY_PATH CPATH C_INCLUDE_PATH FPATH
unset I_MPI_ROOT I_MPI_F90 I_MPI_FC MPI_ROOT NETCDF HDF5 NETCDFC
unset USE_PARALLEL_IO USE_PIO USE_PNETCDF
export OMPI_FC="${ROMS_GNU_FC:-/usr/bin/gfortran-11}"
[ -x "$OMPI_FC" ] || { echo 'Set ROMS_GNU_FC to a GNU >=7 compiler compatible with the installed MPI/NetCDF modules' >&2; return 1; }
export NF_CONFIG=/usr/bin/nf-config NC_CONFIG=/usr/bin/nc-config
export NETCDF_INCDIR="$($NF_CONFIG --includedir)"
export FORT=gfortran which_MPI=openmpi
