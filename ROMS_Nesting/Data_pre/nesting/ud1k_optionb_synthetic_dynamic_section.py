"""Archived REAL UD1K Option B native geometry + SYNTHETIC time-varying 41-level velocity.

This test explicitly mixes REAL validated GEBCO/GSHHG child h/angle/pm/pn/
mask with SYNTHETIC smooth geographic E/N profiles and changing zeta.
It checks target C-grid native face integration at 3 time frames, not real
ES3K history, source transport matching or UD1K physical acceptance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

try:
    from ud1k_boundary_remap_preview import physical_z
    from ud1k_boundary_normal_flux_preview import (
        add_native_normal_face,new_flux_audit,finalize_flux_audit)
    from ud1k_real_optionb_manifest_contract import read_masked_grid,EXPECTED_NORMAL
except ImportError:
    from .ud1k_boundary_remap_preview import physical_z
    from .ud1k_boundary_normal_flux_preview import (
        add_native_normal_face,new_flux_audit,finalize_flux_audit)
    from .ud1k_real_optionb_manifest_contract import read_masked_grid,EXPECTED_NORMAL

FRAME_SECONDS=(0.,1800.,3600.)
ZETA_METERS=(.4,1.0,1.6)
N=41
CHILD_SIGMA={"hc":50.,"theta_s":5.,"theta_b":1.,
             "Vtransform":2,"Vstretching":4}


def synthetic_geographic_velocity(z:np.ndarray,seconds:float)->tuple[np.ndarray,np.ndarray]:
    """Analytical depth- and time-variable geographic reference signal."""
    z=np.asarray(z,dtype=float)
    if not np.isfinite(z).all() or not np.isfinite(seconds):
        raise ValueError("synthetic physical depth or time invalid")
    return .20+.0002*z+seconds*1e-5,-.10+.0001*z+seconds*2e-5


def dynamic_optionb_sections(grid_path:Path,*,n:int=N)->dict:
    if not isinstance(n,int) or n<2 or n>80:
        raise ValueError("bounded synthetic sigma levels required")
    masks,geom=read_masked_grid(grid_path)
    with Dataset(grid_path) as ds:
        h=np.asarray(ds["h"][:],dtype=float)
        a=np.asarray(ds["angle"][:],dtype=float)
        pm=np.asarray(ds["pm"][:],dtype=float)
        pn=np.asarray(ds["pn"][:],dtype=float)
    report=new_flux_audit(len(FRAME_SECONDS))
    for side,kind,sign in (("south","v",-1),("north","v",1),
                           ("west","u",-1),("east","u",1)):
        m=masks[kind]
        if side=="south":
            receivers=((0,i) for i in range(m.shape[1]) if m[0,i])
        elif side=="north":
            receivers=((m.shape[0]-1,i) for i in range(m.shape[1]) if m[-1,i])
        elif side=="west":
            receivers=((j,0) for j in range(m.shape[0]) if m[j,0])
        else:
            receivers=((j,m.shape[1]-1) for j in range(m.shape[0]) if m[j,-1])
        # materialize at most the observed ~400 native face positions
        face_list=list(receivers)
        if len(face_list)!=EXPECTED_NORMAL[side]:
            raise ValueError("real candidate B native wet normal face count mismatch")
        for j,i in face_list:
            if kind=="u":
                face_h=.5*(h[j,i]+h[j,i+1])
                # Angle is periodic. Mean sin/cos instead of raw degree mean.
                face_a=np.arctan2(np.sin(a[j,i])+np.sin(a[j,i+1]),
                                  np.cos(a[j,i])+np.cos(a[j,i+1]))
            else:
                face_h=.5*(h[j,i]+h[j+1,i])
                face_a=np.arctan2(np.sin(a[j,i])+np.sin(a[j+1,i]),
                                  np.cos(a[j,i])+np.cos(a[j+1,i]))
            for t,(seconds,surface) in enumerate(zip(FRAME_SECONDS,ZETA_METERS)):
                z=physical_z(face_h,surface,n,CHILD_SIGMA)
                z_w=physical_z(face_h,surface,n,CHILD_SIGMA,at="w")
                east,north=synthetic_geographic_velocity(z,seconds)
                profile=(east*np.cos(face_a)+north*np.sin(face_a) if kind=="u"
                         else -east*np.sin(face_a)+north*np.cos(face_a))
                hz=np.diff(z_w)
                depth=float(face_h+surface)
                bar=float(np.dot(profile,hz)/depth)
                add_native_normal_face(
                    report,side,t,kind,j,i,pm,pn,z_w,profile,bar,depth)
    report=finalize_flux_audit(report)
    if report["total_wet_normal_face_samples"]!=sum(EXPECTED_NORMAL.values())*len(FRAME_SECONDS):
        raise ValueError("synthetic real-geometry section sample total differs")
    report.update({
        "source":"ACTUAL_ARCHIVED_OPTION_B_GEBCO_GSHHG_GRID_SYNTHETIC_CURRENT",
        "test_case":"THREE_FRAMES_0_1800_3600_SECONDS_CHANGING_ZETA_PLUS_41LEVEL_VERTICAL_SHEAR",
        "source_history":"SYNTHETIC_GEOGRAPHIC_VELOCITY_NO_REAL_PARENT_HISTORY",
        "zeta_m":[float(v) for v in ZETA_METERS],
        "source_bathymetry":"REAL_GEBCO2026_CANDIDATE_B_NOT_ACTIVE",
        "source_angle_pm_pn":"REAL_CGRID_OPTION_B",
        "candidate_grid_shape":list(masks["rho"].shape),
        "parent_history_time_interpolation":"NOT_RUN_IN_THIS_STATIC_GEOMETRY_TEST",
        "parent_to_child_mass_conservation":"NOT_RUN",
        "real_ud1k_bry":"NOT_RUN",
        "real_ocean_physics":"NOT_RUN",
    })
    return report


def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--report-json",type=Path,required=True)
    args=p.parse_args()
    d=dynamic_optionb_sections(args.grid)
    args.report_json.parent.mkdir(parents=True,exist_ok=True)
    args.report_json.write_text(json.dumps(d,indent=2)+"\n")
    print("UD1K_REAL_OPTIONB_GEOMETRY_SYNTHETIC_TIME_SHEAR_2D3D_PASS",json.dumps({
        "times":len(FRAME_SECONDS),"layers":N,
        "wet_face_samples":d["total_wet_normal_face_samples"],
        "max_section_relative_error":d["max_section_2d_vs_3d_relative_mismatch"],
        "real_ocean":"NOT_RUN"},sort_keys=True))


if __name__=="__main__":
    main()
