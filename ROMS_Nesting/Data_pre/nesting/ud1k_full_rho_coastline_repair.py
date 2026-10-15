"""Read-only targeted repair of GSHHG-crossing donor QUADS in full UD1K RHO map.

Priority 1: For each GSHHG-crossing all-wet parent donor RHO quad,
           select an enclosing 3-of-4-wet-vertex triangle that does NOT
           intersect GSHHG L1 shoreline, with positive barycentric weights.
Priority 2: For points with no such triangle, require bounded coastline-
           visible wet-parent extrapolation, from a 4-neighbor connected
           donor graph and with no land crossing. Never overwrite land masks.

Diagnostic only; no actual U/V, sigma remap, `bry.nc` or ROMS integration.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset
from pyproj import CRS, Transformer

_THIS=Path(__file__).resolve().parent
sys.path.insert(0,str(_THIS))
from ud1k_wet_triangle_review import _shoreline_parts,_crosses_coast,_barycentric
from ud1k_coastal_waterpath_fallback import classify_visible_wet_donors
from ud1k_boundary_rho_fallback_map import apply_scalar_stencils
from shoreline import BoundingBox


def choose_coastline_safe_triangle(parent_xy:np.ndarray,
                                  parent_lonlat:np.ndarray,
                                  parent_wet:np.ndarray,
                                  chosen_quad_nodes:list,
                                  receiver_xy:np.ndarray,
                                  coastline_parts:list)->dict|None:
    """Choose any of four 3-of-4 vertices, all wet, enclosed and coast clear."""
    indices=np.asarray(chosen_quad_nodes,dtype=int)
    if indices.shape!=(4,2):
        raise ValueError("expected four ordered quad nodes")
    results=[]
    for omit in range(4):
        nodes=np.delete(indices,omit,axis=0)
        if not parent_wet[nodes[:,0],nodes[:,1]].all():
            continue
        xy=parent_xy[nodes[:,0],nodes[:,1]]
        weight=_barycentric(xy,receiver_xy)
        if weight is None:
            continue
        lonlat=parent_lonlat[nodes[:,0],nodes[:,1]]
        if _crosses_coast(lonlat,coastline_parts):
            continue
        maxdist=float(np.linalg.norm(xy-receiver_xy[None,:],axis=1).max())
        results.append({
            "method":"COASTLINE_CLEAR_THREE_OF_FOUR_WET_PARENT_RHO_TRIANGLE",
            "donor_eta_xi_zero_based":nodes.astype(int).tolist(),
            "weights":weight.astype(float).tolist(),
            "maximum_donor_distance_m":maxdist,
            "enclosing_geometry":True,
            "coastline_visible":True,
            "GSHHG_level1_coastline_intersection":False,
            "source_kind":"TARGETED_GSHHG_PARENT_QUAD_COASTLINE_REPAIR",
        })
    return min(results,key=lambda a:a["maximum_donor_distance_m"]) if results else None


def repair(full:dict,parent_xy:np.ndarray,parent_lonlat:np.ndarray,
           mask_parent:np.ndarray,child_xy:np.ndarray,child_lonlat:np.ndarray,
           child_mask:np.ndarray,coast:list,*,parent_cell_m:float)->dict:
    """Patch only 4-wet quad rows flagged by strict shoreline intersection."""
    rows=[dict(r) for r in full["records"]]
    total=len(rows)
    bad_keys={(int(a["eta_rho_zero_based"]),int(a["xi_rho_zero_based"]))
              for a in full["ordinary_quad_coastline_conflicts"]}
    if not bad_keys or len(bad_keys)!=full["counts"]["ordinary_quad_crosses_GSHHG_level1"]:
        raise ValueError("expected nonempty ordinary coastline-conflict source list")
    resolved=[]
    n_triangle=n_multi=n_single=0
    for r in rows:
        key=(int(r["child_eta_rho_zero_based"]),int(r["child_xi_rho_zero_based"]))
        if key not in bad_keys:
            continue
        j,i=key
        if (r["method"]!="BILINEAR_FOUR_WET_PARENT_RHO_PROJECTED_AEQD"
                or not r["GSHHG_level1_coastline_intersection"] or not child_mask[j,i]):
            raise ValueError("unexpected corrupted original conflict status")
        target=child_xy[j,i]
        alt=choose_coastline_safe_triangle(parent_xy,parent_lonlat,mask_parent,
                                           r["donor_eta_xi_zero_based"],target,coast)
        if alt is None:
            alternate=classify_visible_wet_donors(
                parent_xy,parent_lonlat,mask_parent,target,child_lonlat[j,i],
                coast,median_cell_m=parent_cell_m,max_cell_radius=2.5,
                max_donors=4,max_graph_hops=8)
            if not alternate.get("selected_donors"):
                resolved.append({"child_eta_rho_zero_based":j,
                                 "child_xi_rho_zero_based":i,
                                 "status":"UNRESOLVED_COASTLINE_CONFLICT",
                                 "candidate_diagnostics":alternate})
                continue
            src=alternate["selected_donors"]
            alt={
                "method":"COAST_VISIBLE_BOUNDARY_QUAD_FALLBACK_"+
                          ("MULTI_DONOR_IDW" if len(src)>1 else "SINGLE_DONOR"),
                "donor_eta_xi_zero_based":[[int(a["eta_rho_zero_based"]),int(a["xi_rho_zero_based"])] for a in src],
                "weights":[float(a["weight"]) for a in src],
                "maximum_donor_distance_m":float(alternate["max_selected_distance_m"]),
                "enclosing_geometry":False,
                "coastline_visible":True,
                "GSHHG_level1_coastline_intersection":False,
                "source_kind":"TARGETED_GSHHG_PARENT_QUAD_COASTLINE_REPAIR",
                "extrapolation_review_required":True,
            }
            if len(src)>1:
                n_multi+=1
            else:
                n_single+=1
        else:
            n_triangle+=1
        r.update(alt)
        r["coastline_repair_applied"]=True
        resolved.append({"child_eta_rho_zero_based":j,
                         "child_xi_rho_zero_based":i,
                         "status":r["method"],
                         "selected_parent_eta_xi":r["donor_eta_xi_zero_based"],
                         "weights":r["weights"],
                         "maximum_donor_distance_m":r["maximum_donor_distance_m"]})
    unresolved=[a for a in resolved if a["status"]=="UNRESOLVED_COASTLINE_CONFLICT"]
    if len(resolved)!=len(bad_keys):
        raise ValueError("some coastal source conflicts not visited")
    for row in rows:
        if row.get("GSHHG_level1_coastline_intersection"):
            raise ValueError("coastline conflict remains in final ordinary donor")
        if not row.get("coastline_visible"):
            raise ValueError("some mapped donor is not coast-visible")
        nodes=np.asarray(row["donor_eta_xi_zero_based"],dtype=int)
        w=np.asarray(row["weights"],dtype=float)
        if not np.isfinite(w).all() or (w<0).any() or abs(w.sum()-1)>1e-10:
            raise ValueError("corrupt positive-unit-sum donor weights")
        if not mask_parent[nodes[:,0],nodes[:,1]].all():
            raise ValueError("coastal repair donor contains parent land")
    return {
        "scope":"FULL_1017_CURRENT_UD1K_WET_RHO_PARENT_COASTLINE_REVIEW",
        "input_ordinary_four_wet_GSHHG_conflicts":len(bad_keys),
        "resolved_using_same_quad_safe_three_wet_triangle":n_triangle,
        "resolved_using_connected_multi_wet_extrapolation":n_multi,
        "resolved_using_single_wet_extrapolation":n_single,
        "unresolved_coastline_conflicts":len(unresolved),
        "results_for_original_coastline_conflicts":resolved,
        "all_1017_mapped_RHO_records":rows,
        "original_27_fallback_records_preserved":True,
        "source_masks_modified":False,
        "physical_staggered_UV_vertical_bry_flux":"NOT_RUN",
        "adoption":"DIAGNOSTIC_ONLY_NOT_PRODUCTION_OPEN_BOUNDARY",
    }


def run(parent:Path,child:Path,full_map:Path,gshhg_base:Path)->dict:
    with Dataset(parent) as f:
        pwet=np.asarray(f["mask_rho"][:],dtype=bool)
        plon=np.asarray(f["lon_rho"][:],dtype=float)
        plat=np.asarray(f["lat_rho"][:],dtype=float)
        ph=np.asarray(f["h"][:],dtype=float)
        pm=np.asarray(f["pm"][:],dtype=float)
        pn=np.asarray(f["pn"][:],dtype=float)
    with Dataset(child) as f:
        clon=np.asarray(f["lon_rho"][:],dtype=float)
        clat=np.asarray(f["lat_rho"][:],dtype=float)
        cwet=np.asarray(f["mask_rho"][:],dtype=bool)
    baseline=json.loads(full_map.read_text())
    if baseline["counts"]["total_wet_perimeter"]!=1017 or baseline["counts"]["audited_27_fallback"]!=27:
        raise ValueError("wrong frozen current UD1K source map")
    bbox=BoundingBox(float(clon.min()-.3),float(clon.max()+.3),
                     float(clat.min()-.3),float(clat.max()+.3))
    coasts,_=_shoreline_parts(gshhg_base,bbox,resolution="h")
    if not coasts:
        raise ValueError("GSHHG coastline missing")
    crs=CRS.from_proj4(f"+proj=aeqd +lat_0={plat.mean()} +lon_0={plon.mean()} +datum=WGS84 +units=m +no_defs")
    tf=Transformer.from_crs("EPSG:4326",crs,always_xy=True)
    px,py=tf.transform(plon,plat)
    cx,cy=tf.transform(clon,clat)
    record=repair(baseline,np.stack((px,py),axis=-1),
                  np.stack((plon,plat),axis=-1),pwet,
                  np.stack((cx,cy),axis=-1),
                  np.stack((clon,clat),axis=-1),cwet,
                  coasts,parent_cell_m=float(np.median(1/np.sqrt(pm*pn))))
    if record["unresolved_coastline_conflicts"]:
        raise ValueError("coastline repair did not produce all safe donors")
    rows=record["all_1017_mapped_RHO_records"]
    depth=apply_scalar_stencils(ph,rows)
    constant=apply_scalar_stencils(np.ones_like(ph),rows)
    if not np.isfinite(depth).all() or not np.allclose(constant,1,rtol=0,atol=1e-12):
        raise ValueError("coast-repaired RHO depth numerical smoke failed")
    record["numeric_smoke"]={
        "all_1017_real_parent_depth_samples_finite":True,
        "constant_field_max_abs_error":float(abs(constant-1).max()),
        "min_parent_depth_sample_m":float(depth.min()),
        "max_parent_depth_sample_m":float(depth.max()),
        "parent_solution_available":"FALSE_ONLY_PARENT_BATHYMETRY_NOT_HYDRODYNAMIC_TIME_SERIES",
    }
    return record


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("parent-grid","child-grid","full-map-json","gshhg-base","output-json"):
        ap.add_argument("--"+name,type=Path,required=True)
    args=ap.parse_args()
    rec=run(args.parent_grid,args.child_grid,args.full_map_json,args.gshhg_base)
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(rec,indent=2)+"\n")
    print("UD1K_REAL_FOUR_WET_QUAD_COASTLINE_REPAIRS",json.dumps({
        "quad_conflicts":rec["input_ordinary_four_wet_GSHHG_conflicts"],
        "local_triangle":rec["resolved_using_same_quad_safe_three_wet_triangle"],
        "multi_donor_coast_visible":rec["resolved_using_connected_multi_wet_extrapolation"],
        "single_donor_coast_visible":rec["resolved_using_single_wet_extrapolation"],
        "unresolved":rec["unresolved_coastline_conflicts"],
    },sort_keys=True))
    print("UD1K_REAL_FULL_RHO_COAST_REPAIR_NUMERIC",json.dumps(rec["numeric_smoke"],sort_keys=True))
    print("STATIC_RHO_COAST_SAFE_CANDIDATES_ONLY; STAGGERED_VECTORS_AND_ROMs_BRY_NOT_RUN")


if __name__=="__main__":
    main()
