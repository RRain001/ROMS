"""Experimental UD1K wet *normal* boundary flux accounting (m3/s).

Accumulates independent Hz-integrated 3D velocity and barotropic 2D
velocity flux through real native child U/V faces using C-grid pm/pn,
outward signs and *the same native-face zeta* used to remap velocity.
This is numerical self-consistency only, NOT a parent/child mass-budget
or hydrodynamic conservation certificate.
"""
from __future__ import annotations

import numpy as np

NORMAL_KIND={"south":"v","north":"v","west":"u","east":"u"}
OUTWARD={"south":-1,"north":1,"west":-1,"east":1}


def wet_face_width_m(kind:str,j:int,i:int,pm:np.ndarray,pn:np.ndarray)->float:
    """Cross-normal face width from adjacent rho-cell inverse metrics."""
    dx=np.asarray(pm,dtype=float)
    dy=np.asarray(pn,dtype=float)
    if dx.ndim!=2 or dy.shape!=dx.shape or kind not in ("u","v"):
        raise ValueError("ROMS pm/pn must share 2D rho geometry")
    if kind=="u":
        a,b=dy[j,i],dy[j,i+1]
    else:
        a,b=dx[j,i],dx[j+1,i]
    if not np.isfinite([a,b]).all() or a<=0 or b<=0:
        raise ValueError("nonpositive/invalid native open-face grid metrics")
    return float(.5*(1/a+1/b))


def new_flux_audit(nt:int)->dict:
    if nt<1:raise ValueError("no timestamps in normal flux audit")
    return {
        "status":"NUMERICAL_2D_3D_TARGET_FACE_FLUX_CONSISTENCY_ONLY",
        "normal_sections":{
            side:[{"wet_native_normal_face_count":0,
                   "outward_volume_flux_3d_m3s":0.,
                   "outward_volume_flux_2d_m3s":0.,
                   "face_2d_vs_3d_max_abs_difference_m3s":0.}
                  for _ in range(nt)]
            for side in NORMAL_KIND
        },
        "parent_to_child_mass_conservation":"NOT_RUN",
        "free_surface_storage_and_tidal_budget":"NOT_RUN",
        "ROMS_hydrodynamic_acceptance":"NOT_RUN",
    }


def add_native_normal_face(audit:dict,side:str,t:int,kind:str,
                           j:int,i:int,pm:np.ndarray,pn:np.ndarray,
                           z_w:np.ndarray,three_d_velocity:np.ndarray,
                           barotropic_velocity:float,water_column_depth:float)->None:
    """Update one wet face; call exactly once for each side/time/normal face."""
    if side not in NORMAL_KIND or kind!=NORMAL_KIND[side]:
        raise ValueError("cannot use tangential/stagger-incompatible velocity in section")
    if not (isinstance(t,int) and 0<=t<len(audit["normal_sections"][side])):
        raise ValueError("invalid time index for normal flux")
    levels=np.asarray(z_w,dtype=float)
    velocity=np.asarray(three_d_velocity,dtype=float)
    if (levels.ndim!=1 or velocity.ndim!=1 or levels.size!=velocity.size+1 or
            not np.isfinite(levels).all() or not np.isfinite(velocity).all() or
            not np.isfinite(barotropic_velocity) or not np.isfinite(water_column_depth) or
            water_column_depth<=0):
        raise ValueError("invalid native face velocity/z_w/depth")
    hz=np.diff(levels)
    if (hz<=0).any() or abs(float(hz.sum())-water_column_depth)>1e-8*max(1,water_column_depth):
        raise ValueError("native face Hz levels do not reconstruct h+zeta")
    width=wet_face_width_m(kind,j,i,pm,pn)
    sign=OUTWARD[side]
    q3=sign*width*float(np.sum(velocity*hz))
    q2=sign*width*float(barotropic_velocity*water_column_depth)
    entry=audit["normal_sections"][side][t]
    entry["wet_native_normal_face_count"]+=1
    entry["outward_volume_flux_3d_m3s"]+=q3
    entry["outward_volume_flux_2d_m3s"]+=q2
    entry["face_2d_vs_3d_max_abs_difference_m3s"]=max(
        entry["face_2d_vs_3d_max_abs_difference_m3s"],abs(q3-q2))


def finalize_flux_audit(audit:dict,*,max_relative_error:float=1e-10)->dict:
    """Close individual outward sections without asserting global continuity."""
    all_entries=[entry for side in NORMAL_KIND
                 for entry in audit["normal_sections"][side]]
    worst=0.
    for entry in all_entries:
        a=entry["outward_volume_flux_3d_m3s"]
        b=entry["outward_volume_flux_2d_m3s"]
        scale=max(1.,abs(a),abs(b))
        rel=abs(a-b)/scale
        worst=max(worst,rel)
        if rel>max_relative_error:
            raise ValueError("2D and 3D native section volume flux mismatch")
    audit["max_section_2d_vs_3d_relative_mismatch"]=float(worst)
    audit["total_wet_normal_face_samples"]=sum(
        e["wet_native_normal_face_count"] for e in all_entries)
    audit["normal_face_2d_vs_3d_integration_check"]="PASS"
    return audit
