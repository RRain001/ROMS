#!/usr/bin/env python3
"""Native gfortran test of real offline_tracer_stage.F control order.

Stubs represent ROMS routines whose actual Fortran implementations
are tested by separate native tests. This is NOT ROMS hydrodynamics.
"""
from __future__ import annotations
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"roms_src/roms/ROMS/Nonlinear/offline_tracer_stage.F"
STUBS=r"""
module mod_param
  implicit none
  integer,parameter :: iNLM=1
end module
module log_calls
  implicit none
  integer:: k=0
  integer:: calls(14)=0
contains
  subroutine record(x)
    integer,intent(in)::x
    k=k+1
    if (k>size(calls)) error stop "extra call"
    calls(k)=x
  end subroutine
end module
module set_zeta_mod
  use log_calls
  implicit none
contains
  subroutine set_avg_zeta(ng,tile,first)
    integer,intent(in)::ng,tile
    logical,intent(in)::first
    if(ng/=1) error stop "ng"
    if(first)then
      call record(tile*10+1)
    else
      call record(tile*10+2)
    endif
  end subroutine
end module
module set_depth_mod
  use log_calls
  implicit none
contains
  subroutine set_depth(ng,tile,model)
    integer,intent(in)::ng,tile,model
    if(model/=1) error stop "model"
    call record(tile*10+3)
  end subroutine
end module
module set_massflux_mod
  use log_calls
  implicit none
contains
  subroutine set_massflux(ng,tile,model)
    integer,intent(in)::ng,tile,model
    call record(tile*10+4)
  end subroutine
  subroutine set_massflux_avg(ng,tile,model)
    integer,intent(in)::ng,tile,model
    call record(tile*10+5)
  end subroutine
  subroutine set_massflux_endpoint(ng,tile,model)
    integer,intent(in)::ng,tile,model
    call record(tile*10+6)
  end subroutine
end module
"""
DRIVER=r"""
program stage_test
  use offline_tracer_stage_mod
  use log_calls
  implicit none
  integer::tile
  integer, parameter :: want(14)=[11,13,14,21,23,24,12,13,15,22,23,25,16,26]
  do tile=1,2
    call offline_setup_stage(1,tile)
  enddo
  do tile=1,2
    call offline_midpoint_stage(1,tile)
  enddo
  do tile=1,2
    call offline_endpoint_stage(1,tile)
  enddo
  if(k/=size(want))error stop "wrong call count"
  if(any(calls/=want)) then
    print *, 'actual:',calls
    error stop "wrong staged order"
  endif
  print *, 'I8_NATIVE_STAGE_ORDER_PASS'
end program
"""
def run(*cmd: str, cwd: Path) -> None:
    r=subprocess.run(cmd,cwd=cwd,text=True,capture_output=True)
    print(r.stdout,r.stderr)
    if r.returncode:
        raise RuntimeError(f"{cmd[0]} exited {r.returncode}")
def main() -> None:
    fc=shutil.which("gfortran")
    if fc is None:
        raise RuntimeError("native Fortran compiler required")
    with tempfile.TemporaryDirectory(prefix="roms_i8_stages_") as tmp:
        d=Path(tmp)
        (d/"cppdefs.h").write_text("#define NONLINEAR\n#define SOLVE3D\n")
        (d/"modules.f90").write_text(STUBS)
        (d/"driver.f90").write_text(DRIVER)
        run(fc,"-cpp","-ffree-form","-ffree-line-length-none","-fcheck=all",
            "-DOFFLINE","-DOFFLINE_TPASSIVE",
            "-I",str(d),"-J",str(d),str(d/"modules.f90"),
            str(SOURCE),str(d/"driver.f90"),"-o",str(d/"run"),cwd=d)
        run(str(d/"run"),cwd=d)
        run(fc,"-cpp","-ffree-form","-ffree-line-length-none",
            "-I",str(d),"-J",str(d),"-c",str(SOURCE),
            "-o",str(d/"normal.o"),cwd=d)
    print("I8_STAGE_CONTROL_PASS; real coupled ROMS solver NOT_RUN")
if __name__=="__main__":
    main()
