# Explicit FDNPP-compatible local Linux toolchain, isolated from GNU profiles.
[ "$(uname -s)" = Linux ] || { echo 'Intel Linux profile requires Linux' >&2; return 1; }
: "${NETCDF:?Set the case NetCDF prefix}"
: "${MPI_ROOT:?Set the case Intel MPI prefix}"
# Discover the oneAPI compiler root instead of pinning a release version, so an
# oneAPI upgrade does not silently break the profile. Highest version wins.
intel_compiler_root="${ROMS_INTEL_COMPILER_ROOT:-}"
if [ -z "$intel_compiler_root" ]; then
    for _candidate in $(ls -d "$HOME"/intel/oneapi/compiler/*/linux 2>/dev/null | sort -V); do
        [ -d "$_candidate" ] && intel_compiler_root="$_candidate"
    done
    unset _candidate
fi
[ -n "$intel_compiler_root" ] && [ -d "$intel_compiler_root" ] || {
    echo 'Set ROMS_INTEL_COMPILER_ROOT to an oneAPI compiler/<version>/linux directory' >&2
    return 1
}
export PATH="$MPI_ROOT/bin:$intel_compiler_root/bin/intel64:$NETCDF/bin:/usr/bin:/bin"
unset OMPI_FC OMPI_CC LIBRARY_PATH CPATH C_INCLUDE_PATH FPATH LD_PRELOAD
export LD_LIBRARY_PATH="$NETCDF/lib:$MPI_ROOT/lib/release:$MPI_ROOT/lib:$intel_compiler_root/compiler/lib/intel64_lin"
export NF_CONFIG="$NETCDF/bin/nf-config" NC_CONFIG="$NETCDF/bin/nc-config"
export NETCDF_INCDIR="$NETCDF/include"
export I_MPI_ROOT="$MPI_ROOT" I_MPI_F90=ifort I_MPI_FC=ifort
export FORT=ifort which_MPI=intel
