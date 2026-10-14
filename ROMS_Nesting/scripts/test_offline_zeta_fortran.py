#!/usr/bin/env python3
"""Compile the REAL copied set_zeta.F against isolated ROMS-symbol stubs.

This is a numerical unit contract for native Fortran; it is not the
full ROMS OFFLINE solver and does not validate real ocean forcing.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "roms_src/roms/ROMS/Nonlinear/set_zeta.F"

PARAM_STUB = """
module mod_param
  implicit none
  integer, parameter :: r8=kind(1.0d0), iNLM=1
end module
module mod_scalars
  implicit none
  logical :: EWperiodic(1)=.false., NSperiodic(1)=.false.
end module
module mod_coupling
  use mod_param
  implicit none
  type :: coupling_type
     real(r8), pointer :: Zt_avg1(:,:) => null()
  end type
  type(coupling_type) :: COUPLING(1)
end module
module mod_ocean
  use mod_param
  implicit none
  type :: ocean_type
     real(r8), pointer :: zeta(:,:,:) => null()
  end type
  type(ocean_type) :: OCEAN(1)
end module
module exchange_2d_mod
  use mod_param
  implicit none
contains
  subroutine exchange_r2d_tile(ng,tile,LBi,UBi,LBj,UBj,a)
    integer,intent(in)::ng,tile,LBi,UBi,LBj,UBj
    real(r8),intent(inout)::a(LBi:UBi,LBj:UBj)
  end subroutine
end module
"""
TILE = """      integer, parameter :: LBi=1, UBi=4, LBj=1, UBj=2
      integer, parameter :: IminS=1, ImaxS=4, JminS=1, JmaxS=2
"""
BOUNDS = """      integer :: IstrR,IendR,JstrR,JendR
      IstrR=1+2*(tile-1)
      IendR=2*tile
      JstrR=1
      JendR=2
"""
DRIVER = """
program check_zeta
  use mod_param
  use mod_coupling
  use mod_ocean
  use set_zeta_mod
  implicit none
  integer :: i,j,t
  logical :: setup
  allocate(COUPLING(1)%Zt_avg1(1:4,1:2))
  allocate(OCEAN(1)%zeta(1:4,1:2,1:3))
  COUPLING(1)%Zt_avg1(:,:)=-7.0_r8
  OCEAN(1)%zeta(:,:,:)=0.0_r8
  do j=1,2
    do i=1,4
      OCEAN(1)%zeta(i,j,1)=100.0_r8 + real(i+10*j,r8)
      OCEAN(1)%zeta(i,j,2)=200.0_r8 + real(i+10*j,r8)
    end do
  end do
#ifdef OFFLINE_TPASSIVE
! FirstCall must not be mutated while processing each tile.
  setup=.true.
  do t=1,2
    call set_avg_zeta(1,t,setup)
    if (.not. setup) stop 11
  end do
  if (any(abs(COUPLING(1)%Zt_avg1-OCEAN(1)%zeta(:,:,1))>1.0e-12_r8)) stop 12
  setup=.false.
  do t=1,2
    call set_avg_zeta(1,t,setup)
  end do
  if (any(abs(COUPLING(1)%Zt_avg1-OCEAN(1)%zeta(:,:,2))>1.0e-12_r8)) stop 13
#endif
! Confirm original set_zeta behavior is unchanged when offline is inactive.
  COUPLING(1)%Zt_avg1(:,:)=42.0_r8
  do t=1,2
    call set_zeta(1,t)
  end do
  if (any(OCEAN(1)%zeta(:,:,1)/=42.0_r8)) stop 14
  if (any(OCEAN(1)%zeta(:,:,2)/=42.0_r8)) stop 15
  print *, 'NATIVE_SE​T_ZETA_GFORTRAN_PASS'
end program
""".replace("SE​T","SET")

def command(*args: str, cwd: Path) -> None:
    res = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(res.stdout)
    if res.returncode:
        raise RuntimeError(f"command returned {res.returncode}: {args}")

def main() -> None:
    compiler=shutil.which("gfortran")
    if not compiler:
        raise RuntimeError("gfortran is required: do not silently skip native tests")
    with tempfile.TemporaryDirectory(prefix="roms_i8_zeta_") as tmp:
        d=Path(tmp)
        (d/"cppdefs.h").write_text("#define SOLVE3D\n#define ASSUMED_SHAPE\n")
        (d/"tile.h").write_text(TILE)
        (d/"set_bounds.h").write_text(BOUNDS)
        (d/"stub.f90").write_text(PARAM_STUB)
        (d/"driver.F90").write_text(DRIVER)
        for offline in (False, True):
            name="offline" if offline else "standard"
            argv=[compiler,"-cpp","-ffree-form","-ffree-line-length-none","-std=legacy",
                  "-Wall","-Wextra","-Werror=implicit-interface",
                  "-I",str(d),"-J",str(d)]
            if offline:
                argv+=["-DOFFLINE","-DOFFLINE_TPASSIVE"]
            argv += [str(d/"stub.f90"),str(SOURCE),str(d/"driver.F90"),"-o",str(d/name)]
            command(*argv,cwd=d)
            command(str(d/name),cwd=d)
    print("I8 set_zeta genuine Fortran source unit tests PASS (full offline model NOT_RUN)")

if __name__=="__main__":
    main()
