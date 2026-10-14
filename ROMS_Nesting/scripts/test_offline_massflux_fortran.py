#!/usr/bin/env python3
"""Compile the ACTUAL ROMS set_massflux.F with native Fortran stubs.

Tests endpoint-averaged face volume flux under two tiled updates, not
a complete offline ROMS run or tracer physical conservation.
"""
from __future__ import annotations
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"roms_src/roms/ROMS/Nonlinear/set_massflux.F"
STUBS="""
module mod_param
  implicit none
  integer, parameter :: r8=kind(1d0), iNLM=1
  integer, parameter :: N(1)=[2]
end module
module mod_scalars
  implicit none
  logical :: EWperiodic(1)=.false., NSperiodic(1)=.false.
end module
module mod_stepping
  implicit none
  integer :: nrhs(1)=1, nnew(1)=2
end module
module mod_grid
  use mod_param
  implicit none
  type grid_type
    real(r8), pointer :: Hz(:,:,:)=>null()
    real(r8), pointer :: om_v(:,:)=>null(), on_u(:,:)=>null()
    real(r8), pointer :: Huon(:,:,:)=>null(), Hvom(:,:,:)=>null()
  end type
  type(grid_type) :: GRID(1)
end module
module mod_ocean
  use mod_param
  implicit none
  type ocean_type
    real(r8), pointer :: u(:,:,:,:)=>null(), v(:,:,:,:)=>null()
  end type
  type(ocean_type) :: OCEAN(1)
end module
module exchange_3d_mod
  use mod_param
  implicit none
contains
  subroutine exchange_u3d_tile(ng,tile,LBi,UBi,LBj,UBj,klo,khi,a)
    integer,intent(in)::ng,tile,LBi,UBi,LBj,UBj,klo,khi
    real(r8),intent(inout)::a(LBi:UBi,LBj:UBj,klo:khi)
  end subroutine
  subroutine exchange_v3d_tile(ng,tile,LBi,UBi,LBj,UBj,klo,khi,a)
    integer,intent(in)::ng,tile,LBi,UBi,LBj,UBj,klo,khi
    real(r8),intent(inout)::a(LBi:UBi,LBj:UBj,klo:khi)
  end subroutine
end module
"""
TILE="""      integer, parameter :: LBi=0, UBi=5, LBj=0, UBj=3
      integer, parameter :: IminS=0, ImaxS=5, JminS=0, JmaxS=3
"""
BOUNDS="""      integer :: IstrP,IendT,IstrT,JstrT,JendT,JstrP
      IstrP=1+2*(tile-1)
      IstrT=IstrP
      IendT=2*tile
      JstrT=1
      JstrP=1
      JendT=2
"""
DRIVER="""
program massflux_test
  use mod_param
  use mod_grid
  use mod_ocean
  use set_massflux_mod
  implicit none
  integer :: tile
  allocate(GRID(1)%Hz(0:5,0:3,1:2),GRID(1)%om_v(0:5,0:3),GRID(1)%on_u(0:5,0:3))
  allocate(GRID(1)%Huon(0:5,0:3,1:2),GRID(1)%Hvom(0:5,0:3,1:2))
  allocate(OCEAN(1)%u(0:5,0:3,1:2,1:2),OCEAN(1)%v(0:5,0:3,1:2,1:2))
  GRID(1)%Hz=10.0_r8
  GRID(1)%on_u=2.0_r8
  GRID(1)%om_v=3.0_r8
  GRID(1)%Huon=-999.0_r8
  GRID(1)%Hvom=-999.0_r8
  OCEAN(1)%u(:,:,:,1)=1.0_r8
  OCEAN(1)%u(:,:,:,2)=3.0_r8
  OCEAN(1)%v(:,:,:,1)=2.0_r8
  OCEAN(1)%v(:,:,:,2)=4.0_r8
  do tile=1,2
    call set_massflux(1,tile,1)
  end do
  if (any(abs(GRID(1)%Huon(1:4,1:2,:)-20.0_r8)>1.e-12_r8)) stop 10
  if (any(abs(GRID(1)%Hvom(1:4,1:2,:)-60.0_r8)>1.e-12_r8)) stop 11
#ifdef OFFLINE_TPASSIVE
  do tile=1,2
    call set_massflux_avg(1,tile,1)
  end do
  if (any(abs(GRID(1)%Huon(1:4,1:2,:)-40.0_r8)>1.e-12_r8)) stop 20
  if (any(abs(GRID(1)%Hvom(1:4,1:2,:)-90.0_r8)>1.e-12_r8)) stop 21
#endif
  print *, 'NATIVE_SET_MASSFLUX_GFORTRAN_PASS'
end program
"""
def call(*args:str,cwd:Path)->None:
    v=subprocess.run(args,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    print(v.stdout)
    if v.returncode:
        raise RuntimeError(f"gfortran test error {v.returncode}: {args}")

def main()->None:
    cc=shutil.which("gfortran")
    if not cc:
        raise RuntimeError("gfortran required for native massflux test")
    with tempfile.TemporaryDirectory(prefix="roms_i8_flux_") as tmp:
        root=Path(tmp)
        (root/"cppdefs.h").write_text("#define SOLVE3D\n#define ASSUMED_SHAPE\n")
        (root/"tile.h").write_text(TILE)
        (root/"set_bounds.h").write_text(BOUNDS)
        (root/"stubs.f90").write_text(STUBS)
        (root/"driver.F90").write_text(DRIVER)
        for offline in (False,True):
            mode="offline" if offline else "ordinary"
            args=[cc,"-cpp","-ffree-form","-ffree-line-length-none","-fcheck=all",
                  "-std=legacy","-Werror=implicit-interface","-I",str(root),
                  "-J",str(root)]
            if offline:
                args+=["-DOFFLINE","-DOFFLINE_TPASSIVE"]
            args+=[str(root/"stubs.f90"),str(SOURCE),str(root/"driver.F90"),
                   "-o",str(root/mode)]
            call(*args,cwd=root)
            call(str(root/mode),cwd=root)
    print("I8 actual ROMS Fortran massflux tile compilation PASS (full ROMS offline NOT_RUN)")

if __name__=="__main__":
    main()
