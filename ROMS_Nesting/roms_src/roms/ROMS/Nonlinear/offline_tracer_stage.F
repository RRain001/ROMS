#include "cppdefs.h"
#if defined NONLINEAR && defined SOLVE3D && defined OFFLINE && defined OFFLINE_TPASSIVE
      MODULE offline_tracer_stage_mod
!
!  Real ROMS 4.3 single-frame snapshot stages. The outer driver must:
!  1. load all hydrodynamic snapshots and synchronize state indices;
!  2. execute stage on every tile; barrier/halo synchronization;
!  3. advance time only after ALL tiles are processed.
!
!  This module alone is not a functioning offline tracer time loop.
!
      implicit none
      PRIVATE
      PUBLIC :: offline_setup_stage, offline_midpoint_stage
      PUBLIC :: offline_endpoint_stage
      CONTAINS
!
!***********************************************************************
      SUBROUTINE offline_setup_stage (ng, tile)
!***********************************************************************
      USE mod_param, ONLY : iNLM
      USE set_zeta_mod, ONLY : set_avg_zeta
      USE set_depth_mod, ONLY : set_depth
      USE set_massflux_mod, ONLY : set_massflux
      integer, intent(in) :: ng, tile
!
!  First snapshot: initialize averaged surface and initial 3D face
!  volume transports (Huon/Hvom) from the first velocity record.
!
      CALL set_avg_zeta (ng, tile, .TRUE.)
      CALL set_depth (ng, tile, iNLM)
      CALL set_massflux (ng, tile, iNLM)
      RETURN
      END SUBROUTINE offline_setup_stage
!
!***********************************************************************
      SUBROUTINE offline_midpoint_stage (ng, tile)
!***********************************************************************
      USE mod_param, ONLY : iNLM
      USE set_zeta_mod, ONLY : set_avg_zeta
      USE set_depth_mod, ONLY : set_depth
      USE set_massflux_mod, ONLY : set_massflux_avg
      integer, intent(in) :: ng, tile
!
!  Next snapshot: construct updated Hz and average the new 3D
!  face transport with the previously stored one. The caller must
!  call offline_endpoint_stage after tracer transport across all
!  tiles before advancing the next hydrodynamic time window.
!
      CALL set_avg_zeta (ng, tile, .FALSE.)
      CALL set_depth (ng, tile, iNLM)
      CALL set_massflux_avg (ng, tile, iNLM)
      RETURN
      END SUBROUTINE offline_midpoint_stage
!
!***********************************************************************
      SUBROUTINE offline_endpoint_stage (ng, tile)
!***********************************************************************
      USE mod_param, ONLY : iNLM
      USE set_massflux_mod, ONLY : set_massflux_endpoint
      integer, intent(in) :: ng, tile
!
!  AFTER completing tracer transport and BEFORE loading the following
!  time window, restore the previous right-endpoint face transport.
!  Must execute across all tiles with a barrier before the next frame.
!
      CALL set_massflux_endpoint (ng, tile, iNLM)
      RETURN
      END SUBROUTINE offline_endpoint_stage
      END MODULE offline_tracer_stage_mod
#endif
