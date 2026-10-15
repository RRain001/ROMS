"""Real UD1K wet-open-boundary C-grid geometry + synthetic sigma/flux smoke.

Source: independently filtered current Japanese-Sea UD1K grid (Option B).
No parent ES3K ROMS history, velocities, zeta or tracer are provided.
Only *synthetic* one-timestep velocities and zeta=0 test:
 - true U/V native masks, correct side orientation and face widths;
 - physical vertical levels ROMS Vtransform=2 / Vstretching=4 (41 provisional);
 - Hz-weighted depth average matches direct integrated 3D transport;
 - synthetic profiles correctly interpolate across different sigma levels.
Do not confuse these diagnostic checks with an actual `bry.nc` file or
one-way dynamical ROMS nesting acceptance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from ud1k_vertical_flux_primitives import (
    vtransform2_depth,depth_average_velocity,normal_section_flux,
    remap_profiles_in_z)


def _face_section(h:np.ndarray,pm:np.ndarray,pn:np.ndarray,
                  mask_u:np.ndarray,mask_v:np.ndarray,side:str)->dict:
    """Native ROMS normal face: south/north V; west/east U.

    Standard ROMS U normal is +xi; V normal +eta. Side outward orientation
    is east/north +1 and west/south -1. Tangential C-grid face rows are
    deliberately NOT included in normal-section fluxes.
    """
    if side=="south":
        hh=.5*(h[0,:]+h[1,:])
        width=.5*(1/pm[0,:]+1/pm[1,:])
        wet=mask_v[0,:]
        kind="v";sign=-1
    elif side=="north":
        hh=.5*(h[-2,:]+h[-1,:])
        width=.5*(1/pm[-2,:]+1/pm[-1,:])
        wet=mask_v[-1,:]
        kind="v";sign=1
    elif side=="west":
        hh=.5*(h[:,0]+h[:,1])
        width=.5*(1/pn[:,0]+1/pn[:,1])
        wet=mask_u[:,0]
        kind="u";sign=-1
    elif side=="east":
        hh=.5*(h[:,-2]+h[:,-1])
        width=.5*(1/pn[:,-2]+1/pn[:,-1])
        wet=mask_u[:,-1]
        kind="u";sign=1
    else:
        raise ValueError("unsupported open boundary side")
    if hh.shape!=width.shape or wet.shape!=hh.shape or np.any(hh[wet]<=0) or np.any(width[wet]<=0):
        raise ValueError("invalid C-grid face bathymetry / metrics")
    return {"side":side,"kind":kind,"sign":sign,"h_face":hh,
            "width_m":width,"mask_native_normal_face":wet}


def numerical_smoke_grid(h:np.ndarray,pm:np.ndarray,pn:np.ndarray,
                         rho_wet:np.ndarray,
                         mask_u:np.ndarray,mask_v:np.ndarray)->dict:
    h=np.asarray(h,dtype=float)
    pm=np.asarray(pm,dtype=float)
    pn=np.asarray(pn,dtype=float)
    rho=np.asarray(rho_wet,dtype=bool)
    u=np.asarray(mask_u,dtype=bool)
    v=np.asarray(mask_v,dtype=bool)
    if (h.shape!=(290,438) or pm.shape!=h.shape or pn.shape!=h.shape or
            rho.shape!=h.shape or u.shape!=(290,437) or v.shape!=(289,438)):
        raise ValueError("requires current UD1K exact 290x438 ROMS C-grid")
    if not np.array_equal(u,rho[:,:-1]&rho[:,1:]) or not np.array_equal(v,rho[:-1,:]&rho[1:,:]):
        raise ValueError("face masks inconsistent with RHO wet connectivity")
    if (not np.isfinite(h).all() or not np.isfinite(pm).all() or
            not np.isfinite(pn).all() or np.any(h<=0) or
            np.any(pm<=0) or np.any(pn<=0)):
        raise ValueError("real depth and metrics must be positive")
    reports=[]
    for side in ("south","north","west","east"):
        sec=_face_section(h,pm,pn,u,v,side)
        wet=sec["mask_native_normal_face"]
        if not wet.any():
            reports.append({
                "side":side,"normal_face_type":sec["kind"],
                "native_wet_normal_face_count":0,"outward_sign":sec["sign"],
                "static_geometry_no_open_wet_normal_faces":True})
            continue
        face_depth=sec["h_face"][wet]
        face_width=sec["width_m"][wet]
        nfaces=len(face_depth)
        zeta=np.zeros((1,nfaces),dtype=float)
        # These theta/hc are SYNTHETIC stress parameters, not user-frozen
        # production ROMS physical configuration (which remains undecided).
        z_w=vtransform2_depth(face_depth,zeta,n=41,hc=50.0,
                              theta_s=5.0,theta_b=1.0,at="w")
        z_r=vtransform2_depth(face_depth,zeta,n=41,hc=50.0,
                              theta_s=5.0,theta_b=1.0,at="rho")
        layer_thickness=np.diff(z_w,axis=1)
        if z_w.shape!=(1,42,nfaces) or z_r.shape!=(1,41,nfaces):
            raise ValueError("invalid normal-face sigma-depth dimensions")
        if not np.all(layer_thickness>0):
            raise ValueError("negative wet-layer thickness")
        if not np.allclose(np.sum(layer_thickness,axis=1),face_depth[None,:],rtol=0,atol=5e-10):
            raise ValueError("sigma-layer thickness does not recover local total depth")
        # Diagnostic nonconstant synthetic current; no real ES3K hydrodynamics.
        base=0.2 if sec["kind"]=="u" else -0.1
        current=base+0.07*(z_r/face_depth[None,None,:])
        ubar=depth_average_velocity(current,z_w)
        flux=normal_section_flux(ubar[0],face_depth,face_width,
                                 np.ones(nfaces,bool),sign=sec["sign"])
        flux_3d=float(sec["sign"]*np.sum(current[0]*layer_thickness[0]*
                                         face_width[None,:]))
        err=abs(flux-flux_3d)
        if err>max(1e-7,abs(flux_3d)*1e-11):
            raise ValueError("3D layer-integrated and 2D depth-average face normal flux mismatch")
        # Independent synthetic 30->41 level profile check at true child h.
        src_z=vtransform2_depth(face_depth,zeta,n=30,hc=40.0,
                                theta_s=7.0,theta_b=2.0,at="rho")
        q=np.full_like(src_z,23.4)
        mapped=remap_profiles_in_z(src_z,q,z_r)
        if not np.allclose(mapped["values"],23.4,rtol=0,atol=1e-12):
            raise ValueError("synthetic constant source scalar lost in physical sigma-z transfer")
        reports.append({
            "side":side,"normal_face_type":sec["kind"],
            "native_wet_normal_face_count":nfaces,"outward_sign":sec["sign"],
            "width_min_m":float(face_width.min()),
            "width_max_m":float(face_width.max()),
            "wet_face_depth_min_m":float(face_depth.min()),
            "wet_face_depth_max_m":float(face_depth.max()),
            "synthetic_sigma_nlevels":41,"synthetic_parent_sigma_nlevels":30,
            "synthetic_vtransform":2,"synthetic_vstretching":4,
            "synthetic_hc_m":50.0,"synthetic_theta_s":5.0,"synthetic_theta_b":1.0,
            "synthetic_3d_normal_flux_m3_per_s":flux_3d,
            "synthetic_2d_normal_flux_m3_per_s":flux,
            "sigma_z_max_layer_sum_error_m":float(np.max(abs(np.sum(layer_thickness,axis=1)-face_depth[None,:]))),
            "depth_mean_vs_3d_flux_absolute_error_m3_per_s":float(err),
            "synthetic_constant_scalar_sigma_transfer":"PASS",
            "synthetic_scalar_vertical_clamp_below_count":int(mapped["clamped_below_parent_bottom"]),
            "synthetic_scalar_vertical_clamp_above_count":int(mapped["clamped_above_parent_top"]),
            "actual_parent_roms_velocity_and_zeta_data":"NOT_RUN",
        })
    return {
        "scope":"REAL_UD1K_CORE_SHORELINE_CLEAR_CGRID_GRID_METRICS_SYNTHETIC_SIGMA_FLUX_SMOKE",
        "normal_open_sides":"SOUTH_NORTH_V_AND_WEST_EAST_U_ONLY",
        "wet_normal_face_count":int(sum(r["native_wet_normal_face_count"] for r in reports)),
        "normal_sections":reports,
        "all_real_rho_masks_and_bathymetry_unchanged":True,
        "one_way_parent_roms_history_available":False,
        "physical_velocity_boundary_bry_netcdf":"NOT_RUN",
        "true_time_dependent_mass_flux_conservation":"NOT_RUN",
        "actual_child_roms_model_integration":"NOT_RUN",
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("child-grid","output-json"):
        ap.add_argument("--"+name,type=Path,required=True)
    args=ap.parse_args()
    with Dataset(args.child_grid) as f:
        arrays={key:np.asarray(f[key][:]) for key in (
            "h","pm","pn","mask_rho","mask_u","mask_v")}
    report=numerical_smoke_grid(arrays["h"],arrays["pm"],arrays["pn"],
                                arrays["mask_rho"],arrays["mask_u"],arrays["mask_v"])
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2)+"\n")
    print("UD1K_REAL_GEOMETRY_SYNTHETIC_SIGMA_AND_NORMAL_FLUX",json.dumps({
        "normal_wet_face_count":report["wet_normal_face_count"],
        "sections":[{
            "side":r["side"],"wet":r["native_wet_normal_face_count"],
            "integrated_flux_vs_ubar_error":r.get("depth_mean_vs_3d_flux_absolute_error_m3_per_s",0)
        } for r in report["normal_sections"]],
        "dynamic_ES3K_roms_history":"NOT_AVAILABLE",
        "physical_boundary":"NOT_RUN",
    },sort_keys=True))
    print("THIS_IS_SYNTHETIC_PHYSICS_NUMERIC_SMOKE_NOT_REAL_ROMs_BRY")


if __name__=="__main__":
    main()
