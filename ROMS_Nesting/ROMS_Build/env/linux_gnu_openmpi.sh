# Sourced by the existing build/run frameworks, never by frozen ROMS sources.
[ "$(uname -s)" = Linux ] || { echo 'Use the separate macOS toolchain profile' >&2; return 1; }

# Keep the vendor toolchain out of the way, but do not pretend the NetCDF tools
# live in a fixed distro directory: locate them, or take an explicit override.
export PATH=/usr/local/bin:/usr/bin:/bin
unset LD_LIBRARY_PATH LD_PRELOAD LIBRARY_PATH CPATH C_INCLUDE_PATH FPATH
unset I_MPI_ROOT I_MPI_F90 I_MPI_FC MPI_ROOT NETCDF HDF5 NETCDFC
unset USE_PARALLEL_IO USE_PIO USE_PNETCDF

_resolve_gnu_netcdf_tool() {
    # $1 = explicit override, $2 = tool name
    if [ -n "$1" ]; then
        printf '%s' "$1"
        return 0
    fi
    _found="$(command -v "$2" 2>/dev/null || true)"
    if [ -n "$_found" ]; then
        printf '%s' "$_found"
        return 0
    fi
    return 1
}

NF_CONFIG="$(_resolve_gnu_netcdf_tool "${ROMS_GNU_NF_CONFIG:-}" nf-config)" || {
    echo 'Set ROMS_GNU_NF_CONFIG to an nf-config belonging to the GNU toolchain' >&2
    unset -f _resolve_gnu_netcdf_tool
    return 1
}
NC_CONFIG="$(_resolve_gnu_netcdf_tool "${ROMS_GNU_NC_CONFIG:-}" nc-config)" || {
    echo 'Set ROMS_GNU_NC_CONFIG to an nc-config belonging to the GNU toolchain' >&2
    unset -f _resolve_gnu_netcdf_tool
    return 1
}
unset -f _resolve_gnu_netcdf_tool
export NF_CONFIG NC_CONFIG

export OMPI_FC="${ROMS_GNU_FC:-/usr/bin/gfortran-11}"
[ -x "$OMPI_FC" ] || { echo 'Set ROMS_GNU_FC to a GNU >=7 compiler compatible with the installed MPI/NetCDF modules' >&2; return 1; }
export NETCDF_INCDIR="$($NF_CONFIG --includedir)"
export FORT=gfortran which_MPI=openmpi
