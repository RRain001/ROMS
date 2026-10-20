"""Audit TRUE wet native UD1K C-grid face connectivity against GSHHG L1.

A face can be wet by mask_rho-pair logic even if the segment connecting
those two RHO centers crosses a fine GSHHG coastline. This is a geometry
warning, not authority to overwrite mask_u or mask_v: assess whether
the crossing represents real topography, shoreline level-1 artifacts or
a local C-grid resolution issue. Never force ocean/land from this test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset

_LOCAL=Path(__file__).resolve().parent
sys.path.insert(0,str(_LOCAL))
from ud1k_coastal_waterpath_fallback import _segment_crosses_coast
from ud1k_wet_triangle_review import _shoreline_parts
from ud1k_staggered_face_map import wet_perimeter_ij
from shoreline import BoundingBox


def crossing_wet_faces(rho_lon:np.ndarray,rho_lat:np.ndarray,
                       rho_wet:np.ndarray,face_kind:str,coast_parts:list)->dict:
    """Check both adjacent RHO centers defining each actual child U/V face."""
    rho=np.asarray(rho_wet,dtype=bool)
    if face_kind=="u":
        face=rho[:,:-1]&rho[:,1:]
    elif face_kind=="v":
        face=rho[:-1,:]&rho[1:,:]
    else:
        raise ValueError("native face kind must be u or v")
    nodes=wet_perimeter_ij(face)
    flagged=[]
    for j,i in nodes:
        j,i=int(j),int(i)
        a=np.array([rho_lon[j,i],rho_lat[j,i]],float)
        b=(np.array([rho_lon[j,i+1],rho_lat[j,i+1]],float) if face_kind=="u"
           else np.array([rho_lon[j+1,i],rho_lat[j+1,i]],float))
        if _segment_crosses_coast(a,b,coast_parts):
            flagged.append({
                "child_eta_face_zero_based":j,"child_xi_face_zero_based":i,
                "rho_endpoint_A_lonlat":a.tolist(),
                "rho_endpoint_B_lonlat":b.tolist(),
                "logical_sides":[s for s,flag in (("south",j==0),("north",j==face.shape[0]-1),
                                  ("west",i==0),("east",i==face.shape[1]-1)) if flag],
                "GSHHG_L1_segment_intersects":True,
            })
    return {
        "native_face_kind":face_kind,
        "wet_perimeter_face_count":int(len(nodes)),
        "wet_face_RHO_to_RHO_segment_crosses_GSHHG_count":len(flagged),
        "flagged_faces":flagged,
        "reason":"ADJACENT_RHO_WET_BUT_SEGMENT_INTERSECTS_GSHHG_L1",
        "child_land_or_Cgrid_mask_edited":False,
    }


def run(child_grid:Path,gshhg_base:Path)->dict:
    with Dataset(child_grid) as f:
        lon=np.asarray(f["lon_rho"][:],float)
        lat=np.asarray(f["lat_rho"][:],float)
        wet=np.asarray(f["mask_rho"][:],bool)
        native_u=np.asarray(f["mask_u"][:],bool)
        native_v=np.asarray(f["mask_v"][:],bool)
    if wet.shape!=(290,438) or not np.array_equal(native_u,wet[:,:-1]&wet[:,1:]) or not np.array_equal(
            native_v,wet[:-1,:]&wet[1:,:]):
        raise ValueError("not the original UD1K native C-grid pair mask")
    bbox=BoundingBox(float(lon.min()-.12),float(lon.max()+.12),
                     float(lat.min()-.12),float(lat.max()+.12))
    coast,meta=_shoreline_parts(gshhg_base,bbox,resolution="h")
    if not coast:
        raise ValueError("GSHHG shoreline source missing")
    reports={kind:crossing_wet_faces(lon,lat,wet,kind,coast)
             for kind in ("u","v")}
    target=(0,30)
    v_hit=next((x for x in reports["v"]["flagged_faces"] if
                (x["child_eta_face_zero_based"],x["child_xi_face_zero_based"])==target),None)
    return {
        "scope":"CURRENT_UD1K_NATIVE_WET_FACE_SEGMENT_GSHHG_L1_CROSSING_REVIEW",
        "child_grid":child_grid.name,
        "GSHHG_v2_3_7_High_L1_shapefile":str(meta.shapefile_path),
        "reports":reports,
        "special_hold_V_face_eta0_xi30_crosses_real_coastline":bool(v_hit),
        "special_hold_face_record":v_hit,
        "masks_mutated":False,
        "conclusion":"GEOMETRIC_CROSSING_ONLY_NOT_AUTOMATIC_LAND_MASK_FIX",
        "hydrodynamic_bry_nc":"NOT_RUN",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("child-grid","gshhg-base","output-json"):
        p.add_argument("--"+name,required=True,type=Path)
    args=p.parse_args()
    result=run(args.child_grid,args.gshhg_base)
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(result,indent=2)+"\n")
    print("UD1K_NATIVE_WET_FACE_RHO_SEGMENT_COASTLINE_CROSSINGS",json.dumps({
        "u":result["reports"]["u"]["wet_face_RHO_to_RHO_segment_crosses_GSHHG_count"],
        "v":result["reports"]["v"]["wet_face_RHO_to_RHO_segment_crosses_GSHHG_count"],
        "special_V_0_30_intersects":result["special_hold_V_face_eta0_xi30_crosses_real_coastline"],
    },sort_keys=True))
    print("NO_MASK_CHANGED_GSHHG_CROSSING_DIAGNOSTIC_ONLY")


if __name__=="__main__":
    main()
