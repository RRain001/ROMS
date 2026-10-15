"""Retain validated RHO donor maps only for core UD1K wet-perimeter points.

Never rerun coastline interpolation with relaxed rules: the 1017 original
RHO donor records already passed shoreline checks. Drop records whose child
RHO receiver was *physically disconnected* and is dry on the new opt-in core
candidate, preserve all other parent donor indices and scalar weights.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


def subset(repaired_map:dict,original_wet:np.ndarray,core_wet:np.ndarray)->dict:
    old=np.asarray(original_wet,dtype=bool)
    core=np.asarray(core_wet,dtype=bool)
    if old.shape!=core.shape or old.shape!=(290,438) or (core&~old).any():
        raise ValueError("candidate must be wet-only subset of original current UD1K")
    rim=np.zeros_like(core,dtype=bool)
    rim[0,:]=rim[-1,:]=True
    rim[:,0]=rim[:,-1]=True
    actual_old={(int(j),int(i)) for j,i in np.argwhere(old&rim)}
    actual_new={(int(j),int(i)) for j,i in np.argwhere(core&rim)}
    rows=repaired_map["all_1017_mapped_RHO_records"]
    if len(rows)!=1017 or len(actual_old)!=1017:
        raise ValueError("not original 1017 audited wet RHO receivers")
    map_old={(int(r["child_eta_rho_zero_based"]),int(r["child_xi_rho_zero_based"])):r for r in rows}
    if len(map_old)!=len(rows) or set(map_old)!=actual_old:
        raise ValueError("missing or duplicate original RHO mapping")
    kept=[map_old[k] for k in sorted(actual_new)]
    discarded=[list(k) for k in sorted(actual_old-actual_new)]
    if len(kept)!=1014 or discarded!=[[0,27],[0,28],[0,30]]:
        raise ValueError(f"unexpected core candidate RHO perimeter change: removed={discarded}")
    if any((not r.get("coastline_visible",False)) or not r.get("weights") or
           abs(sum(r["weights"])-1)>1e-10 for r in kept):
        raise ValueError("unsafe original scalar RHO source in core mapping")
    return {
        "scope":"CURRENT_UD1K_CORE_CONNECTED_OCEAN_1014_WET_RHO_PERIMETER_ONLY",
        "original_source_RHO_perimeter_count":1017,
        "core_candidate_wet_RHO_perimeter_count":len(kept),
        "removed_disconnected_boundary_RHO_receivers":discarded,
        "original_all_wet_coastline_safe_source_weights_preserved":True,
        "coastline_and_parent_wet_source_checks_not_relaxed":True,
        "source_candidate_original_grid_modified":False,
        "physical_bry_nc_and_mass_flux":"NOT_RUN",
        "records":kept,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("original-grid","core-grid","full-repaired-rho-map","output-json"):
        p.add_argument("--"+key,type=Path,required=True)
    args=p.parse_args()
    with Dataset(args.original_grid) as f:
        old=np.asarray(f["mask_rho"][:],dtype=bool)
    with Dataset(args.core_grid) as f:
        new=np.asarray(f["mask_rho"][:],dtype=bool)
    report=subset(json.loads(args.full_repaired_rho_map.read_text()),old,new)
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(report,indent=2)+"\n")
    print("UD1K_CORE_CONNECTED_OCEAN_VALIDATED_RHO_PERIMETER",json.dumps({
        "original":report["original_source_RHO_perimeter_count"],
        "core":report["core_candidate_wet_RHO_perimeter_count"],
        "removed":report["removed_disconnected_boundary_RHO_receivers"],
    },sort_keys=True))
    print("NO_NEW_INTERPOLATION_OR_GRID_PRODUCTION")


if __name__=="__main__":
    main()
