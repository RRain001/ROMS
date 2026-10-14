#include "cppdefs.h"
      MODULE set_zeta_mod

#ifdef SOLVE3D
!
!git $Id$
!================================================== Hernan G. Arango ===
!  Copyright (c) 2002-2026 The ROMS Group                              !
!    Licensed under a MIT/X style license                              !
!    See License_ROMS.md                                               !
!=======================================================================
!                                                                      !
!  This routine sets free-surface to its fast-time averaged value.     !
!                                                                      !
!=======================================================================
!
      implicit none
!
      PRIVATE
      PUBLIC  :: set_zeta
# if defined OFFLINE && defined OFFLINE_TPASSIVE
!  Offline snapshot-based free surface; no change to default build.
      PUBLIC  :: set_avg_zeta
# endif
!
      CONTAINS
!
!***********************************************************************
      SUBROUTINE set_zeta (ng, tile)
!***********************************************************************
!
      USE mod_param
      USE mod_coupling
      USE mod_ocean
!
!  Imported variable declarations.
!
      integer, intent(in) :: ng, tile
!
!  Local variable declarations.
!
      character (len=*), parameter :: MyFile =                          &
     &  __FILE__
!
# include "tile.h"
!
# ifdef PROFILE
      CALL wclock_on (ng, iNLM, 12, __LINE__, MyFile)
# endif
      CALL set_zeta_tile (ng, tile,                                     &
     &                    LBi, UBi, LBj, UBj,                           &
     &                    IminS, ImaxS, JminS, JmaxS,                   &
     &                    COUPLING(ng) % Zt_avg1,                       &
     &                    OCEAN(ng) % zeta)
# ifdef PROFILE
      CALL wclock_off (ng, iNLM, 12, __LINE__, MyFile)
# endif
!
      RETURN
      END SUBROUTINE set_zeta
!
!***********************************************************************
      SUBROUTINE set_zeta_tile (ng, tile,                               &
     &                          LBi, UBi, LBj, UBj,                     &
     &                          IminS, ImaxS, JminS, JmaxS,             &
     &                          Zt_avg1, zeta)
!***********************************************************************
!
      USE mod_param
      USE mod_scalars
!
      USE exchange_2d_mod, ONLY : exchange_r2d_tile
# ifdef DISTRIBUTE
      USE mp_exchange_mod, ONLY : mp_exchange2d
# endif
!
!  Imported variable declarations.
!
      integer, intent(in) :: ng, tile
      integer, intent(in) :: LBi, UBi, LBj, UBj
      integer, intent(in) :: IminS, ImaxS, JminS, JmaxS
!
# ifdef ASSUMED_SHAPE
      real(r8), intent(in) :: Zt_avg1(LBi:,LBj:)

      real(r8), intent(out) :: zeta(LBi:,LBj:,:)
# else
      real(r8), intent(in) :: Zt_avg1(LBi:UBi,LBj:UBj)

      real(r8), intent(out) :: zeta(LBi:UBi,LBj:UBj,3)
# endif
!
!  Local variable declarations.
!
      integer :: i, j

# include "set_bounds.h"
!
!-----------------------------------------------------------------------
!  Prepare to time-step 2D equations:  set initial free-surface
!  to its fast-time averaged values (which corresponds to the time
!  step "n").
!-----------------------------------------------------------------------
!
      DO j=JstrR,JendR
        DO i=IstrR,IendR
          zeta(i,j,1)=Zt_avg1(i,j)
          zeta(i,j,2)=Zt_avg1(i,j)
        END DO
      END DO

      IF (EWperiodic(ng).or.NSperiodic(ng)) THEN
        CALL exchange_r2d_tile (ng, tile,                               &
     &                          LBi, UBi, LBj, UBj,                     &
     &                          zeta(:,:,1))
        CALL exchange_r2d_tile (ng, tile,                               &
     &                          LBi, UBi, LBj, UBj,                     &
     &                          zeta(:,:,2))
      END IF

# ifdef DISTRIBUTE
      CALL mp_exchange2d (ng, tile, iNLM, 2,                            &
     &                    LBi, UBi, LBj, UBj,                           &
     &                    NghostPoints,                                 &
     &                    EWperiodic(ng), NSperiodic(ng),               &
     &                    zeta(:,:,1),                                  &
     &                    zeta(:,:,2))
# endif
!
      RETURN
      END SUBROUTINE set_zeta_tile

# if defined OFFLINE && defined OFFLINE_TPASSIVE
!
!***********************************************************************
      SUBROUTINE set_avg_zeta (ng, tile, FirstCall)
!***********************************************************************
!
!  One stage of the offline HTO free-surface coupling.
!  FirstCall is READ ONLY here: in a multi-tile run the caller must
!  transition to the second-snapshot state AFTER all tiles finish.
!  This differs deliberately from the mutable Thyng-2021 FIRSTCALL.
!
      USE mod_param
      USE mod_coupling
      USE mod_ocean
!
      integer, intent(in) :: ng, tile
      logical, intent(in) :: FirstCall
!
# include "tile.h"
!
      CALL set_avg_zeta_tile (ng, tile,                                 &
     &                        LBi, UBi, LBj, UBj,                       &
     &                        IminS, ImaxS, JminS, JmaxS,               &
     &                        FirstCall,                                &
     &                        COUPLING(ng) % Zt_avg1,                   &
     &                        OCEAN(ng) % zeta)
!
      RETURN
      END SUBROUTINE set_avg_zeta
!
!***********************************************************************
      SUBROUTINE set_avg_zeta_tile (ng, tile,                            &
     &                             LBi, UBi, LBj, UBj,                  &
     &                             IminS, ImaxS, JminS, JmaxS,          &
     &                             FirstCall, Zt_avg1, zeta)
!***********************************************************************
!
      USE mod_param
      USE mod_scalars
!
      USE exchange_2d_mod, ONLY : exchange_r2d_tile
#  ifdef DISTRIBUTE
      USE mp_exchange_mod, ONLY : mp_exchange2d
#  endif
!
      integer, intent(in) :: ng, tile
      integer, intent(in) :: LBi, UBi, LBj, UBj
      integer, intent(in) :: IminS, ImaxS, JminS, JmaxS
      logical, intent(in) :: FirstCall
!
#  ifdef ASSUMED_SHAPE
      real(r8), intent(inout) :: Zt_avg1(LBi:,LBj:)
      real(r8), intent(in) :: zeta(LBi:,LBj:,:)
#  else
      real(r8), intent(inout) :: Zt_avg1(LBi:UBi,LBj:UBj)
      real(r8), intent(in) :: zeta(LBi:UBi,LBj:UBj,3)
#  endif
!
      integer :: i, j, k
!
# include "set_bounds.h"
!
!  Thyng snapshots: first record at first setup call (k=1);
!  following record at next hydrodynamic time level (k=2).
!  This step does NOT time-average the physical field itself.
!
      k=2
      IF (FirstCall) k=1
      DO j=JstrR,JendR
        DO i=IstrR,IendR
          Zt_avg1(i,j)=zeta(i,j,k)
        END DO
      END DO
!
      IF (EWperiodic(ng).or.NSperiodic(ng)) THEN
        CALL exchange_r2d_tile (ng, tile,                               &
     &                          LBi, UBi, LBj, UBj,                     &
     &                          Zt_avg1)
      END IF
#  ifdef DISTRIBUTE
      CALL mp_exchange2d (ng, tile, iNLM, 1,                            &
     &                    LBi, UBi, LBj, UBj,                           &
     &                    NghostPoints,                                 &
     &                    EWperiodic(ng), NSperiodic(ng),               &
     &                    Zt_avg1)
#  endif
!
      RETURN
      END SUBROUTINE set_avg_zeta_tile
# endif
#endif
      END MODULE set_zeta_mod
