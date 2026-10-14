#include "cppdefs.h"
#if defined NONLINEAR && defined SOLVE3D && defined OFFLINE && defined OFFLINE_TPASSIVE
!
!  ROMS 4.3 offline Eulerian tracer entry, I8 fail-closed scaffold.
!
!  IMPORTANT: The offline tracer transport engine is not yet complete.
!  Dispatching through normal main3d would silently recalculate ocean
!  dynamics and would NOT implement the selected offline method.
!
!  This explicitly prevents a false scientific result while staged
!  offline input, tracer advance and output interfaces are ported.
!
      SUBROUTINE main3d_offline (RunInterval)
      USE mod_param, ONLY : dp
      implicit none
      real(dp), intent(in) :: RunInterval
!
      WRITE (*,'(a)') 'ROMS_NESTING_I8_BLOCKED_PORT_REQUIRED: ' //       &
     &              'offline snapshot IO/tracer timestep not yet wired'
      WRITE (*,'(a)') 'ROMS_NESTING_I8_BLOCKED: ' //                     &
     &              'normal 3D hydrodynamics will NOT be executed'
      ERROR STOP 86
      END SUBROUTINE main3d_offline
#endif
