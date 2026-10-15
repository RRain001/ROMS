"""True ES3K native U/V face support for unresolved UD1K staggered faces.

Targets are actual wet *child* U/V faces. Original coastal map uses
parent wet-face-supported RHO-collocated source vectors; if every such
RHO source fails the shoreline line-of-sight test, individually inspect
the ACTUAL parent native U and V face coordinates and masks instead.

A result with both component sets coastline-visible is a static source
potential, not yet a physically faithful C-grid vector remap. In
particular it does not prove barotropic/baroclinic flux conservation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset
from pyproj import CRS, Transformer

_ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(_ROOT))
from ud1k_wet_triangle_review import _shoreline_parts
from ud1k_coastal_waterpath_fallback import classify_visible_wet_donors
from shoreline import BoundingBox


def _native_face_source(parent_face_xy:np.ndarray,parent_face_ll:np.ndarray,
                        parent_face_wet:np.ndarray,target_xy:np.ndarray,
                        target_ll:np.ndarray,coast_parts:list,
                        *,parent_cell_m:float,face_kind:str)->dict:
    """Coastline-visible bounded source native U/V component face audit."""
    support=classify_visible_wet_donors(
        parent_face_xy,parent_face_ll,parent_face_wet,target_xy,target_ll,
        coast_parts,median_cell_m=parent_cell_m,max_cell_radius=2.5,
        max_donors=4,max_graph_hops=8)
    result={
        "parent_component_kind":face_kind,
        "status":support["status"],
        "native_parent_face_mask_used":True,
        "source_location":"ACTUAL_NATIVE_ES3K_LON_LAT_"+face_kind.upper(),
        "coastline_visible_candidate_count":len(support.get("selected_donors",[])),
        "search_radius_m":float(2.5*parent_cell_m),
        "nearby_wet_faces":support.get("nearby_parent_wet",0),
        "rejected_shoreline_rays":support.get("rejected_GSHHG_L1_coastline",0),
        "max_selected_distance_m":support.get("max_selected_distance_m",None),
        "selected_native_component_faces":[{
            "eta_face_zero_based":int(s["eta_rho_zero_based"]),
            "xi_face_zero_based":int(s["xi_rho_zero_based"]),
            "lon":s["lon"],"lat":s["lat"],"weight":s["weight"],
            "distance_m":s["target_distance_m"],
        } for s in support.get("selected_donors",[])],
    }
    return result


def audit(parent:Path,child:Path,staggered_map:Path,gshhg_base:Path)->dict:
    base=json.loads(staggered_map.read_text())
    with Dataset(parent) as f:
        pwet=np.asarray(f["mask_rho"][:],dtype=bool)
        pm=np.asarray(f["pm"][:],dtype=float)
        pn=np.asarray(f["pn"][:],dtype=float)
        plat=np.asarray(f["lat_rho"][:],dtype=float)
        plon=np.asarray(f["lon_rho"][:],dtype=float)
        native={}
        for kind in ("u","v"):
            for prefix in ("lon","lat","mask"):
                key=prefix+"_"+kind
                if key not in f.variables:
                    raise ValueError(f"required genuine ES3K native face missing: {key}")
                native[key]=np.asarray(f[key][:])
    if not np.array_equal(native["mask_u"].astype(bool),pwet[:,:-1]&pwet[:,1:]):
        raise ValueError("source ES3K native U mask not consistent with parent")
    if not np.array_equal(native["mask_v"].astype(bool),pwet[:-1,:]&pwet[1:,:]):
        raise ValueError("source ES3K native V mask not consistent with parent")
    with Dataset(child) as f:
        mask={}
        geographic={}
        for kind in ("u","v"):
            mask[kind]=np.asarray(f["mask_"+kind][:],dtype=bool)
            geographic[kind]=np.stack((np.asarray(f["lon_"+kind][:],dtype=float),
                                      np.asarray(f["lat_"+kind][:],dtype=float)),axis=-1)
    candidates=[]
    for kind,report in base["reports"].items():
        for rec in report["records"]:
            if rec.get("status")=="HOLD_NO_COAST_VISIBLE_CGRID_FACE_SUPPORTED_PARENT_DONORS":
                j,i=int(rec["child_eta_face_zero_based"]),int(rec["child_xi_face_zero_based"])
                if not mask[kind][j,i]:
                    raise ValueError("unresolved target should be wet face")
                actual=geographic[kind][j,i]
                if np.linalg.norm(actual-np.array([rec["child_lon"],rec["child_lat"]]))>1e-9:
                    raise ValueError("native face target coordinate drift")
                candidates.append((kind,j,i,actual))
    if not candidates:
        raise ValueError("no unresolved native face receivers to investigate")
    target=np.stack([a[3] for a in candidates])
    bbox=BoundingBox(float(target[:,0].min()-.3),float(target[:,0].max()+.3),
                     float(target[:,1].min()-.3),float(target[:,1].max()+.3))
    coast,_=_shoreline_parts(gshhg_base,bbox,resolution="h")
    if not coast:
        raise ValueError("real GSHHG source not available")
    crs=CRS.from_proj4(f"+proj=aeqd +lat_0={plat.mean()} +lon_0={plon.mean()} +datum=WGS84 +units=m +no_defs")
    tr=Transformer.from_crs("EPSG:4326",crs,always_xy=True)
    support_fields={}
    for kind in ("u","v"):
        x,y=tr.transform(native["lon_"+kind],native["lat_"+kind])
        support_fields[kind]=(
            np.stack((x,y),axis=-1),
            np.stack((native["lon_"+kind],native["lat_"+kind]),axis=-1),
            native["mask_"+kind].astype(bool))
    cell=float(np.median(1/np.sqrt(pm*pn)))
    records=[]
    for kind,j,i,ll in candidates:
        x,y=tr.transform(float(ll[0]),float(ll[1]))
        target_xy=np.array([x,y])
        face_sources={}
        for src in ("u","v"):
            xy,geo,wet=support_fields[src]
            face_sources[src]=_native_face_source(
                xy,geo,wet,target_xy,ll,coast,
                parent_cell_m=cell,face_kind=src)
        pair=all(len(v["selected_native_component_faces"]) for v in face_sources.values())
        records.append({
            "child_face_kind":kind,"child_eta_face_zero_based":j,
            "child_xi_face_zero_based":i,
            "child_lon":float(ll[0]),"child_lat":float(ll[1]),
            "status":("BOTH_COMPONENTS_HAVE_NATIVE_FACE_COAST_VISIBLE_SOURCES"
                      if pair else "HOLD_TRUE_NATIVE_FACE_COMPONENT_UNSUPPORTED"),
            "parent_true_native_component_stencils":face_sources,
        })
    return {
        "scope":"ONLY_UNRESOLVED_ACTUAL_UD1K_STAGGERED_FACE_RECEIVERS",
        "original_face_report":staggered_map.name,
        "real_parent_ES3K_UV_native_face_masks_verified":True,
        "native_face_search_radius_parent_cells":2.5,
        "receiver_count":len(records),
        "two_component_visible_source_candidates":sum(
            r["status"]=="BOTH_COMPONENTS_HAVE_NATIVE_FACE_COAST_VISIBLE_SOURCES" for r in records),
        "remains_unresolved":sum(r["status"]=="HOLD_TRUE_NATIVE_FACE_COMPONENT_UNSUPPORTED" for r in records),
        "receiver_source_records":records,
        "physical_UV_rotation_and_bry_flux":"NOT_RUN",
        "land_masks_modified":False,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("parent-grid","child-grid","staggered-map","gshhg-base","output-json"):
        p.add_argument("--"+name,required=True,type=Path)
    args=p.parse_args()
    result=audit(args.parent_grid,args.child_grid,args.staggered_map,args.gshhg_base)
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(result,indent=2)+"\n")
    print("UD1K_TRUE_ES3K_PARENT_UV_NATIVE_FACE_COASTAL_HOLD_REVIEW",json.dumps({
        "targets":result["receiver_count"],
        "both_parent_components_visible":result["two_component_visible_source_candidates"],
        "still_unsupported":result["remains_unresolved"]},sort_keys=True))
    print("NATIVE_COMPONENT_SOURCE_STATIC_DIAGNOSTIC_NOT_ROMs_BRY")


if __name__=="__main__":
    main()
