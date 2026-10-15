"""Optional UD1K connected-core + shoreline-consistent native face C-grid candidate.

Creates a SECOND separate grid file from the first (core-only) candidate.
There are four known real GSHHG L1 wet-face segment intersections. Find
a minimal covering subset of *existing wet perimeter RHO vertices* whose
drying disables all coastline-crossing U/V face connections, while
requiring the entire dominant wet ocean to remain four-neighbor connected.

No arbitrary inland/lagoon cleaning or domain extent change is performed.
This is not an automatic production mask approval; hydrodynamic tests
and independent shoreline/bathymetry review are still mandatory.
"""
from __future__ import annotations
import argparse
from itertools import combinations
import json
from pathlib import Path
import shutil

import numpy as np
from netCDF4 import Dataset
from scipy.ndimage import label

from ud1k_connected_core_candidate import FOUR_NEIGHBOR,connected_core_masks


def minimal_boundary_wet_vertex_cover(wet:np.ndarray,topology:dict)->tuple[list[list[int]],dict]:
    """Minimum perimeter-RHO cut of real coastline-crossing native faces.

    Affected U face (eta_u,xi_u) connects RHO(j,i) and RHO(j,i+1),
    V face (eta_v,xi_v) connects RHO(j,i) and RHO(j+1,i).
    Reject candidates that split the main connected ocean or remove any
    interior RHO cell. Ties: prefer smaller lost native U/V face counts,
    then deterministic sorted RHO indices.
    """
    m=np.asarray(wet,dtype=bool)
    if m.shape!=(290,438):
        raise ValueError("unexpected frozen current user UD1K shape")
    if np.max(np.bincount(label(m,structure=FOUR_NEIGHBOR)[0].ravel())[1:])!=m.sum():
        raise ValueError("must start with only dominant connected wet component")
    ny,nx=m.shape
    flagged=[]
    for kind in ("u","v"):
        for r in topology["reports"][kind]["flagged_faces"]:
            j=int(r["child_eta_face_zero_based"])
            i=int(r["child_xi_face_zero_based"])
            a=(j,i)
            b=(j,i+1) if kind=="u" else (j+1,i)
            if not all(0<=jj<ny and 0<=ii<nx and m[jj,ii] for jj,ii in (a,b)):
                raise ValueError("invalid topology: wet crossing with a dry RHO endpoint")
            flagged.append((kind,a,b))
    if len(flagged)!=4:
        raise ValueError("expected the four actual GSHHG-crossing wet faces only")
    periphery=lambda j,i:j in (0,ny-1) or i in (0,nx-1)
    vertices=sorted({v for _,a,b in flagged for v in (a,b) if periphery(*v)})
    if not vertices:
        raise ValueError("no wet boundary endpoints available for safe localized cut")
    best=None
    for nchoose in range(1,len(vertices)+1):
        for choice in combinations(vertices,nchoose):
            selected=set(choice)
            if not all(a in selected or b in selected for _,a,b in flagged):
                continue
            trial=m.copy()
            for j,i in selected:
                trial[j,i]=False
            components,n=label(trial,structure=FOUR_NEIGHBOR)
            if n!=1 or not trial.any():
                continue
            removed_u=int(np.sum(m[:,:-1]&m[:,1:])-np.sum(trial[:,:-1]&trial[:,1:]))
            removed_v=int(np.sum(m[:-1,:]&m[1:,:])-np.sum(trial[:-1,:]&trial[1:,:]))
            score=(nchoose,removed_u+removed_v,tuple(sorted(choice)))
            if best is None or score<best[0]:
                best=(score,trial)
        if best is not None:
            break
    if best is None:
        raise ValueError("cannot repair coastline-crossing faces without disconnecting ocean")
    picked=[list(p) for p in best[0][2]]
    repaired=[
        {"face_kind":kind,
         "child_face_eta_xi_zero_based":list(a),
         "adjacent_RHO_eta_xi_zero_based":[list(a),list(b)],
         "removed_boundary_RHO_vertex":[list(x) for x in (a,b) if x in {tuple(y) for y in picked}]}
        for kind,a,b in flagged]
    return picked,{"repaired_coastline_crossing_faces":repaired,
                   "minimal_removed_boundary_RHO_count":len(picked),
                   "lost_native_U_wet_faces":best[0][1]-(
                       (int(np.sum(m[:-1,:]&m[1:,:])-np.sum(best[1][:-1,:]&best[1][1:,:])))),
                   "source_ocean_remains_4_connected":True}


def create(core_grid:Path,topology_json:Path,output_grid:Path,report_json:Path)->dict:
    src=Path(core_grid);dst=Path(output_grid)
    if not src.exists() or src.resolve()==dst.resolve() or dst.exists():
        raise ValueError("original core source missing or destination overwrite forbidden")
    topology=json.loads(topology_json.read_text())
    with Dataset(src) as f:
        src_wet=np.asarray(f["mask_rho"][:],dtype=bool)
        h=np.asarray(f["h"][:])
        lon=np.asarray(f["lon_rho"][:])
        lat=np.asarray(f["lat_rho"][:])
        nbase=src_wet.sum()
    chosen,info=minimal_boundary_wet_vertex_cover(src_wet,topology)
    candidate=src_wet.copy()
    for j,i in chosen:
        candidate[j,i]=False
    masks,connectivity=connected_core_masks(candidate)
    if connectivity["wet_component_count"]!=1 or len(connectivity["removed_RHO_points_eta_xi_zero_based"]):
        raise ValueError("min-cut must not disconnect additional wet ocean")
    if chosen!=[[0,40],[0,42],[23,437]] or nbase!=96107 or candidate.sum()!=96104:
        raise ValueError("unexpected real coastline issue or minimization result")
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dst)
    with Dataset(dst,"a") as f:
        for key,val in masks.items():
            if f[key].shape!=val.shape:
                raise ValueError("native ROMS C-grid mask shape changed")
            f[key][:]=val
        f.setncattr("shoreline_mask_candidate_status",
                    "SEPARATE_GSHHG_L1_PERIMETER_FACE_CUT_NOT_HYDRODYNAMIC_ACCEPTANCE")
        f.setncattr("shoreline_mask_source_grid",src.name)
        f.setncattr("shoreline_mask_method","smallest boundary RHO vertex cover of GSHHG-crossing U/V faces")
    with Dataset(src) as base,Dataset(dst) as out:
        for key in ("h","lon_rho","lat_rho","pm","pn","angle"):
            if not np.array_equal(base[key][:],out[key][:]):
                raise ValueError("non-mask geometry or bathymetry changed")
        if not np.array_equal(base["mask_rho"][:],src_wet.astype("i1")):
            raise ValueError("first candidate changed during second candidate creation")
        for key,val in masks.items():
            if not np.array_equal(out[key][:],val):
                raise ValueError("final mask not saved as expected")
    info.update({
        "scope":"SEPARATE_UD1K_CONNECTED_CORE_PLUS_MIN_BOUNDARY_CROSSING_MASK_CANDIDATE",
        "input_grid":src.name,
        "output_grid":dst.name,
        "wet_source_RHO":int(nbase),
        "wet_candidate_RHO":int(candidate.sum()),
        "minimal_removed_RHO_eta_xi_zero_based":chosen,
        "minimal_removed_RHO_lonlat":[[float(lon[j,i]),float(lat[j,i])] for j,i in chosen],
        "geometry_and_bathymetry_identical_to_source_candidate":True,
        "source_candidate_was_modified":False,
        "all_RHO_wet_components_preserved_as_one":True,
        "mask_modified_only_in_separate_candidate":True,
        "hydrodynamic_transport_bry_nc":"NOT_RUN",
    })
    report_json.parent.mkdir(parents=True,exist_ok=True)
    report_json.write_text(json.dumps(info,indent=2)+"\n")
    print("UD1K_CORE_PLUS_MIN_SHORELINE_BOUNDARY_MASK",json.dumps({
        "removed_3_wet_perimeter_RHO":chosen,
        "source_RHO":int(nbase),"final_RHO":int(candidate.sum()),
        "final_is_one_connected_wet_body":True,
        "physical_bry_nc":"NOT_RUN",
    },sort_keys=True))
    return info


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("core-grid","core-topology-json","output-grid","report-json"):
        p.add_argument("--"+key,type=Path,required=True)
    a=p.parse_args()
    create(a.core_grid,a.core_topology_json,a.output_grid,a.report_json)


if __name__=="__main__":
    main()
