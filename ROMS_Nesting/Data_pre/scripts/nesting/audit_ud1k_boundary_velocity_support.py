#!/usr/bin/env python3
"""Real native 15s source C-grid U/V face support for current UD1K boundary.

Analyses 1017 *RHO* scalar mapping donors from prior audited map; uses
actual ES3K RHO mask to determine if native U and V face fields can be
collocated at each donor. Pure diagnostics; actual velocities not available.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"nesting"))
from ud1k_boundary_cgrid_velocity import face_support_report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("parent-grid","full-rho-map","output-json"):
        p.add_argument("--"+name,required=True,type=Path)
    args=p.parse_args()
    manifest=json.loads(args.full_rho_map.read_text())
    if manifest["counts"]["total_wet_perimeter"]!=1017:
        raise ValueError("not the approved UD1K wet RHO perimeter map")
    with Dataset(args.parent_grid) as f:
        wet=np.asarray(f["mask_rho"][:],dtype=bool)
        if "angle" not in f.variables:
            raise ValueError("parent angle is missing")
        angle=np.asarray(f["angle"][:],dtype=float)
        if angle.shape!=wet.shape or not np.isfinite(angle).all():
            raise ValueError("invalid parent local rotation angle")
    result=face_support_report(wet,manifest["records"])
    result["source_parent_grid"]=args.parent_grid.name
    result["receiver_count"]=len(manifest["records"])
    result["parent_local_rotation_angle_available"]=True
    result["physical_vector_flux_acceptance"]="NOT_RUN"
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(result,indent=2)+"\n")
    print("UD1K_PARENT_CGRID_WET_FACE_SUPPORT",json.dumps({
        "mapped_rho_receivers":result["receiver_count"],
        "required_source_donors":result["donor_samples_checked"],
        "U_or_V_missing_receivers":result["receiver_RHO_points_with_missing_U_or_V_donor"],
        "only_one_native_U_face":result["u_one_wet_face_samples"],
        "only_one_native_V_face":result["v_one_wet_face_samples"],
    },sort_keys=True))
    print("VECTOR_SOURCE_FACE_SUPPORT_ONLY; STAGGERED_CHILD_UV_AND_ROMs_BRY_NOT_RUN")


if __name__=="__main__":
    main()
