#!/usr/bin/env python3
"""Real native 15s C-grid face support and adjusted RHO vector-only donors.

After the coastline-safe 1017-point RHO map has been assembled, any parent
RHO donor with no wet U or V face is excluded from the *vector only* weights.
No change to original scalar donor weights or parent/child masks.

This is NOT child U/V staggered mapping or a physical velocity bry.nc.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"nesting"))
from ud1k_boundary_cgrid_velocity import (
    face_support_report,vector_face_supported_stencils,
    rotate_parent_to_child_rho)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("parent-grid","child-grid","full-rho-map","output-json"):
        p.add_argument("--"+name,required=True,type=Path)
    args=p.parse_args()
    data=json.loads(args.full_rho_map.read_text())
    records=data.get("all_1017_mapped_RHO_records",data.get("records",[]))
    if len(records)!=1017:
        raise ValueError("not the fixed current UD1K 1017 wet RHO perimeter")
    with Dataset(args.parent_grid) as f:
        wet=np.asarray(f["mask_rho"][:],dtype=bool)
        if "angle" not in f.variables:
            raise ValueError("parent local angle missing")
        angle=np.asarray(f["angle"][:],dtype=float)
        if angle.shape!=wet.shape or not np.isfinite(angle).all():
            raise ValueError("bad parent local angle")
    with Dataset(args.child_grid) as f:
        if "angle" not in f.variables:
            raise ValueError("child local angle missing")
        child_angle=np.asarray(f["angle"][:],dtype=float)
        if not np.isfinite(child_angle).all():
            raise ValueError("bad child local angle")
    before=face_support_report(wet,records)
    vmap=vector_face_supported_stencils(wet,records)
    if vmap["status"]!="RHO_VECTOR_DONOR_FACE_SUPPORT_PREFLIGHT_PASS_ONLY":
        raise ValueError("no valid native wet U/V donor face mapping for some RHO boundary points")
    after=face_support_report(wet,vmap["vector_only_stencils"])
    if after["receiver_RHO_points_with_missing_U_or_V_donor"]:
        raise ValueError("vector map still has missing native wet U/V face")
    u=np.ones((1,wet.shape[0],wet.shape[1]-1),dtype=float)
    v=np.zeros((1,wet.shape[0]-1,wet.shape[1]),dtype=float)
    rotated=rotate_parent_to_child_rho(
        u,v,wet,angle,child_angle,vmap["vector_only_stencils"])
    east=rotated["east_at_child_rho"]
    north=rotated["north_at_child_rho"]
    if (east.shape!=(1,1017) or north.shape!=(1,1017)
            or not np.isfinite(east).all() or not np.isfinite(north).all()
            or np.any(east**2+north**2>1.000000001)):
        raise ValueError("parent native wet C-grid local-angle synthetic smoke failed")
    report={
        "scope":"PARENT_WET_UV_FACE_SUPPORT_ALL_CURRENT_UD1K_1017_RHO_RECEIVERS",
        "parent_grid":args.parent_grid.name,
        "child_grid":args.child_grid.name,
        "parent_source_face_support_before_vector_only_filter":before,
        "parent_source_face_support_after_vector_only_filter":after,
        "vector_only_rho_stencil_manifest":vmap,
        "rotation_smoke":{
            "synthetic_parent_native_U":"CONSTANT_1",
            "synthetic_parent_native_V":"CONSTANT_0",
            "result_dimensions":list(east.shape),
            "max_rotated_east_north_speed":float(np.sqrt(east**2+north**2).max()),
            "all_finite":True,
            "real_parent_velocity_time_series":"NOT_RUN",
        },
        "physical_child_staggered_UV_and_open_boundary_mass_flux":"NOT_RUN",
        "scalar_RHO_mapping_was_modified":False,
        "land_masks_were_modified":False,
    }
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2)+"\n")
    print("UD1K_PARENT_CGRID_VECTOR_ONLY_RHO_FACE_SUPPORT",json.dumps({
        "mapped_rho_receivers":len(records),
        "U_or_V_missing_receivers_before":before["receiver_RHO_points_with_missing_U_or_V_donor"],
        "U_or_V_missing_receivers_after":after["receiver_RHO_points_with_missing_U_or_V_donor"],
        "vector_only_adjusted_receivers":len(vmap["adjusted_receivers"]),
        "native_to_EastNorth_rotation_synthetic_smoke":"PASS",
    },sort_keys=True))
    print("RHO_VECTOR_ONLY_DIAGNOSTIC; REAL_BRY_PHYSICS_NOT_RUN")


if __name__=="__main__":
    main()
