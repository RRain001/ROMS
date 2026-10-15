"""Build a complete 27-point *read-only* scalar RHO fallback stencil manifest.

Composes prior real GEBCO/GSHHG evidence into one stable interface. These
are 7 enclosing triangles plus 16 multi-donor and 4 single-donor
coast-visible wet-only, radius-bounded EXTRAPOLATION stencils.

Not yet ROMS bry production: U/V stagger, z-levels, boundary transports,
time dependency, and external barotropic/baroclinic response NOT_RUN.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

T1="COASTLINE_CLEAR_LOCAL_TRIANGLE_STATIC_CANDIDATE"
T2="CONNECTED_3X3_COASTLINE_CLEAR_STATIC_CANDIDATE"
M="MULTI_DONOR_COAST_VISIBLE_IDW_EXTRAPOLATION_CANDIDATE"
S="SINGLE_DONOR_COAST_VISIBLE_EXTRAPOLATION_CANDIDATE"


def _key(record:dict)->tuple[int,int]:
    return int(record["child_eta_rho_zero_based"]),int(record["child_xi_rho_zero_based"])


def _triangle(record:dict, candidate:dict,method:str)->dict:
    return {
        "method":method,"child_eta_rho_zero_based":_key(record)[0],
        "child_xi_rho_zero_based":_key(record)[1],
        "child_lon":float(record["child_lon"]),"child_lat":float(record["child_lat"]),
        "donor_eta_xi_zero_based":[list(map(int,ij)) for ij in candidate["donor_eta_xi_zero_based"]],
        "weights":list(map(float,candidate["weights"])),
        "maximum_donor_distance_m":float(candidate["max_donor_distance_m"]),
        "coastline_visible":True,
        "enclosing_geometry":True,
        "source":"REAL_ES3K_WET_RHO",
    }


def _extrap(record:dict)->dict:
    src=record["selected_donors"]
    if not src:raise ValueError("coast-visible donor list must not be empty")
    return {
        "method":record["status"],
        "child_eta_rho_zero_based":_key(record)[0],
        "child_xi_rho_zero_based":_key(record)[1],
        "child_lon":float(record["child_lon"]),"child_lat":float(record["child_lat"]),
        "donor_eta_xi_zero_based":[[int(s["eta_rho_zero_based"]),int(s["xi_rho_zero_based"])] for s in src],
        "weights":[float(s["weight"]) for s in src],
        "maximum_donor_distance_m":float(record["max_selected_distance_m"]),
        "coastline_visible":True,
        "enclosing_geometry":False,
        "source":"REAL_ES3K_WET_RHO",
        "note":"Non-enclosing coastal extrapolation. Requires physical validation.",
    }


def compose(first:dict,second:dict,third:dict,mask_parent:np.ndarray,
            mask_child:np.ndarray,baseline:dict)->dict:
    """Fail closed if any of 27 unresolved points is absent, dry or duplicated."""
    all_keys={
        (int(z["eta_rho_zero_based"]),int(z["xi_rho_zero_based"])):(float(z["lon"]),float(z["lat"]))
        for z in baseline["full_wet_parent_quad_stencil"]["uncovered_sample_ij_lonlat"]
    }
    if len(all_keys)!=27 or len(first["records"])!=27 or len(second["records"])!=22 or len(third["records"])!=20:
        raise ValueError("baseline must be exactly 27 coastal problems")
    rows={}
    def add(item):
        key=_key(item)
        if key in rows or key not in all_keys:
            raise ValueError("duplicate or unrecognized RHO boundary point")
        lon,lat=all_keys[key]
        if abs(item["child_lon"]-lon)>1e-9 or abs(item["child_lat"]-lat)>1e-9:
            raise ValueError("receiver lon/lat differs from original real baseline")
        rows[key]=item
    for r in first["records"]:
        if r["status"]==T1:
            add(_triangle(r,r["best_candidate"],"BARYCENTRIC_SAME_2x2_THREE_WET"))
    for r in second["records"]:
        if r["status"]==T2:
            add(_triangle(r,r["selected_candidate"],"BARYCENTRIC_CONNECTED_3x3_THREE_WET"))
    for r in third["records"]:
        if r["status"] in (M,S):
            add(_extrap(r))
        else:
            raise ValueError("unresolved fallback point: "+r["status"])
    if len(rows)!=27 or set(rows)!=set(all_keys):
        raise ValueError("missing RHO boundary wet points")

    counts=Counter()
    for key,r in rows.items():
        j,i=key
        if j<0 or j>=mask_child.shape[0] or i<0 or i>=mask_child.shape[1]:
            raise ValueError("child point outside actual grid")
        if not (mask_child[j,i] and (j in (0,mask_child.shape[0]-1) or i in (0,mask_child.shape[1]-1))):
            raise ValueError("child donor receiver must be wet on perimeter")
        nodes=np.asarray(r["donor_eta_xi_zero_based"],dtype=int)
        weights=np.asarray(r["weights"],dtype=float)
        if nodes.ndim!=2 or nodes.shape[1]!=2 or len(weights)!=len(nodes) or len(nodes)<1 or len(nodes)>4:
            raise ValueError("malformed boundary donor stencil")
        if (nodes[:,0]<0).any() or (nodes[:,0]>=mask_parent.shape[0]).any() or (nodes[:,1]<0).any() or (nodes[:,1]>=mask_parent.shape[1]).any():
            raise ValueError("parent donor outside grid")
        if not mask_parent[nodes[:,0],nodes[:,1]].all():
            raise ValueError("dry parent RHO donor in interpolator")
        if not np.isfinite(weights).all() or (weights<0).any() or abs(weights.sum()-1)>1e-10:
            raise ValueError("invalid finite convex interpolator")
        if not r["coastline_visible"]:
            raise ValueError("coastline-crossing donor")
        counts[r["method"]]+=1
    if counts != Counter({"BARYCENTRIC_SAME_2x2_THREE_WET":5,
                          "BARYCENTRIC_CONNECTED_3x3_THREE_WET":2,
                          M:16,S:4}):
        raise ValueError("real source category counts drift")
    records=[rows[k] for k in sorted(rows)]
    return {
        "scope":"27_CURRENT_UD1K_WET_RHO_PERIMETER_FALLBACK_CANDIDATES_ONLY",
        "source":"GEBCO_2026_NATIVE15S_GSHHG_2_3_7_HIGH_L1",
        "target_grid_shape_eta_xi":list(mask_child.shape),
        "parent_grid_shape_eta_xi":list(mask_parent.shape),
        "mapping_kind":"STATIC_BOUNDARY_SCALAR_RHO_STENCIL_NOT_BRY_PRODUCTION",
        "counts_by_method":dict(counts),
        "total_previously_missing_full_wet_quads":27,
        "now_with_coast_visible_wet_donors":len(records),
        "all_parent_nodes_wet":True,
        "all_child_receivers_wet":True,
        "all_weights_nonnegative_sum1":True,
        "source_masks_mutated":False,
        "physical_validation":"NOT_RUN",
        "notes":["7 methods are enclosing triangle *interpolations*; remaining 20 are *extrapolations*.",
                 "These 27 must not be equated to boundary PHYSICS acceptance.",
                 "Cannot apply this RHO map directly to staggered U/V or infer normal flux.",
                 "No parent/child masks, open-boundary types or domain extent were changed."],
        "records":records,
    }


def apply_scalar_stencils(parent_rho:np.ndarray,records:list[dict])->np.ndarray:
    """Unit-safe linear RHO sample for any leading time/vertical dimensions."""
    arr=np.asarray(parent_rho,dtype=float)
    if arr.ndim<2:
        raise ValueError("parent field must contain eta_rho,xi_rho axes")
    outputs=[]
    for r in records:
        coords=np.asarray(r["donor_eta_xi_zero_based"],dtype=int)
        weights=np.asarray(r["weights"],dtype=float)
        values=arr[...,coords[:,0],coords[:,1]]
        if not np.isfinite(values).all():
            raise ValueError("parent wet donor field not finite")
        outputs.append(np.sum(values*weights,axis=-1))
    return np.stack(outputs,axis=-1)


def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("parent-grid","child-grid","preflight-json","strict-json",
                 "connected-json","visible-json","output-json"):
        p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args()
    reports=[json.loads(f.read_text()) for f in (
        a.strict_json,a.connected_json,a.visible_json,a.preflight_json)]
    with Dataset(a.parent_grid) as f:
        mask_parent=np.asarray(f["mask_rho"][:],dtype=bool)
        h=np.asarray(f["h"][:],dtype=float)
        lon=np.asarray(f["lon_rho"][:],dtype=float)
        lat=np.asarray(f["lat_rho"][:],dtype=float)
    with Dataset(a.child_grid) as f:
        mask_child=np.asarray(f["mask_rho"][:],dtype=bool)
    result=compose(*reports[:3],mask_parent,mask_child,reports[3])
    # Live field + synthetic multidimensional diagnostics. Preserve donor
    # convex hull, finite values, constant fields, and point ordering.
    sampled=apply_scalar_stencils(h,result["records"])
    if not (np.isfinite(sampled).all() and np.all(sampled>=0)):
        raise ValueError("invalid actual parent bathymetry field sampling")
    constant=apply_scalar_stencils(np.ones_like(h),result["records"])
    if not np.allclose(constant,1,rtol=0,atol=2e-12):
        raise ValueError("constant field not preserved exactly")
    stack=apply_scalar_stencils(np.stack([h,2*h],axis=0),result["records"])
    if not np.allclose(stack[0],sampled,atol=1e-9) or not np.allclose(stack[1],2*sampled,atol=1e-9):
        raise ValueError("time-layer vectorization not consistent")
    result["numeric_probe"]={
        "all_27_parent_h_samples_finite":True,
        "all_27_parent_h_samples_nonnegative":True,
        "constant_field_max_abs_error":float(abs(constant-1).max()),
        "multi_leading_dim_broadcast":"PASS",
        "max_selected_donor_radius_m":float(max(r["maximum_donor_distance_m"] for r in result["records"])),
        "sampled_parent_depth_min_m":float(sampled.min()),
        "sampled_parent_depth_max_m":float(sampled.max()),
        "physical_flux_conservation":"NOT_RUN",
    }
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(result,indent=2)+"\n")
    print("UD1K_RHO_27_ALL_WET_VISIBLE_DONORS",json.dumps(result["counts_by_method"],sort_keys=True))
    print("UD1K_27_REAL_RHO_SCALAR_NUMERIC_PROBE",json.dumps(result["numeric_probe"],sort_keys=True))
    print("ONLY_STATIC_BOUNDARY_RHO_STENCIL_NOT_APPROVED_BRY_PHYSICS")


if __name__=="__main__":
    main()
