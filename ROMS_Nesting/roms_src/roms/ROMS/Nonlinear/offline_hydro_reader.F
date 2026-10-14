#include "cppdefs.h"
#if defined NONLINEAR && defined SOLVE3D && defined OFFLINE && defined OFFLINE_TPASSIVE
!
!  ROMS nesting I8: read-only *prototype* interface for frozen
!  hydrodynamic snapshots.  Reads history files in native ROMS
!  C-grid indexing; does NOT make offline integration operational.
!  To avoid uncontrolled production memory allocations, it accepts
!  only small grids until per-tile / MPI halo I/O is implemented.
!
      MODULE offline_hydro_reader_mod
      USE mod_param, ONLY : r8
      USE netcdf
      USE, INTRINSIC :: ieee_arithmetic, ONLY : ieee_is_finite
      IMPLICIT NONE
      PRIVATE
      PUBLIC :: offline_hydro_frame, read_offline_hydro_frame
      PUBLIC :: read_offline_hydro_times
!
      INTEGER, PARAMETER :: MaxPrototypeCells=100000
      TYPE offline_hydro_frame
        REAL(r8), ALLOCATABLE :: zeta(:,:), ubar(:,:), vbar(:,:)
        REAL(r8), ALLOCATABLE :: u(:,:,:), v(:,:,:), AKs(:,:,:)
        REAL(r8) :: seconds=0.0_r8
      END TYPE offline_hydro_frame
!
      CONTAINS
!
      SUBROUTINE read_offline_hydro_times (filename,times,ierr,reason)
        CHARACTER(len=*), INTENT(in) :: filename
        REAL(r8), ALLOCATABLE, INTENT(out) :: times(:)
        INTEGER, INTENT(out) :: ierr
        CHARACTER(len=*), INTENT(out) :: reason
        INTEGER :: ncid,vid,dimid,nrec,k,st
        CHARACTER(len=160) :: units
        ierr=1
        reason='could not open NetCDF history'
        st=nf90_open(TRIM(filename),nf90_nowrite,ncid)
        IF (st.ne.nf90_noerr) RETURN
        reason='ocean_time missing or invalid'
        st=nf90_inq_varid(ncid,'ocean_time',vid)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inq_dimid(ncid,'ocean_time',dimid)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inquire_dimension(ncid,dimid,len=nrec)
        IF (st.ne.nf90_noerr) GOTO 900
        IF (nrec.lt.2) GOTO 900
        units=''
        st=nf90_get_att(ncid,vid,'units',units)
        IF (st.ne.nf90_noerr) GOTO 900
        IF ((INDEX(units,'seconds since').ne.1).and.               &
     &      (INDEX(units,'days since').ne.1)) GOTO 900
        allocate(times(nrec))
        st=nf90_get_var(ncid,vid,times)
        IF (st.ne.nf90_noerr) GOTO 890
        DO k=2,nrec
          IF (.not.(times(k).gt.times(k-1))) GOTO 890
        END DO
        IF (INDEX(units,'days since').eq.1) times=times*86400.0_r8
        ierr=0
        reason='ok'
        st=nf90_close(ncid)
        RETURN
 890    DEALLOCATE(times)
 900    st=nf90_close(ncid)
      END SUBROUTINE read_offline_hydro_times
!
      SUBROUTINE read_offline_hydro_frame (filename,record,frame,     &
     &                                     ierr,reason)
        CHARACTER(len=*), INTENT(in) :: filename
        INTEGER, INTENT(in) :: record
        TYPE(offline_hydro_frame), INTENT(out) :: frame
        INTEGER, INTENT(out) :: ierr
        CHARACTER(len=*), INTENT(out) :: reason
        INTEGER :: ncid,st, nx,ny,nu,nv,nu_eta,nv_xi,nz,nw, nt
        INTEGER :: idxr,idyr,idxu,idyu,idxv,idyv,idsr,idsw,idt
        INTEGER :: vid,dids(NF90_MAX_VAR_DIMS), ndim
        REAL(r8), ALLOCATABLE :: times(:)
        INTEGER :: ids(8),i
        CHARACTER(len=16) :: names(8)
        ierr=1
        reason='history time axis invalid'
        CALL read_offline_hydro_times(filename,times,st,reason)
        IF (st.ne.0) RETURN
        nt=SIZE(times)
        IF ((record.lt.1).or.(record.gt.nt)) THEN
          reason='record outside valid history time range'
          RETURN
        END IF
        frame%seconds=times(record)
        reason='unable to open history for frame'
        st=nf90_open(TRIM(filename),nf90_nowrite,ncid)
        IF (st.ne.nf90_noerr) RETURN
        reason='C-grid dimensions missing or inconsistent'
        st=nf90_inq_dimid(ncid,'xi_rho',idxr)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inq_dimid(ncid,'eta_rho',idyr)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inq_dimid(ncid,'xi_u',idxu)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inq_dimid(ncid,'eta_u',idyu)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inq_dimid(ncid,'xi_v',idxv)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inq_dimid(ncid,'eta_v',idyv)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inq_dimid(ncid,'s_rho',idsr)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inq_dimid(ncid,'s_w',idsw)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inq_dimid(ncid,'ocean_time',idt)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inquire_dimension(ncid,idxr,len=nx)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inquire_dimension(ncid,idyr,len=ny)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inquire_dimension(ncid,idxu,len=nu)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inquire_dimension(ncid,idyv,len=nv)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inquire_dimension(ncid,idxv,len=nv_xi)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inquire_dimension(ncid,idyu,len=nu_eta)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inquire_dimension(ncid,idsr,len=nz)
        IF (st.ne.nf90_noerr) GOTO 900
        st=nf90_inquire_dimension(ncid,idsw,len=nw)
        IF (st.ne.nf90_noerr) GOTO 900
        IF (nx*ny.gt.MaxPrototypeCells) THEN
          reason='prototype refuses large grids until tiled I/O'
          GOTO 900
        END IF
        IF (nu.ne.nx-1.or.nv.ne.ny-1.or.nw.ne.nz+1.or.    &
     &      nu_eta.ne.ny.or.nv_xi.ne.nx) GOTO 900
        names=(/'zeta            ','ubar            ',              &
     &          'vbar            ','u               ',              &
     &          'v               ','AKs             ',              &
     &          'unused_1        ','unused_2        '/)
        DO i=1,6
          st=nf90_inq_varid(ncid,TRIM(names(i)),ids(i))
          IF (st.ne.nf90_noerr) THEN
            reason='missing field '//TRIM(names(i))
            GOTO 900
          END IF
        END DO
!  Native NetCDF Fortran dimension order: xi,eta,[s],ocean_time.
        CALL verify_dims(ncid,ids(1),[idxr,idyr,idt],st)
        IF (st.ne.0) GOTO 910
        CALL verify_dims(ncid,ids(2),[idxu,idyu,idt],st)
        IF (st.ne.0) GOTO 910
        CALL verify_dims(ncid,ids(3),[idxv,idyv,idt],st)
        IF (st.ne.0) GOTO 910
        CALL verify_dims(ncid,ids(4),[idxu,idyu,idsr,idt],st)
        IF (st.ne.0) GOTO 910
        CALL verify_dims(ncid,ids(5),[idxv,idyv,idsr,idt],st)
        IF (st.ne.0) GOTO 910
        CALL verify_dims(ncid,ids(6),[idxr,idyr,idsw,idt],st)
        IF (st.ne.0) GOTO 910
        allocate(frame%zeta(nx,ny),frame%ubar(nu,ny))
        allocate(frame%vbar(nx,nv))
        allocate(frame%u(nu,ny,nz),frame%v(nx,nv,nz))
        allocate(frame%AKs(nx,ny,nw))
        st=nf90_get_var(ncid,ids(1),frame%zeta,                 &
     &                  start=[1,1,record],count=[nx,ny,1])
        IF (st.ne.nf90_noerr) GOTO 920
        st=nf90_get_var(ncid,ids(2),frame%ubar,                 &
     &                  start=[1,1,record],count=[nu,ny,1])
        IF (st.ne.nf90_noerr) GOTO 920
        st=nf90_get_var(ncid,ids(3),frame%vbar,                 &
     &                  start=[1,1,record],count=[nx,nv,1])
        IF (st.ne.nf90_noerr) GOTO 920
        st=nf90_get_var(ncid,ids(4),frame%u,                    &
     &                  start=[1,1,1,record],count=[nu,ny,nz,1])
        IF (st.ne.nf90_noerr) GOTO 920
        st=nf90_get_var(ncid,ids(5),frame%v,                    &
     &                  start=[1,1,1,record],count=[nx,nv,nz,1])
        IF (st.ne.nf90_noerr) GOTO 920
        st=nf90_get_var(ncid,ids(6),frame%AKs,                  &
     &                  start=[1,1,1,record],count=[nx,ny,nw,1])
        IF (st.ne.nf90_noerr) GOTO 920
        IF (.not.ALL(ieee_is_finite(frame%zeta)).or.             &
     &      .not.ALL(ieee_is_finite(frame%ubar)).or.              &
     &      .not.ALL(ieee_is_finite(frame%vbar)).or.              &
     &      .not.ALL(ieee_is_finite(frame%u)).or.                 &
     &      .not.ALL(ieee_is_finite(frame%v)).or.                 &
     &      .not.ALL(ieee_is_finite(frame%AKs))) THEN
          reason='nonfinite offline hydrodynamic value'
          GOTO 900
        END IF
        IF (ANY(frame%AKs.lt.0.0_r8)) THEN
          reason='negative AKs in field'
          GOTO 900
        END IF
        ierr=0
        reason='ok'
        st=nf90_close(ncid)
        RETURN
 910    reason='field C-grid dimensions wrong'
        GOTO 900
 920    reason='unable to read history field from record'
 900    st=nf90_close(ncid)
      END SUBROUTINE read_offline_hydro_frame
!
      SUBROUTINE verify_dims (ncid,vid,want,ierr)
        INTEGER, INTENT(in) :: ncid,vid
        INTEGER, INTENT(in) :: want(:)
        INTEGER, INTENT(out) :: ierr
        INTEGER :: ndims, dims(NF90_MAX_VAR_DIMS),st
        ierr=1
        st=nf90_inquire_variable(ncid,vid,ndims=ndims,dimids=dims)
        IF (st.ne.nf90_noerr) RETURN
        IF (ndims.ne.SIZE(want)) RETURN
        IF (ANY(dims(1:ndims).ne.want)) RETURN
        ierr=0
      END SUBROUTINE verify_dims
      END MODULE offline_hydro_reader_mod
#endif
