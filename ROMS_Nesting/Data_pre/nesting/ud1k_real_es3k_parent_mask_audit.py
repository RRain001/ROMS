"""Independent archived ES3K REAL wet-mask check for actual UD1K Option B donors.

This is a one-time READ-ONLY geometry audit: source parent is the original
GEBCO2026/GSHHG237 ES3K I3 NetCDF, NOT an all-wet synthetic substitute.
The companion child grid and RHO/native-U/native-V manifests are actual
coastline-checked Option B *comparison* candidate artifacts.

A PASS certifies source wet RHO and native parent U and V face support for
the frozen source stencils *against the supplied real parent mask*. It
DOES NOT rerun shoreline line-of-sight intersections or hydrodynamics,
nor certify parent->child physical mass/volume transport or activate Option B.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

try:
    from ud1k_real_optionb_manifest_contract import (
        EXPECTED_COUNTS,EXPECTED_NORMAL,PARENT_RHO_SHAPE,validate_real_candidate_b)
except ImportError:
    from .ud1k_real_optionb_manifest_contract import (
        EXPECTED_COUNTS,EXPECTED_NORMAL,PARENT_RHO_SHAPE,validate_real_candidate_b)

SOURCES={
    "rho":("donor_eta_xi_zero_based","records"),
    "u":("donor_parent_rho_eta_xi_zero_based","reports"),
    "v":("donor_parent_rho_eta_xi_zero_based","reports"),
}


def _mask(source:Dataset,name:str,shape:tuple[int,int])->np.ndarray:
    if name not in source.variables:
        raise ValueError("actual ES3K parent grid missing "+name)
    a=np.asarray(np.ma.filled(np.ma.asarray(source[name][:]),-999),dtype=float)
    if a.shape!=shape or not np.isfinite(a).all() or not np.isin(a,(0,1)).all():
        raise ValueError(f"actual ES3K {name} has invalid shape or nonbinary wet flags")
    return a.astype(bool)


def _pair_faces(wet:np.ndarray,j:int,i:int)->tuple[list[tuple[int,int]],list[tuple[int,int]]]:
    ny,nx=wet.shape
    u=[(j,k) for k in (i-1,i) if 0<=k<nx-1 and wet[j,k] and wet[j,k+1]]
    v=[(k,i) for k in (j-1,j) if 0<=k<ny-1 and wet[k,i] and wet[k+1,i]]
    return u,v


def check_real_parent_donors(
    parent_grid:Path,child_grid:Path,rho_json:Path,uv_json:Path,
    *,expected_parent_shape:tuple[int,int]=PARENT_RHO_SHAPE)->dict:
    parent_grid=Path(parent_grid);child_grid=Path(child_grid)
    static=validate_real_candidate_b(child_grid,rho_json,uv_json,
                                     parent_shape=expected_parent_shape)
    r=json.loads(Path(rho_json).read_text(encoding="utf-8"))
    v=json.loads(Path(uv_json).read_text(encoding="utf-8"))
    records={"rho":r["records"],
             "u":v["reports"]["u"]["records"],
             "v":v["reports"]["v"]["records"]}
    kinds={}
    unique=set()
    with Dataset(parent_grid) as ds:
        wet=_mask(ds,"mask_rho",expected_parent_shape)
        wu=_mask(ds,"mask_u",(wet.shape[0],wet.shape[1]-1))
        wv=_mask(ds,"mask_v",(wet.shape[0]-1,wet.shape[1]))
        if not np.array_equal(wu,wet[:,:-1]&wet[:,1:]):
            raise ValueError("real ES3K native U mask inconsistent with wet RHO neighbors")
        if not np.array_equal(wv,wet[:-1,:]&wet[1:,:]):
            raise ValueError("real ES3K native V mask inconsistent with wet RHO neighbors")
        for key in ("h","angle","lon_rho","lat_rho"):
            if key not in ds.variables:
                raise ValueError("real ES3K parent missing physical "+key)
            a=np.asarray(np.ma.filled(np.ma.asarray(ds[key][:],dtype=float),np.nan))
            if a.shape!=wet.shape or not np.isfinite(a[wet]).all():
                raise ValueError("real ES3K parent wet "+key+" invalid")
            if key=="h" and np.any(a[wet]<=0):
                raise ValueError("real ES3K parent wet h not positive")
        h=np.asarray(ds["h"][:],dtype=float)
        for kind,rows in records.items():
            source_key=SOURCES[kind][0]
            counts={"source_donor_references":0,"zero_weight_references":0,
                    "unique_parent_RHO_nodes":0}
            used=set()
            for row in rows:
                donors=row[source_key]
                weights=row["weights"]
                for pair,weight in zip(donors,weights,strict=True):
                    j,i=pair
                    counts["source_donor_references"]+=1
                    if weight==0:
                        counts["zero_weight_references"]+=1
                    if not wet[j,i]:
                        raise ValueError(
                            f"real ES3K parent DRY RHO donor for {kind} target at {(j,i)}")
                    used.add((j,i));unique.add((j,i))
                    if kind in ("u","v"):
                        uf,vf=_pair_faces(wet,j,i)
                        if not uf or not vf:
                            raise ValueError(f"actual ES3K parent donor {kind} lacks wet U AND V faces at {(j,i)}")
                        if not all(wu[jj,ii] for jj,ii in uf):
                            raise ValueError("ES3K mask_u differs from RHO wet-derived donor face")
                        if not all(wv[jj,ii] for jj,ii in vf):
                            raise ValueError("ES3K mask_v differs from RHO wet-derived donor face")
            if len(rows)!=EXPECTED_COUNTS[kind]:
                raise ValueError("source record count differs from original Option B manifest")
            counts["unique_parent_RHO_nodes"]=len(used)
            kinds[kind]=counts
        ordered=sorted(unique)
        all_j=np.array([j for j,i in ordered],dtype=int)
        all_i=np.array([i for j,i in ordered],dtype=int)
        if not len(unique) or not np.isfinite(h[all_j,all_i]).all():
            raise ValueError("invalid ES3K real parent donor list or bathymetry")
        digest=hashlib.sha256(np.stack([all_j,all_i],axis=-1).astype("<i4")
                .tobytes()).hexdigest()
        return {
            "status":"REAL_ES3K_PARENT_MASK_ALL_OPTIONB_RHO_U_V_DONORS_PASS",
            "source_grid_name":parent_grid.name,
            "source_grid_mask":"ACTUAL_GEBCO2026_GSHHG237_ES3K_I3_NOT_ARTIFICIAL",
            "target_grid_status":static["option_b_status"],
            "parent_rho_shape":list(wet.shape),
            "actual_parent_wet_rho_cells":int(np.count_nonzero(wet)),
            "actual_parent_wet_u_faces":int(np.count_nonzero(wu)),
            "actual_parent_wet_v_faces":int(np.count_nonzero(wv)),
            "source_real_cgrid_wet_face_mask_consistency":"PASS",
            "actual_RHO_and_native_UV_donor_checks":"PASS",
            "receivers_by_kind":{k:len(rows) for k,rows in records.items()},
            "source_donor_statistics":kinds,
            "unique_real_parent_RHO_donor_nodes":len(unique),
            "sorted_unique_parent_donor_sha256":digest,
            "real_parent_donor_h_min_max_m":[float(np.min(h[all_j,all_i])),
                                             float(np.max(h[all_j,all_i]))],
            "native_child_normal_face_counts":static["wet_native_open_normal_section_counts"],
            "recomputed_GSHHG_shoreline_line_of_sight":"NOT_RUN_PREVIOUS_MANIFEST_AUDIT_ONLY",
            "real_parent_ES3K_time_dependent_history":"NOT_AVAILABLE",
            "real_ES3K_UD1K_parent_child_transport_mass_conservation":"NOT_RUN",
            "real_ROMs_ocean_integration":"NOT_RUN",
        }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("parent-grid","child-grid","rho-map","native-uv-map","report-json"):
        p.add_argument("--"+arg,required=True,type=Path)
    args=p.parse_args()
    result=check_real_parent_donors(
        args.parent_grid,args.child_grid,args.rho_map,args.native_uv_map)
    args.report_json.parent.mkdir(parents=True,exist_ok=True)
    args.report_json.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print("REAL_ES3K_PARENT_MASK_OPTION_B_NATIVE_SOURCE_DONORS",json.dumps({
        "result":result["status"],
        "real_parent_unique_donors":result["unique_real_parent_RHO_donor_nodes"],
        "child_receiver_counts":result["receivers_by_kind"],
        "actual_parent_history":"NOT_AVAILABLE",
    },sort_keys=True))


if __name__=="__main__":
    main()
