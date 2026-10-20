"""ROMS Vtransform=2 / Vstretching=4 physical-depth and flux primitives.

Reference: repository roms_src/roms/ROMS/Utility/set_scoord.F, Vstretching=4
(Shchepetkin) and standard ROMS Vtransform=2 equations. These tools are
for testable preparation of true parent-history sigma-z to child-sigma
remapping, *not* yet an accepted operational ROMS bry.nc generator.

ROMS uses ascending k from bottom to surface; z_w has N+1 interfaces.
"""
from __future__ import annotations

import numpy as np


def stretching4(n:int,theta_s:float,theta_b:float,*,at:str="rho")->tuple[np.ndarray,np.ndarray]:
    """Reproduce ROMS set_scoord Vstretching=4 sc and Cs curves."""
    if not (isinstance(n,(int,np.integer)) and n>1):
        raise ValueError("N must be integer >1")
    if not (0<=theta_s<=10 and 0<=theta_b<=3
            and np.isfinite(theta_s) and np.isfinite(theta_b)):
        raise ValueError("invalid Vstretching4 theta_s/theta_b")
    if at=="rho":
        s=(np.arange(1,n+1,dtype=float)-n-.5)/n
    elif at=="w":
        s=(np.arange(n+1,dtype=float)-n)/n
    else:
        raise ValueError("at must be 'rho' or 'w'")
    if theta_s>0:
        c_surface=(1-np.cosh(theta_s*s))/(np.cosh(theta_s)-1)
    else:
        c_surface=-s*s
    if theta_b>0:
        c=(np.exp(theta_b*c_surface)-1)/(1-np.exp(-theta_b))
    else:
        c=c_surface
    return s,c


def vtransform2_depth(h:np.ndarray,zeta:np.ndarray,*,n:int,
                      hc:float,theta_s:float,theta_b:float,
                      at:str="rho")->np.ndarray:
    """Physical z(m): trailing h-space shape supports arbitrary 1D/2D grids.

    Leading dimensions in zeta may include time; h is one geometry-only
    slice and is never broadcast as a sigma/time axis.
    Returns z[...,nz,*h.shape], positive upwards.
    """
    depth=np.asarray(h,dtype=float)
    surface=np.asarray(zeta,dtype=float)
    if depth.ndim not in (1,2):
        raise ValueError("h must be 1D/2D actual wet geometry")
    if surface.shape[-depth.ndim:]!=depth.shape:
        raise ValueError("zeta trailing dimensions must equal h")
    if (not np.isfinite(depth).all() or (depth<=0).any()
            or not np.isfinite(surface).all()
            or np.any(surface+depth<=0)
            or not np.isfinite(hc) or hc<=0):
        raise ValueError("nonfinite/invalid h, zeta or hc")
    s,c=stretching4(n,theta_s,theta_b,at=at)
    broadcast_shape=(1,)* (surface.ndim-depth.ndim) + depth.shape
    h_b=depth.reshape(broadcast_shape)
    z0=(hc*s.reshape((-1,)+(1,)*surface.ndim)+
        h_b.reshape((1,)+broadcast_shape)*c.reshape((-1,)+(1,)*surface.ndim))/(
            hc+h_b.reshape((1,)+broadcast_shape))
    # For shape (time, n, y, x), move sigma axis behind time.
    lead=surface.ndim-depth.ndim
    z0=np.moveaxis(z0,0,lead)
    surface_advanced=np.expand_dims(surface,axis=lead)
    depth_advanced=np.expand_dims(h_b,axis=lead)
    z=surface_advanced+(surface_advanced+depth_advanced)*z0
    if not np.all(np.diff(z,axis=lead)>0):
        raise ValueError("non-monotonic physical sigma depth")
    return z


def remap_profiles_in_z(parent_z:np.ndarray,parent_values:np.ndarray,
                        child_z:np.ndarray,*,vertical_endpoint_policy:str="clamp")->dict:
    """Piecewise linear *physical depth* remap, preserving constant fields.

    Input arrays (time, nz_parent, columns) and (time,nz_child,columns).
    For h/zeta mismatch, endpoint values are explicitly clamped with
    per-target out-of-parent-range statistics, never hidden extrapolation.
    """
    zp=np.asarray(parent_z,dtype=float)
    val=np.asarray(parent_values,dtype=float)
    zc=np.asarray(child_z,dtype=float)
    if (zp.ndim!=3 or zp.shape!=val.shape or zc.ndim!=3 or
            zp.shape[0]!=zc.shape[0] or zp.shape[2]!=zc.shape[2] or
            zp.shape[1]<2 or zc.shape[1]<1):
        raise ValueError("expected (time,nz,columns) physical depth profiles")
    if vertical_endpoint_policy!="clamp":
        raise ValueError("only explicit clamp endpoint policy supported")
    if (not np.isfinite(zp).all() or not np.isfinite(val).all() or
            not np.isfinite(zc).all() or np.any(np.diff(zp,axis=1)<=0) or
            np.any(np.diff(zc,axis=1)<=0)):
        raise ValueError("invalid profiles or nonmonotonic physical z")
    nt,nzchild,ncol=zc.shape
    output=np.empty((nt,nzchild,ncol),dtype=float)
    below=above=0
    for t in range(nt):
        for p in range(ncol):
            bottom=float(zp[t,0,p])
            top=float(zp[t,-1,p])
            below+=int(np.sum(zc[t,:,p]<bottom))
            above+=int(np.sum(zc[t,:,p]>top))
            output[t,:,p]=np.interp(
                zc[t,:,p],zp[t,:,p],val[t,:,p],
                left=val[t,0,p],right=val[t,-1,p])
    if not np.isfinite(output).all():
        raise ValueError("nonfinite output")
    return {"values":output,"clamped_below_parent_bottom":below,
            "clamped_above_parent_top":above,
            "physical_vertical_acceptance":"NOT_RUN"}


def depth_average_velocity(vel:np.ndarray,interfaces_z:np.ndarray)->np.ndarray:
    """Hz-weighted ubar/vbar along face-normal columns (no flux correction)."""
    u=np.asarray(vel,dtype=float)
    z=np.asarray(interfaces_z,dtype=float)
    if u.ndim<2 or z.ndim!=u.ndim or z.shape[-2]!=u.shape[-2]+1 or z.shape[-1]!=u.shape[-1]:
        raise ValueError("velocity, interface z must have matching face columns")
    Hz=np.diff(z,axis=-2)
    if not np.isfinite(Hz).all() or not np.isfinite(u).all() or (Hz<=0).any():
        raise ValueError("nonpositive layer thickness or invalid velocity")
    return np.sum(u*Hz,axis=-2)/np.sum(Hz,axis=-2)


def normal_section_flux(ubar:np.ndarray,water_column_depth:np.ndarray,
                        face_width_m:np.ndarray,wet_mask:np.ndarray,*,sign:int)->float:
    """One outward-oriented section face flux, m^3/s; diagnostic only.

    A user-configured outward sign +/-1 is compulsory: the orientation of
    U and V normal velocity depends on south/north/east/west side.
    """
    u=np.asarray(ubar,dtype=float)
    depth=np.asarray(water_column_depth,dtype=float)
    width=np.asarray(face_width_m,dtype=float)
    mask=np.asarray(wet_mask,dtype=bool)
    if sign not in (-1,1) or u.shape!=depth.shape or depth.shape!=width.shape or width.shape!=mask.shape:
        raise ValueError("section arrays mismatch or invalid outward sign")
    if (not np.isfinite(u).all() or not np.isfinite(depth).all()
            or not np.isfinite(width).all() or
            (depth[mask]<=0).any() or (width[mask]<=0).any()):
        raise ValueError("invalid wet section")
    return float(sign*np.sum(u[mask]*depth[mask]*width[mask]))
