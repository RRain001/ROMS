# Explicit FDNPP-compatible local Linux toolchain, isolated from GNU profiles.
[ "$(uname -s)" = Linux ] || { echo 'Intel Linux profile requires Linux' >&2; return 1; }
: "${NETCDF:?Set the case NetCDF prefix}"
: "${MPI_ROOT:?Set the case Intel MPI prefix}"
intel_compiler_root="${ROMS_INTEL_COMPILER_ROOT:-$HOME/intel/oneapi/compiler/2023.1.0/linux}"
export PATH="$MPI_ROOT/bin:$intel_compiler_root/bin/intel64:$NETCDF/bin:/usr/bin:/bin"
unset OMPI_FC OMPI_CC LIBRARY_PATH CPATH C_INCLUDE_PATH FPATH LD_PRELOAD
export LD_LIBRARY_PATH="$NETCDF/lib:$MPI_ROOT/lib/release:$MPI_ROOT/lib:$intel_compiler_root/compiler/lib/intel64_lin"
export NF_CONFIG="$NETCDF/bin/nf-config" NC_CONFIG="$NETCDF/bin/nc-config"
export NETCDF_INCDIR="$NETCDF/include"
export I_MPI_ROOT="$MPI_ROOT" I_MPI_F90=ifort I_MPI_FC=ifort
export FORT=ifort which_MPI=intel
