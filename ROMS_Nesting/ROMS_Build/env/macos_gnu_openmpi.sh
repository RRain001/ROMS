# Explicit macOS/Homebrew profile; never sourced on Linux.
[ "$(uname -s)" = Darwin ] || { echo 'macOS toolchain selected on another platform' >&2; return 1; }
brew_bin=$(command -v brew) || return 1
netcdf_f_prefix=$("$brew_bin" --prefix netcdf-fortran) || return 1
netcdf_c_prefix=$("$brew_bin" --prefix netcdf) || return 1
mpi_prefix=$("$brew_bin" --prefix open-mpi) || return 1
gcc_prefix=$("$brew_bin" --prefix gcc) || return 1
export PATH="$mpi_prefix/bin:$gcc_prefix/bin:/usr/bin:/bin:/usr/sbin:/sbin"
unset LD_LIBRARY_PATH DYLD_LIBRARY_PATH LIBRARY_PATH CPATH FPATH
unset I_MPI_ROOT I_MPI_F90 I_MPI_FC MPI_ROOT NETCDF HDF5 NETCDFC
unset USE_PARALLEL_IO USE_PIO USE_PNETCDF
export NF_CONFIG="$netcdf_f_prefix/bin/nf-config" NC_CONFIG="$netcdf_c_prefix/bin/nc-config"
export NETCDF_INCDIR="$netcdf_f_prefix/include"
export OMPI_FC="${ROMS_GNU_FC:-$gcc_prefix/bin/gfortran}"
export FORT=gfortran which_MPI=openmpi
