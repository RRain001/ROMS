"""Read-only parent native V-face, water-visible radius sensitivity for V(0,30).

Standard 2.5 ES3K-cell radius found no non-coast-crossing parent native V
source. Do not silently widen the operational mapping: compare strictly
bounded alternatives 2.5, 3.0, 3.5, 4.0, 5.0 median source-cell widths,
keeping GSHHG shoreline and parent C-grid wet-graph connectivity immutable.
Any wider source is a separately disclosed extrapolation risk, NOT a
production ROMS boundary validation.
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
from ud1k_coastal_waterpath_fallback import _segment_crosses_coast
from shoreline import BoundingBox


def test_radii(source_xy:np.ndarray,source_ll:np.ndarray,
               source_wet:np.ndarray,target_xy:np.ndarray,
               target_ll:np.ndarray,coast_parts:list,
               median_parent_cell_m:float)->dict:
    """Constrained source check at fixed predetermined radii, not tuning CI PASS."""
    reports=[]
    for cells in (2.5,3.0,3.5,4.0,5.0):
        report=classify_visible_wet_donors(
            source_xy,source_ll,source_wet,target_xy,target_ll,
            coast_parts,median_cell_m=median_parent_cell_m,
            max_cell_radius=cells,max_donors=4,max_graph_hops=8)
        records=report.get("selected_donors",[])
        reports.append({
            "radius_in_parent_cell_widths":cells,
            "radius_m":float(cells*median_parent_cell_m),
            "status":report["status"],
            "candidate_native_V_face_count":len(records),
            "nearby_parent_wet_faces":int(report.get("nearby_parent_wet",0)),
            "GSHHG_line_of_sight_rejections":int(report.get("rejected_GSHHG_L1_coastline",0)),
            "max_selected_distance_m":report.get("max_selected_distance_m",None),
            "candidates":records,
        })
    min_safe=next((x for x in reports if x["candidate_native_V_face_count"]>0),None)
    return {
        "radii":reports,
        "first_water_visible_radius_parent_cells":None if min_safe is None
                                               else min_safe["radius_in_parent_cell_widths"],
        "first_water_visible_candidate_count":0 if min_safe is None
                                               else min_safe["candidate_native_V_face_count"],
        "no_cross_land_override":True,
        "hydrodynamic_acceptance":"NOT_RUN",
    }


def run(parent:Path,child:Path,gshhg_base:Path)->dict:
    with Dataset(parent) as f:
        wet=np.asarray(f["mask_rho"][:],dtype=bool)
        lon_v=np.asarray(f["lon_v"][:],dtype=float)
        lat_v=np.asarray(f["lat_v"][:],dtype=float)
        mask_v=np.asarray(f["mask_v"][:],dtype=bool)
        plat=np.asarray(f["lat_rho"][:],dtype=float)
        plon=np.asarray(f["lon_rho"][:],dtype=float)
        pm=np.asarray(f["pm"][:],dtype=float)
        pn=np.asarray(f["pn"][:],dtype=float)
    if not np.array_equal(mask_v,wet[:-1,:]&wet[1:,:]):
        raise ValueError("parent native mask_v inconsistent with parent RHO")
    with Dataset(child) as f:
        clat=np.asarray(f["lat_v"][:],dtype=float)
        clon=np.asarray(f["lon_v"][:],dtype=float)
        cmask=np.asarray(f["mask_v"][:],dtype=bool)
        rho_lon=np.asarray(f["lon_rho"][:],dtype=float)
        rho_lat=np.asarray(f["lat_rho"][:],dtype=float)
    j,i=0,30
    if cmask.shape!=(289,438) or not cmask[j,i]:
        raise ValueError("this audit targets only actual wet current UD1K V(0,30)")
    bbox=BoundingBox(float(clon[j,i]-.3),float(clon[j,i]+.3),
                     float(clat[j,i]-.3),float(clat[j,i]+.3))
    coast,_=_shoreline_parts(gshhg_base,bbox,resolution="h")
    if not coast:
        raise ValueError("actual GSHHG high-L1 source unavailable")
    crs=CRS.from_proj4(f"+proj=aeqd +lat_0={plat.mean()} +lon_0={plon.mean()} +datum=WGS84 +units=m +no_defs")
    tf=Transformer.from_crs("EPSG:4326",crs,always_xy=True)
    xx,yy=tf.transform(lon_v,lat_v)
    rx,ry=tf.transform(float(clon[j,i]),float(clat[j,i]))
    median_m=float(np.median(1/np.sqrt(pm*pn)))
    output=test_radii(np.stack((xx,yy),axis=-1),
                      np.stack((lon_v,lat_v),axis=-1),
                      mask_v,np.array([rx,ry]),np.array([clon[j,i],clat[j,i]]),
                      coast,median_m)
    A=np.array([rho_lon[j,i],rho_lat[j,i]])
    B=np.array([rho_lon[j+1,i],rho_lat[j+1,i]])
    output.update({
        "scope":"ONLY_CURRENT_UD1K_WET_NATIVE_V_FACE_ETA0_XI30",
        "child_eta_v_zero_based":j,
        "child_xi_v_zero_based":i,
        "target_v_face_lonlat":[float(clon[j,i]),float(clat[j,i])],
        "child_V_adjacent_two_RHO_endpoints":[A.tolist(),B.tolist()],
        "child_V_face_RHO_neighbor_segment_intersects_GSHHG_L1":
            _segment_crosses_coast(A,B,coast),
        "parent_es3k_native_v_mask_used":True,
        "land_masks_modified":False,
        "widening_does_not_imply_autoadoption":True,
    })
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("parent-grid","child-grid","gshhg-base","output-json"):
        p.add_argument("--"+key,type=Path,required=True)
    a=p.parse_args()
    result=run(a.parent_grid,a.child_grid,a.gshhg_base)
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(result,indent=2)+"\n")
    print("UD1K_LAST_V0_30_NATIVE_ES3K_V_FACE_WATER_VISIBLE_SENSITIVITY",json.dumps({
        "first_visible_radius_cells":result["first_water_visible_radius_parent_cells"],
        "first_visible_donors":result["first_water_visible_candidate_count"],
        "coastline_crosses_child_native_V_face":
            result["child_V_face_RHO_neighbor_segment_intersects_GSHHG_L1"],
        "radius_stats":[(r["radius_in_parent_cell_widths"],
                         r["candidate_native_V_face_count"],
                         r["GSHHG_line_of_sight_rejections"]) for r in result["radii"]],
    },sort_keys=True))
    print("STATIC_DIAGNOSTIC_ONLY_NO_AUTOMATIC_RADIUS_EXTENSION")


if __name__=="__main__":
    main()
