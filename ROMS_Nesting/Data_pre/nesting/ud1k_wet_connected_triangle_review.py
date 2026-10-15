"""Second-tier 3x3, wet-graph-connected coastal RHO triangle diagnostic.

Only invoked for *original* 27 wet boundary positions that failed the
strict same-parent-2x2 triple. This is a larger, still bounded static
candidate family; never substitute for verified ROMS one-way bry physics.
"""
from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
import json
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset
from pyproj import CRS, Transformer
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, Point

_ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(_ROOT))
from ud1k_wet_triangle_review import (_barycentric, _crosses_coast,
                                      _shoreline_parts)
from shoreline import BoundingBox


def _local_connected(wet: np.ndarray, nodes: np.ndarray) -> bool:
    """Require a <=3x3 fully local 4-neighbor wet path between 3 donors."""
    if len(nodes)!=3 or len({tuple(x) for x in nodes})!=3:
        return False
    low=np.min(nodes,axis=0);high=np.max(nodes,axis=0)
    if np.any(high-low>2):
        return False
    j0,i0=map(int,low);j1,i1=map(int,high)
    if j0<0 or i0<0 or j1>=wet.shape[0] or i1>=wet.shape[1]:
        return False
    local={(j0+j,i0+i) for j,i in np.argwhere(wet[j0:j1+1,i0:i1+1])}
    if not all(tuple(x) in local for x in nodes):
        return False
    visited={tuple(nodes[0])}
    todo=list(visited)
    while todo:
        j,i=todo.pop()
        for n in ((j-1,i),(j+1,i),(j,i-1),(j,i+1)):
            if n in local and n not in visited:
                visited.add(n)
                todo.append(n)
    return all(tuple(x) in visited for x in nodes)


def _dry_node_inside_triangle(xy: np.ndarray, wet: np.ndarray,
                              nodes: np.ndarray, triangle: np.ndarray) -> bool:
    """Reject triangles enclosing GEBCO/GSHHG dry RHO nodes in their 3x3 patch."""
    lo=np.min(nodes,axis=0);hi=np.max(nodes,axis=0)
    j0,i0=map(int,lo);j1,i1=map(int,hi)
    sub=wet[j0:j1+1,i0:i1+1]
    if sub.all():
        return False
    dry_xy=xy[j0:j1+1,i0:i1+1][~sub]
    poly=Polygon(triangle)
    return any(poly.covers(Point(x)) for x in dry_xy)


def classify_connected(parent_xy: np.ndarray,parent_lonlat: np.ndarray,
                       wet: np.ndarray,target_xy: np.ndarray,
                       coast_parts: list,*,parent_cell_m:float) -> dict:
    """Bounded local proposals; coast or dry-RHO conflicts fail closed."""
    mask=np.asarray(wet,dtype=bool)
    coords=np.argwhere(mask)
    pts=parent_xy[mask]
    tree=cKDTree(pts)
    max_dist=2.8*parent_cell_m
    neighbors=tree.query_ball_point(target_xy,r=max_dist)
    geometric=0
    connected=0
    land_conflict=0
    coast_conflict=0
    safe=[]
    for trip in combinations(neighbors,3):
        nodes=coords[list(trip)]
        if np.any(np.ptp(nodes,axis=0)>2):
            continue
        triangle=parent_xy[nodes[:,0],nodes[:,1]]
        bary=_barycentric(triangle,target_xy)
        if bary is None:
            continue
        geometric+=1
        if not _local_connected(mask,nodes):
            continue
        connected+=1
        if _dry_node_inside_triangle(parent_xy,mask,nodes,triangle):
            land_conflict+=1
            continue
        corners=parent_lonlat[nodes[:,0],nodes[:,1]]
        if _crosses_coast(corners,coast_parts):
            coast_conflict+=1
            continue
        safe.append({
            "donor_eta_xi_zero_based":nodes.astype(int).tolist(),
            "donor_lonlat":corners.astype(float).tolist(),
            "weights":bary.astype(float).tolist(),
            "sum_weights":float(bary.sum()),
            "min_weight":float(bary.min()),
            "max_donor_distance_m":float(np.linalg.norm(triangle-target_xy,axis=1).max()),
            "wet_four_neighbor_path_in_local_3x3":True,
            "no_dry_rho_node_inside_triangle":True,
            "GSHHG_L1_coastline_intersection":False,
            "local_index_span_eta_xi":np.ptp(nodes,axis=0).astype(int).tolist(),
        })
    safe.sort(key=lambda x:x["max_donor_distance_m"])
    if safe:
        status="CONNECTED_3X3_COASTLINE_CLEAR_STATIC_CANDIDATE"
    elif land_conflict or coast_conflict:
        status="THREE_WET_3X3_GEOMETRY_BUT_LAND_OR_COAST_CONFLICT"
    else:
        status="NO_COASTLINE_CLEAR_CONNECTED_3X3_TRIANGLE"
    return {
        "status":status,
        "nearby_wet_parent_rho_points":len(neighbors),
        "geometric_enclosing_triangles":geometric,
        "connected_local_candidates":connected,
        "reject_dry_parent_rho_containment":land_conflict,
        "reject_GSHHG_coastline":coast_conflict,
        "safe_candidate_count":len(safe),
        "selected_candidate":safe[0] if safe else None,
    }


def review_connected(parent:Path,child:Path,strict_json:Path,gshhg_base:Path,
                     *,coast_resolution:str="h") -> dict:
    first=json.loads(strict_json.read_text())
    if first["scope"]!="ONLY_27_CURRENT_UD1K_PRELIMINARY_RHO_COASTAL_STENCIL_GAPS":
        raise ValueError("require current 27-point strict evidence")
    if len(first["records"])!=27 or sum(first["status_counts"].values())!=27:
        raise ValueError("strict report is incomplete")
    with Dataset(parent) as f:
        wet=np.asarray(f["mask_rho"][:],dtype=bool)
        lon=np.asarray(f["lon_rho"][:],dtype=float)
        lat=np.asarray(f["lat_rho"][:],dtype=float)
        pm=np.asarray(f["pm"][:],dtype=float)
        pn=np.asarray(f["pn"][:],dtype=float)
    with Dataset(child) as f:
        clon=np.asarray(f["lon_rho"][:],dtype=float)
        clat=np.asarray(f["lat_rho"][:],dtype=float)
        cmask=np.asarray(f["mask_rho"][:],dtype=bool)
    if cmask.shape!=(290,438):
        raise ValueError("unexpected child scope")
    unresolved=[r for r in first["records"] if r["status"]==
                "NO_ENCLOSING_LOCAL_THREE_WET_PARENT_RHO_TRIANGLE"]
    if len(unresolved)!=22:
        raise ValueError("strict candidate baseline drift")
    target_lonlat=np.array([[r["child_lon"],r["child_lat"]] for r in unresolved])
    bbox=BoundingBox(float(target_lonlat[:,0].min()-.15),
                     float(target_lonlat[:,0].max()+.15),
                     float(target_lonlat[:,1].min()-.15),
                     float(target_lonlat[:,1].max()+.15))
    coast,meta=_shoreline_parts(gshhg_base,bbox,resolution=coast_resolution)
    if not coast:
        raise ValueError("must screen against real GSHHG shoreline")
    crs=CRS.from_proj4(f"+proj=aeqd +lat_0={float(lat.mean())} +lon_0={float(lon.mean())} +datum=WGS84 +units=m +no_defs")
    trans=Transformer.from_crs("EPSG:4326",crs,always_xy=True)
    px,py=trans.transform(lon,lat)
    tx,ty=trans.transform(target_lonlat[:,0],target_lonlat[:,1])
    p_xy=np.stack((px,py),axis=-1)
    parent_lonlat=np.stack((lon,lat),axis=-1)
    cell_m=float(np.median(1/np.sqrt(pm*pn)))
    results=[]
    for r,x in zip(unresolved,np.column_stack((tx,ty))):
        j,i=int(r["child_eta_rho_zero_based"]),int(r["child_xi_rho_zero_based"])
        if not cmask[j,i] or abs(clon[j,i]-r["child_lon"])>1e-9 or abs(clat[j,i]-r["child_lat"])>1e-9:
            raise ValueError("receiver point disagrees with wet mask/coordinates")
        classified=classify_connected(p_xy,parent_lonlat,wet,x,coast,parent_cell_m=cell_m)
        results.append({"child_eta_rho_zero_based":j,"child_xi_rho_zero_based":i,
                        "child_lon":float(r["child_lon"]),"child_lat":float(r["child_lat"]),
                        **classified})
    counts=dict(Counter(r["status"] for r in results))
    return {
        "scope":"SECOND_TIER_ONLY_22_CURRENT_UD1K_UNSUPPORTED_SAME_2x2_QUAD_RHO",
        "reference_strict":Path(strict_json).name,
        "source_parent":Path(parent).name,
        "source_child":Path(child).name,
        "real_GSHHG_version":"2.3.7_L1_"+coast_resolution,
        "GSHHG_parts_loaded":len(coast),
        "parent_median_cell_m":cell_m,
        "max_donor_target_distance_m":2.8*cell_m,
        "method":"THREE_WET_RHO_IN_LOCAL_3x3_INDEX_BBOX_PLUS_GRAPH_WET_CONNECTED_PLUS_NO_DRY_VERTEX_INTERIOR_PLUS_GSHHG",
        "status_counts":counts,
        "strict_first_tier_coastline_clear":5,
        "reviewed_unresolved_first_tier":len(results),
        "records":results,
        "physical_validation":"NOT_RUN",
        "full_roms_boundary_and_flux_acceptance":"NOT_RUN",
        "masks_modified":False,
        "caveat":"A connected wet 3x3 + GSHHG-clear triangle is a static candidate, NOT a validated ROMS boundary interpolation. No triangle is not proof a waterway is unresolvable.",
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("parent-grid","child-grid","strict-json","gshhg-base","output-json"):
        ap.add_argument("--"+name,required=True,type=Path)
    ap.add_argument("--gshhg-resolution",choices=("h","f"),default="h")
    args=ap.parse_args()
    d=review_connected(args.parent_grid,args.child_grid,args.strict_json,
                       args.gshhg_base,coast_resolution=args.gshhg_resolution)
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(d,indent=2)+"\n")
    print("CURRENT_UD1K_REMAINING_22_CONNECTED_3X3_COUNTS",
          json.dumps(d["status_counts"],sort_keys=True))
    print("PROPOSALS_ARE_STATIC_PRELIMINARY_ONLY")


if __name__=="__main__":
    main()
