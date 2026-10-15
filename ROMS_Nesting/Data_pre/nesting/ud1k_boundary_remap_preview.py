"""Source-history-driven ROMS boundary remap NUMERICAL PREVIEW (not bry.nc).

Consumes parent ES3K history, independently audited child RHO/U/V perimeter
stencils, and target C-grid grid with explicit child sigma parameters.
Computes each wet receiver using parent **native staggered U/V faces** for
each donor and physical-z remap *before horizontal mixing*, then local
parent angle rotation -> East/North -> child face axes. Child ubar/vbar
are recomputed from child three-dimensional velocity and local layer Hz.

Interpolates actual parent history frames in CF-ocean_time *numeric units*,
requiring target timestamps in the source range (no time extrapolation).
The companion strict history contract should be run first on source input.
Every target perimeter wet RHO/U/V must be mapped, even on dry-only sides
where zeros are merely internal placeholder values.

Status: experimental numeric engine and synthetic-source CI ONLY.
Not conservative parent-child normal transport matching, not scientific
boundary conditions, NOT a production bry.nc writer/ROMS acceptance.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

try:
    from ud1k_vertical_flux_primitives import stretching4
    from ud1k_parent_history_contract import validate_parent_history
    from ud1k_boundary_normal_flux_preview import (
        NORMAL_KIND,new_flux_audit,add_native_normal_face,finalize_flux_audit)
    from ud1k_cf_time_bridge import bridge_target_to_parent_cf_time
except ImportError:
    from .ud1k_vertical_flux_primitives import stretching4
    from .ud1k_parent_history_contract import validate_parent_history
    from .ud1k_boundary_normal_flux_preview import (
        NORMAL_KIND,new_flux_audit,add_native_normal_face,finalize_flux_audit)
    from .ud1k_cf_time_bridge import bridge_target_to_parent_cf_time

SIDES=("south","north","west","east")
FIELDS=("zeta","temp","salt","u","v","ubar","vbar")


def physical_z(h:float,zeta:float,n:int,params:dict,*,at:str="rho")->np.ndarray:
    h=float(h);zeta=float(zeta)
    if not np.isfinite(h+zeta) or h<=0 or h+zeta<=0:
        raise ValueError("nonpositive wet water column in physical z interpolation")
    s,c=stretching4(n,float(params["theta_s"]),float(params["theta_b"]),at=at)
    hc=float(params["hc"])
    if not np.isfinite(hc) or hc<=0:
        raise ValueError("hc must be finite and positive")
    return zeta+(zeta+h)*(hc*s+h*c)/(hc+h)


def _finite(a)->np.ndarray:
    return np.asarray(np.ma.filled(np.ma.asarray(a,dtype=float),np.nan))


def _perimeter(mask:np.ndarray)->set[tuple[int,int]]:
    wet=np.asarray(mask,dtype=bool)
    boundary=np.zeros_like(wet,dtype=bool)
    boundary[0,:]=boundary[-1,:]=True
    boundary[:,0]=boundary[:,-1]=True
    return set(map(tuple,np.argwhere(wet&boundary)))


def _validated_maps(parent_wet:np.ndarray,child:Dataset,rho_rows:list[dict],
                    face_reports:dict)->dict:
    """Refuse incomplete, duplicated, dry or non-coast-checked source maps."""
    pw=np.asarray(parent_wet,dtype=bool)
    maps={}
    for kind,rows in (("rho",rho_rows),
                      ("u",face_reports["u"]["records"]),
                      ("v",face_reports["v"]["records"])):
        wet=_finite(child["mask_"+kind][:]).astype(bool)
        found={}
        for row in rows:
            if kind=="rho":
                key=(int(row["child_eta_rho_zero_based"]),
                     int(row["child_xi_rho_zero_based"]))
                sources=row["donor_eta_xi_zero_based"]
                clear=row.get("coastline_visible",False)
            else:
                key=(int(row["child_eta_face_zero_based"]),
                     int(row["child_xi_face_zero_based"]))
                sources=row["donor_parent_rho_eta_xi_zero_based"]
                clear=row.get("GSHHG_L1_coastline_clear",False)
            if key in found or not clear:
                raise ValueError("duplicate receiver or uncertified GSHHG source")
            if not (0<=key[0]<wet.shape[0] and 0<=key[1]<wet.shape[1] and wet[key]):
                raise ValueError("mapped receiver is not wet or is out of child grid")
            ij=np.asarray(sources,dtype=int)
            w=np.asarray(row["weights"],dtype=float)
            if (ij.ndim!=2 or ij.shape[1]!=2 or len(w)!=len(ij) or
                not len(w) or not np.isfinite(w).all() or (w<0).any() or
                abs(float(w.sum())-1)>1e-10):
                raise ValueError("invalid certified donor geometry/weights")
            if (np.any(ij[:,0]<0) or np.any(ij[:,0]>=pw.shape[0]) or
                np.any(ij[:,1]<0) or np.any(ij[:,1]>=pw.shape[1]) or
                not pw[ij[:,0],ij[:,1]].all()):
                raise ValueError("donor at dry/outside parent RHO position")
            if kind in ("u","v") and not row.get("native_parent_U_and_V_wet_face_support",False):
                raise ValueError("velocity donor lacks certified native wet U/V support")
            found[key]=list(zip(map(tuple,ij.tolist()),w.tolist()))
        if set(found)!=_perimeter(wet):
            missing=_perimeter(wet)-set(found)
            raise ValueError(f"incomplete native {kind} wet perimeter map: missing={len(missing)}")
        maps[kind]=found
    return maps


def _adjacent_native(wet:np.ndarray,j:int,i:int,kind:str)->list[tuple[int,int]]:
    ny,nx=wet.shape
    if kind=="u":
        return [(j,ii) for ii in (i-1,i) if 0<=ii<nx-1 and wet[j,ii] and wet[j,ii+1]]
    if kind=="v":
        return [(jj,i) for jj in (j-1,j) if 0<=jj<ny-1 and wet[jj,i] and wet[jj+1,i]]
    raise ValueError("unknown native component")


def validate_source_donor_native_support(maps:dict,parent_wet:np.ndarray)->dict:
    """Recheck BOTH true U/V wet parent faces, not just JSON audit flags.

    This check runs against the ACTUAL supplied ES3K parent mask when a real
    history becomes available. Test-only fixtures do not prove real I3 wetness.
    """
    wet=np.asarray(parent_wet,dtype=bool)
    checked=set()
    for kind in ("u","v"):
        for receivers in maps[kind].values():
            for (j,i),weight in receivers:
                if (j,i) in checked:
                    continue
                # Even a zero-weight but listed donor must be physically
                # valid; otherwise a broken source mask can hide in JSON.
                if not _adjacent_native(wet,j,i,"u") or not _adjacent_native(wet,j,i,"v"):
                    raise ValueError(f"certified parent native U/V donor has no actual wet face at {(j,i)}")
                checked.add((j,i))
    return {"parent_rho_nodes_checked_for_both_native_faces":len(checked),
            "actual_parent_wet_UV_face_support":"PASS_AGAINST_SUPPLIED_PARENT_MASK",
            "coastline_l1_intersection_recomputed":"NOT_RUN_RELY_ON_GSHHG_MANIFEST"}


def _native_face_h_zeta(h:np.ndarray,zeta:np.ndarray,j:int,i:int,kind:str)->tuple[float,float]:
    if kind=="u":
        return (.5*(h[j,i]+h[j,i+1]),.5*(zeta[j,i]+zeta[j,i+1]))
    return (.5*(h[j,i]+h[j+1,i]),.5*(zeta[j,i]+zeta[j+1,i]))


def _face_target(h:np.ndarray,zeta:np.ndarray,angle:np.ndarray,
                 j:int,i:int,kind:str)->tuple[float,float,float]:
    if kind=="u":
        return (float(.5*(h[j,i]+h[j,i+1])),
                float(.5*(zeta[j,i]+zeta[j,i+1])),
                float(.5*(angle[j,i]+angle[j,i+1])))
    return (float(.5*(h[j,i]+h[j+1,i])),
            float(.5*(zeta[j,i]+zeta[j+1,i])),
            float(.5*(angle[j,i]+angle[j+1,i])))


def _source_profile(v:np.ndarray,z_source:np.ndarray,z_target:np.ndarray,
                    counter:Counter)->np.ndarray:
    if (len(v)!=len(z_source) or not np.isfinite(v).all() or
        not np.isfinite(z_source).all() or not np.all(np.diff(z_source)>0)):
        raise ValueError("invalid parent wet native sigma profile")
    counter["clamped_below"]+=int(np.sum(z_target<z_source[0]))
    counter["clamped_above"]+=int(np.sum(z_target>z_source[-1]))
    return np.interp(z_target,z_source,v,left=v[0],right=v[-1])


def _parent_native_component(frame:dict,h:np.ndarray,wet:np.ndarray,params:dict,
                             j:int,i:int,kind:str,target_z:np.ndarray,
                             counter:Counter)->np.ndarray:
    faces=_adjacent_native(wet,j,i,kind)
    if not faces:
        raise ValueError("missing wet native U/V face at certified donor")
    n=frame[kind].shape[0]
    values=[]
    for fj,fi in faces:
        faceh,facezeta=_native_face_h_zeta(h,frame["zeta"],fj,fi,kind)
        src_z=physical_z(faceh,facezeta,n,params)
        source_w=physical_z(faceh,facezeta,n,params,at="w")
        source_ubar=float(np.sum(frame[kind][:,fj,fi]*np.diff(source_w))/(faceh+facezeta))
        recorded=float(frame["ubar" if kind=="u" else "vbar"][fj,fi])
        if not np.isfinite(source_ubar) or not np.isfinite(recorded):
            raise ValueError("nonfinite parent wet C-grid barotropic source field")
        counter["max_parent_native_barotropic_mismatch_mps"]=max(
            counter["max_parent_native_barotropic_mismatch_mps"],abs(source_ubar-recorded))
        values.append(_source_profile(frame[kind][:,fj,fi],src_z,target_z,counter))
    return np.mean(values,axis=0)


def _sample_scalar(frame:dict,grid_h:np.ndarray,src_params:dict,
                   source:list,target_z:np.ndarray,field:str,counter:Counter)->np.ndarray:
    result=np.zeros_like(target_z)
    for (j,i),weight in source:
        if weight==0:continue
        v=frame[field][:,j,i]
        z=physical_z(grid_h[j,i],frame["zeta"][j,i],len(v),src_params)
        result+=weight*_source_profile(v,z,target_z,counter)
    return result


def _vector_profile(frame:dict,parent_h:np.ndarray,parent_wet:np.ndarray,
                    parent_angle:np.ndarray,src_params:dict,
                    donors:list,target_z:np.ndarray,target_angle:float,
                    kind:str,counter:Counter)->np.ndarray:
    east=np.zeros_like(target_z);north=np.zeros_like(target_z)
    for (j,i),weight in donors:
        if weight==0:continue
        u=_parent_native_component(frame,parent_h,parent_wet,src_params,
                                   j,i,"u",target_z,counter)
        v=_parent_native_component(frame,parent_h,parent_wet,src_params,
                                   j,i,"v",target_z,counter)
        ap=parent_angle[j,i]
        east+=weight*(u*np.cos(ap)-v*np.sin(ap))
        north+=weight*(u*np.sin(ap)+v*np.cos(ap))
    return (east*np.cos(target_angle)+north*np.sin(target_angle) if kind=="u"
            else -east*np.sin(target_angle)+north*np.cos(target_angle))


def _frame_at(history:Dataset,request:float)->dict:
    times=_finite(history["ocean_time"][:])
    if len(times)<2 or not np.all(np.diff(times)>0):
        raise ValueError("parent history timestamps not strictly increasing")
    if request<times[0] or request>times[-1]:
        raise ValueError("child requested timestamp outside parent history coverage")
    k=int(np.searchsorted(times,request,side="right"))
    if k>=len(times):lo=hi=len(times)-1
    elif k==0:lo=hi=0
    else:
        lo=k-1
        hi=k
        if request==times[lo]:hi=lo
    alpha=0. if hi==lo else float((request-times[lo])/(times[hi]-times[lo]))
    return {field:(
        _finite(history[field][lo]) if hi==lo
        else (1-alpha)*_finite(history[field][lo])+alpha*_finite(history[field][hi])
    ) for field in FIELDS}


def prepare_boundary_preview(parent_grid:Path,parent_history:Path,child_grid:Path,
                             rho_map:dict,face_maps:dict,
                             child_times:np.ndarray,*,child_n:int,
                             child_params:dict,
                             target_time_units:str|None=None,
                             target_time_calendar:str|None=None,
                             max_parent_gap_hours:float=3.)->tuple[dict,dict]:
    """Prepare all four sides from certified maps and real *or fixture* source.

    Returned arrays are experimental and must NOT be labeled production bry.
    Parent history should additionally pass validate_parent_history(...).
    """
    if not isinstance(child_n,int) or child_n<2:
        raise ValueError("child sigma layer count invalid")
    if not (set(child_params)=={"hc","theta_s","theta_b","Vtransform","Vstretching"}
            and child_params["Vtransform"]==2 and child_params["Vstretching"]==4):
        raise ValueError("explicit child ROMS Vtransform2/Vstretching4 metadata required")
    times=np.asarray(child_times,dtype=float)
    if times.ndim!=1 or len(times)<2 or not np.isfinite(times).all() or not (np.diff(times)>0).all():
        raise ValueError("requested child times must be strictly increasing")
    source_admission=validate_parent_history(parent_grid,parent_history,scan_values=True)
    if not source_admission["full_wet_values_scanned"]:
        raise ValueError("ES3K history full-wet-data admission not passed")
    with Dataset(parent_grid) as pg,Dataset(parent_history) as hs,Dataset(child_grid) as cg:
        pw=_finite(pg["mask_rho"][:]).astype(bool)
        parenth=_finite(pg["h"][:]);parentangle=_finite(pg["angle"][:])
        childh=_finite(cg["h"][:]);childangle=_finite(cg["angle"][:])
        if childh.shape!=childangle.shape or parenth.shape!=parentangle.shape:
            raise ValueError("parent/child h/angle shape mismatch")
        if not np.isfinite(childh).all() or not np.isfinite(childangle).all():
            raise ValueError("invalid child bathymetry/angle values")
        for kind in ("rho","u","v"):
            raw=_finite(cg["mask_"+kind][:])
            if not np.isin(raw,(0,1)).all():
                raise ValueError("child native wet masks must be finite binary")
        child_wet=_finite(cg["mask_rho"][:]).astype(bool)
        if (childh[child_wet]<=0).any():
            raise ValueError("nonpositive actual wet child bathymetry")
        masku=_finite(cg["mask_u"][:]).astype(bool)
        maskv=_finite(cg["mask_v"][:]).astype(bool)
        if (not np.array_equal(masku,child_wet[:,:-1]&child_wet[:,1:]) or
                not np.array_equal(maskv,child_wet[:-1,:]&child_wet[1:,:])):
            raise ValueError("child staggered wet face mask inconsistent with RHO mask")
        if ("pm" in cg.variables)!=("pn" in cg.variables):
            raise ValueError("child native normal flux requires BOTH pm and pn")
        has_metrics="pm" in cg.variables
        if has_metrics:
            childpm=_finite(cg["pm"][:])
            childpn=_finite(cg["pn"][:])
            if (childpm.shape!=childh.shape or childpn.shape!=childh.shape or
                    not np.isfinite(childpm).all() or not np.isfinite(childpn).all() or
                    (childpm<=0).any() or (childpn<=0).any()):
                raise ValueError("child ROMS pm/pn metrics invalid")
            normal_flux=new_flux_audit(len(times))
        else:
            normal_flux=None
            childpm=childpn=None
        maps=_validated_maps(pw,cg,rho_map["records"],face_maps["reports"])
        child_masks={k:_finite(cg["mask_"+k][:]).astype(bool) for k in ("rho","u","v")}
        src_params={k:float(hs[k][()]) for k in ("theta_s","theta_b","hc")}
        if int(hs["Vtransform"][()])!=2 or int(hs["Vstretching"][()])!=4:
            raise ValueError("unsupported parent vertical transform")
        n_parent=len(hs.dimensions["s_rho"])
        tvar=hs["ocean_time"]
        time_bridge=bridge_target_to_parent_cf_time(
            times,_finite(tvar[:]),
            parent_units=tvar.units,
            parent_calendar=getattr(tvar,"calendar","standard"),
            target_units=target_time_units,
            target_calendar=target_time_calendar,
            max_gap_hours=max_parent_gap_hours)
        source_frame_times=time_bridge["parent_time_values"]
        source_support=validate_source_donor_native_support(maps,pw)
        for key in FIELDS:
            if key not in hs.variables:
                raise ValueError("missing ES3K physical source history field "+key)
        arrays={}
        for kind in ("rho","u","v"):
            field_names=("zeta","temp","salt") if kind=="rho" else (
                ("u","ubar") if kind=="u" else ("v","vbar"))
            wet=child_masks[kind]
            side_data={}
            for side in SIDES:
                width=wet.shape[1] if side in ("south","north") else wet.shape[0]
                for field in field_names:
                    shp=(len(times),child_n,width) if field in ("temp","salt","u","v") else (len(times),width)
                    side_data[field+"_"+side]=np.zeros(shp,dtype=float)
            arrays[kind]=side_data
        extrapolated=Counter()
        for t_index,when in enumerate(source_frame_times):
            frame=_frame_at(hs,float(when))
            zeta_child_by_kind={}
            for kind in ("rho","u","v"):
                data=maps[kind]
                target_zeta={}
                for (j,i),src in data.items():
                    target_zeta[j,i]=float(sum(weight*frame["zeta"][sj,si]
                                                for (sj,si),weight in src))
                    if not np.isfinite(target_zeta[j,i]):
                        raise ValueError("missing parent sea surface at accepted wet receiver")
                zeta_child_by_kind[kind]=target_zeta
            for (j,i),src in maps["rho"].items():
                surface=zeta_child_by_kind["rho"][j,i]
                target=physical_z(childh[j,i],surface,child_n,child_params)
                value={
                    "zeta":surface,
                    "temp":_sample_scalar(frame,parenth,src_params,src,target,"temp",extrapolated),
                    "salt":_sample_scalar(frame,parenth,src_params,src,target,"salt",extrapolated),
                }
                for side in SIDES:
                    mask=child_masks["rho"]
                    if not (j==0 if side=="south" else j==mask.shape[0]-1 if side=="north"
                            else i==0 if side=="west" else i==mask.shape[1]-1):
                        continue
                    index=i if side in ("south","north") else j
                    for field,v in value.items():
                        arrays["rho"][field+"_"+side][t_index,...,index]=v
            for kind in ("u","v"):
                wet=child_masks[kind]
                for (j,i),src in maps[kind].items():
                    # Interpolate zeta directly at the *same child face*.
                    surface=zeta_child_by_kind[kind][j,i]
                    targeth,_,ac=_face_target(childh,np.zeros_like(childh),
                                             childangle,j,i,kind)
                    target_z=physical_z(targeth,surface,child_n,child_params)
                    profile=_vector_profile(frame,parenth,pw,parentangle,src_params,
                                            src,target_z,ac,kind,extrapolated)
                    z_w=physical_z(targeth,surface,child_n,child_params,at="w")
                    bar=float(np.sum(profile*np.diff(z_w))/(surface+targeth))
                    if not np.isfinite(bar):
                        raise ValueError("child barotropic reconstructed velocity nonfinite")
                    for side in SIDES:
                        if not (j==0 if side=="south" else j==wet.shape[0]-1 if side=="north"
                                else i==0 if side=="west" else i==wet.shape[1]-1):
                            continue
                        index=i if side in ("south","north") else j
                        arrays[kind][kind+"_"+side][t_index,:,index]=profile
                        arrays[kind][("ubar" if kind=="u" else "vbar")+"_"+side][t_index,index]=bar
                        if normal_flux is not None and NORMAL_KIND[side]==kind:
                            add_native_normal_face(
                                normal_flux,side,t_index,kind,j,i,childpm,childpn,
                                z_w,profile,bar,surface+targeth)
        prepared={side:{name:arrays["rho" if name in ("zeta","temp","salt")
                                  else "u" if name in ("u","ubar") else "v"][name+"_"+side]
                        for name in FIELDS} for side in SIDES}
        for kind,mapped in maps.items():
            for side in SIDES:
                wet=child_masks[kind]
                w=wet[0,:] if side=="south" else wet[-1,:] if side=="north" else (
                    wet[:,0] if side=="west" else wet[:,-1])
                for fld in ("zeta","temp","salt") if kind=="rho" else (
                    ("u","ubar") if kind=="u" else ("v","vbar")):
                    data=prepared[side][fld]
                    if not np.isfinite(data[...,w]).all():
                        raise ValueError("preview failed to assign finite values to wet boundary")
        flux_report=(finalize_flux_audit(normal_flux) if normal_flux is not None else
                     {"status":"NOT_RUN_MISSING_CHILD_PM_PN_GRID_METRICS",
                      "parent_to_child_mass_conservation":"NOT_RUN"})
        return prepared,{
            "scope":"SOURCE_HISTORY_BASED_ROMS_BOUNDARY_NUMERICAL_PREVIEW",
            "native_normal_section_flux_diagnostic":flux_report,
            "status":"EXPERIMENTAL_NOT_PRODUCTION_BRY",
            "source_history":Path(parent_history).name,
            "full_source_history_admission":"PASS",
            "source_native_donor_support":source_support,
            "source_target_CF_time_bridge":{
                k: v.tolist() if isinstance(v,np.ndarray) else v
                for k,v in time_bridge.items()},
            "target_grid":Path(child_grid).name,
            "time_count":len(times),"source_vertical_N":n_parent,
            "target_vertical_N":child_n,
            "wet_receivers_by_native_kind":{k:len(v) for k,v in maps.items()},
            "physical_z_profile_endpoint_clamps":dict(extrapolated),
            "parent_native_2d_vs_3d_barotropic_mismatch_max_mps":float(
                extrapolated["max_parent_native_barotropic_mismatch_mps"]),
            "parent_native_barotropic_mismatch_acceptance":"DIAGNOSTIC_ONLY",
            "parent_field_time_interpolation":"PIECEWISE_LINEAR_INSIDE_HISTORY_TIME_RANGE",
            "source_velocity_collocation":"WET_NATIVE_PARENT_U_AND_V_FACES_AT_PARENT_RHO_DONORS",
            "child_velocity_rotation":"PARENT_GRID_TO_GEOGRAPHIC_TO_CHILD_GRID",
            "child_barotropic_velocity":"RECOMPUTED_USING_TARGET_HZ",
            "barotropic_mass_transport_comparison_with_source":"NOT_RUN",
            "real_roms_bry_nc":"NOT_RUN",
            "actual_roms_model_integration":"NOT_RUN",
        }
