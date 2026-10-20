"""Read-only 27-point nearshore parent-wet visible fallback stencil audit.

This is a deliberately explicit coastal **extrapolation** preflight, not a
claim of physical ROMS nesting or a replacement for valid 4/3 wet templates.

Targets with no enclosing local triangle may still receive a *bounded*,
nonnegative wet-only inverse-distance stencil, but ONLY if every donor:
- is wet on the actual parent mask, belongs to the same local four-neighbor
  connected wet graph as the closest accepted parent wet donor;
- lies within a hard radius of 2.5 median parent grid spacings;
- has a direct target-to-donor line that does not intersect the real
  GSHHG v2.3.7 L1 coastline, including tangential touches;
- never uses zero or negative weights, dry/land vertices, distant donors
  across peninsula or nearest-unchecked filling.

The result is a candidate, NOT a production boundary implementation. Actual
physical `bry.nc` needs C-grid U/V, vertical remap, time, flux checks.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, deque
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset
from pyproj import CRS, Transformer
from scipy.spatial import cKDTree
from shapely.geometry import LineString

_THIS=Path(__file__).resolve().parent
sys.path.insert(0,str(_THIS))
from ud1k_wet_triangle_review import _shoreline_parts
from shoreline import BoundingBox


def _segment_crosses_coast(source_ll:np.ndarray,receiver_ll:np.ndarray,
                           coast_parts:list) -> bool:
    """Reject all contact with real shoreline rings; never bridge islands."""
    xmin=min(float(source_ll[0]),float(receiver_ll[0]))
    xmax=max(float(source_ll[0]),float(receiver_ll[0]))
    ymin=min(float(source_ll[1]),float(receiver_ll[1]))
    ymax=max(float(source_ll[1]),float(receiver_ll[1]))
    ray=LineString([tuple(source_ll),tuple(receiver_ll)])
    for bounds,coords in coast_parts:
        if (bounds[2]<xmin or bounds[0]>xmax or
                bounds[3]<ymin or bounds[1]>ymax):
            continue
        if ray.intersects(LineString(coords)):
            return True
    return False


def _connected_subset(wet:np.ndarray,from_ij:tuple[int,int],
                      candidate_indices:list[tuple[int,int]],
                      *,max_hops:int=8)->set[tuple[int,int]]:
    """Retain donors 4-wet-connected within short source-grid graph paths."""
    if not wet[from_ij]:
        raise ValueError("nonwet root of wet graph")
    wanted=set(candidate_indices)
    visited={from_ij}
    frontier=deque([(from_ij,0)])
    allowed=set()
    while frontier:
        (j,i),h=frontier.popleft()
        if (j,i) in wanted:
            allowed.add((j,i))
        if h>=max_hops:
            continue
        for a,b in ((j-1,i),(j+1,i),(j,i-1),(j,i+1)):
            if 0<=a<wet.shape[0] and 0<=b<wet.shape[1] and wet[a,b] and (a,b) not in visited:
                visited.add((a,b))
                frontier.append(((a,b),h+1))
    return allowed


def classify_visible_wet_donors(parent_xy:np.ndarray,parent_lonlat:np.ndarray,
                               wet:np.ndarray,target_xy:np.ndarray,
                               target_lonlat:np.ndarray,coast_parts:list,*,
                               median_cell_m:float,max_cell_radius:float=2.5,
                               max_donors:int=4,max_graph_hops:int=8) ->dict:
    """Build at most four coastline-visible wet donors using capped IDW.

    There is no enclosing-triangle claim. A single donor uses weight 1 as
    controlled extrapolation and MUST be evaluated for scientific impact.
    """
    if median_cell_m<=0 or max_cell_radius<=0 or max_donors<1:
        raise ValueError("invalid donor search parameters")
    if parent_xy.shape != (*wet.shape,2) or parent_lonlat.shape!=parent_xy.shape:
        raise ValueError("invalid parent geometry")
    nodes=np.argwhere(wet)
    if not len(nodes):
        return {"status":"NO_PARENT_WET_DONOR","selected_donors":[]}
    tree=cKDTree(parent_xy[wet])
    max_d=max_cell_radius*median_cell_m
    ids=tree.query_ball_point(target_xy,r=max_d)
    distances=np.linalg.norm(parent_xy[nodes[ids,0],nodes[ids,1]]-target_xy[None,:],axis=1) if len(ids) else np.empty(0)
    order=np.argsort(distances,kind="stable")
    candidates=[]
    rejected_coast=0
    for q in order:
        idx=int(ids[int(q)])
        j,i=map(int,nodes[idx])
        distance=float(distances[int(q)])
        if _segment_crosses_coast(parent_lonlat[j,i],target_lonlat,coast_parts):
            rejected_coast+=1
            continue
        candidates.append(((j,i),distance))
    if not candidates:
        return {"status":"NO_VISIBLE_PARENT_WET_DONOR_WITHIN_RADIUS",
                "search_radius_m":float(max_d),"nearby_parent_wet":len(ids),
                "rejected_GSHHG_L1_coastline":rejected_coast,"selected_donors":[]}
    # Graph root is *the nearest truly coastline-visible wet parent*;
    # otherwise an across-land nearest source may anchor the wrong basin.
    root=candidates[0][0]
    connected=_connected_subset(wet,root,[c[0] for c in candidates],max_hops=max_graph_hops)
    chosen=[(idx,d) for idx,d in candidates if idx in connected][:max_donors]
    if not chosen:
        raise AssertionError("visible wet root must be connected to itself")
    d=np.array([v for _,v in chosen],dtype=float)
    if d.min()<1e-6:
        w=np.where(d<1e-6,1.0,0.0)
    else:
        w=1/np.maximum(d,1.)**2
    w/=w.sum()
    if not np.isfinite(w).all() or min(w)<0 or not np.isclose(w.sum(),1,atol=1e-12):
        raise AssertionError("invalid bounded wet interpolation weights")
    donors=[]
    for (j,i),dist,weight in zip([a for a,_ in chosen],d,w):
        donors.append({"eta_rho_zero_based":j,"xi_rho_zero_based":i,
                       "lon":float(parent_lonlat[j,i,0]),
                       "lat":float(parent_lonlat[j,i,1]),
                       "target_distance_m":float(dist),"weight":float(weight),
                       "visible_water_segment_no_GSHHG_L1_intersection":True})
    return {
        "status":("MULTI_DONOR_COAST_VISIBLE_IDW_EXTRAPOLATION_CANDIDATE"
                  if len(chosen)>=2 else "SINGLE_DONOR_COAST_VISIBLE_EXTRAPOLATION_CANDIDATE"),
        "extrapolation_not_enclosing_interpolation":True,
        "search_radius_m":float(max_d),
        "nearby_parent_wet":len(ids),
        "visible_parent_wet_before_graph_filter":len(candidates),
        "rejected_GSHHG_L1_coastline":rejected_coast,
        "max_graph_hops":max_graph_hops,
        "selected_donors":donors,
        "weights_sum":float(w.sum()),
        "max_selected_distance_m":float(d.max()),
    }


def audit(parent:Path,child:Path,first_tier:Path,second_tier:Path,
          gshhg_base:Path,*,resolution:str="h")->dict:
    strict=json.loads(first_tier.read_text())
    second=json.loads(second_tier.read_text())
    if len(strict["records"])!=27 or len(second["records"])!=22:
        raise ValueError("not the agreed 27 current UD1K baseline")
    remaining=[r for r in second["records"] if r["status"]!="CONNECTED_3X3_COASTLINE_CLEAR_STATIC_CANDIDATE"]
    if len(remaining)!=20:
        raise ValueError("not the agreed 20 residuals")
    with Dataset(parent) as f:
        pwet=np.asarray(f["mask_rho"][:],dtype=bool)
        plon=np.asarray(f["lon_rho"][:],dtype=float)
        plat=np.asarray(f["lat_rho"][:],dtype=float)
        pm=np.asarray(f["pm"][:],dtype=float)
        pn=np.asarray(f["pn"][:],dtype=float)
    with Dataset(child) as f:
        cwet=np.asarray(f["mask_rho"][:],dtype=bool)
        clon=np.asarray(f["lon_rho"][:],dtype=float)
        clat=np.asarray(f["lat_rho"][:],dtype=float)
    if cwet.shape != (290,438):
        raise ValueError("not the frozen UD1K")
    lo=np.asarray([[r["child_lon"],r["child_lat"]] for r in remaining],dtype=float)
    bbox=BoundingBox(float(lo[:,0].min()-.15),float(lo[:,0].max()+.15),
                     float(lo[:,1].min()-.15),float(lo[:,1].max()+.15))
    coast,meta=_shoreline_parts(gshhg_base,bbox,resolution=resolution)
    if not coast:
        raise ValueError("GSHHG coastline source missing")
    crs=CRS.from_proj4(f"+proj=aeqd +lat_0={plat.mean()} +lon_0={plon.mean()} +datum=WGS84 +units=m +no_defs")
    trans=Transformer.from_crs("EPSG:4326",crs,always_xy=True)
    x,y=trans.transform(plon,plat)
    tx,ty=trans.transform(lo[:,0],lo[:,1])
    pxy=np.stack((x,y),axis=-1)
    pll=np.stack((plon,plat),axis=-1)
    cell=float(np.median(1/np.sqrt(pm*pn)))
    rows=[]
    for p,target,receiver in zip(remaining,np.column_stack((tx,ty)),lo):
        j=int(p["child_eta_rho_zero_based"]);i=int(p["child_xi_rho_zero_based"])
        if not cwet[j,i] or abs(clon[j,i]-receiver[0])>1e-9 or abs(clat[j,i]-receiver[1])>1e-9:
            raise ValueError("child baseline coordinates changed")
        status=classify_visible_wet_donors(pxy,pll,pwet,target,receiver,coast,
                                             median_cell_m=cell)
        rows.append({"child_eta_rho_zero_based":j,"child_xi_rho_zero_based":i,
                     "child_lon":float(receiver[0]),"child_lat":float(receiver[1]),
                     "prior_connected_3x3_status":p["status"],**status})
    counts=dict(Counter(v["status"] for v in rows))
    return {
        "scope":"THE_20_REMAINING_CURRENT_USER_UD1K_RHO_WET_BOUNDARY_POINTS_ONLY",
        "parent":parent.name,"child":child.name,
        "real_GSHHG":"v2.3.7_high_level1",
        "source_GSHHG_file":str(meta.shapefile_path),
        "wet_parent_median_cell_m":cell,
        "max_distance_parent_cell_units":2.5,
        "coastal_segment_crossing":"REJECTED_EVEN_TOUCHING_LINEWORK",
        "wet_parent_four_neighbor_graph_max_hops":8,
        "method":"BOUNDED_WET_ONLY_LINE_OF_SIGHT_AND_CONNECTED_GRAPH_IDW_EXTRAPOLATION",
        "distance_kernel":"INVERSE_SQUARE_DISTANCE_WITH_NONNEGATIVE_UNIT_SUM",
        "status_counts":counts,"records":rows,
        "prior_seven_enclosing_triangle_static_candidates":7,
        "physical_validation":"NOT_RUN",
        "source_masks_modified":False,
        "disposition":"STATIC_WET_BOUNDARY_MAPPING_CANDIDATES_NOT_PRODUCTION_BRY",
        "warning":"A candidate from >=1 nearby coastline-visible donor is an EXTRAPOLATION, not 2D enclosing interpolation. It does NOT validate ROMS U/V, vertical remap, lateral mass flux or circulation.",
    }


def main()->None:
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("parent-grid","child-grid","strict-json","connected-json","gshhg-base","output-json"):
        ap.add_argument("--"+name,type=Path,required=True)
    args=ap.parse_args()
    report=audit(args.parent_grid,args.child_grid,args.strict_json,
                 args.connected_json,args.gshhg_base)
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2)+"\n")
    print("UD1K_20_BOUNDARY_WET_VISIBLE_FALLBACK",json.dumps(report["status_counts"],sort_keys=True))
    print("CAUTION: STATIC_NONENCLOSING_EXTRAPOLATION_ONLY")


if __name__=="__main__":
    main()
