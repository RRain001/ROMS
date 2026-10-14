#!/usr/bin/env python3
"""Compile/test the REAL isolated ROMS offline hydro NetCDF Fortran reader.

Includes deliberately defective inputs. A passing test means only native
NetCDF snapshot I/O works on a SMALL single grid, not offline physics.
"""
from __future__ import annotations

from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tests"))
from test_offline_hydro_contract import make_file

SOURCE=ROOT/"roms_src/roms/ROMS/Nonlinear/offline_hydro_reader.F"
MODULES="""module mod_param
 implicit none
 integer, parameter :: r8=kind(1d0)
end module mod_param
"""
DRIVER=r"""
program inspect_offline_hydro
 use mod_param
 use offline_hydro_reader_mod
 implicit none
 type(offline_hydro_frame) :: f
 real(r8), allocatable :: times(:)
 integer :: ierr
 character(len=220):: reason
 character(len=600):: fname
 call get_command_argument(1,fname)
 if(len_trim(fname)==0) error stop 'need filename'
 call read_offline_hydro_times(trim(fname),times,ierr,reason)
 if(ierr/=0) then
   print *, trim(reason)
   error stop 15
 endif
 if(size(times)/=3) error stop 16
 if(abs(times(2)-60d0)>1d-12) error stop 17
 if(abs(times(3)-120d0)>1d-12) error stop 18
 call read_offline_hydro_frame(trim(fname),2,f,ierr,reason)
 if(ierr/=0) then
   print *, trim(reason)
   error stop 19
 endif
 if(size(f%zeta,1)/=6 .or. size(f%zeta,2)/=5) error stop 20
 if(size(f%u,1)/=5 .or. size(f%v,2)/=4) error stop 21
 if(size(f%AKs,3)/=3) error stop 22
 if(abs(f%seconds-60d0)>1d-12) error stop 23
 if(any(abs(f%u-0.5d0)>1d-12)) error stop 24
 if(any(abs(f%vbar-0.5d0)>1d-12)) error stop 25
 if(any(abs(f%AKs-0.0001d0)>1d-12)) error stop 26
 call read_offline_hydro_frame(trim(fname),4,f,ierr,reason)
 if(ierr==0) error stop 'record range did not fail'
 print *, 'I8_NATIVE_ROMS_HYDRO_NETCDF_READER_PASS'
end program
"""
NEGATIVE=r"""
program check_bad_hydro
 use offline_hydro_reader_mod
 implicit none
 type(offline_hydro_frame)::f
 real(kind(1d0)),allocatable:: times(:)
 character(len=200):: reason
 character(len=600)::fname
 integer:: ierror
 call get_command_argument(1,fname)
 call read_offline_hydro_frame(trim(fname),2,f,ierror,reason)
 if(ierror==0) error stop 'bad input was accepted'
 print *, 'I8_NATIVE_BAD_HYDRO_REJECTED:',trim(reason)
end program
"""
def run(command:list[str], cwd:Path)->None:
    result=subprocess.run(command,cwd=cwd,capture_output=True,text=True)
    if result.returncode!=0:
        raise RuntimeError(f"command failed with {result.returncode}: {' '.join(command)}\n{result.stdout}\n{result.stderr}")
    print(result.stdout)

def main()->None:
    fc=shutil.which("gfortran")
    nf=shutil.which("nf-config")
    if not fc or not nf:
        raise RuntimeError("requires both gfortran and nf-config; do not skip")
    nfargs=shlex.split(subprocess.check_output([nf,"--flibs"],text=True))
    finc=shlex.split(subprocess.check_output([nf,"--fflags"],text=True))
    with tempfile.TemporaryDirectory(prefix="roms_i8_native_netcdf_") as tmp:
        d=Path(tmp)
        (d/"cppdefs.h").write_text("#define SOLVE3D\n#define NONLINEAR\n")
        (d/"mod_param.f90").write_text(MODULES)
        (d/"driver.f90").write_text(DRIVER)
        (d/"driver_bad.f90").write_text(NEGATIVE)
        argv=[fc,"-cpp","-ffree-form","-ffree-line-length-none","-fcheck=all",
              "-fbacktrace","-Wall","-DOFFLINE","-DOFFLINE_TPASSIVE",
              "-I",str(d),"-J",str(d),*finc,str(d/"mod_param.f90"),
              str(SOURCE)]
        run([*argv,str(d/"driver.f90"),*nfargs,"-o",str(d/"run")],d)
        run([*argv,str(d/"driver_bad.f90"),*nfargs,"-o",str(d/"run_bad")],d)
        good=d/"good.nc"
        make_file(good)
        run([str(d/"run"),str(good)],d)
        tests={"missing_AKs":{"aks":False},
               "nonmonotonic_time":{"ordered":False},
               "bad_stagger":{"stagger_valid":False}}
        for name,kwargs in tests.items():
            p=d/(name+".nc")
            make_file(p,**kwargs)
            run([str(d/"run_bad"),str(p)],d)
        run([fc,"-cpp","-ffree-form","-ffree-line-length-none",
             "-I",str(d),"-J",str(d),*finc,"-c",str(SOURCE),
             "-o",str(d/"regular_mode.o")],d)
    print("I8_NATIVE_NETCDF_SNAPSHOT_IO_PASS; OFFLINE_TRACER_INTEGRATION_NOT_RUN")

if __name__=="__main__":
    main()
