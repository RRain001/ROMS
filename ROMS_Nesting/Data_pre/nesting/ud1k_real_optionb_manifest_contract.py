"""Read-only validation of actual UD1K Option B geometry and donor manifests.

Runs on the SMALL archived GEBCO/GSHHG-derived 2026-10-15 artifact,
without rebuilding terrain or acquiring a genuine parent ES3K history.
Rejects missing/duplicate wet receivers, invalid weights, noncertified
coastline routes, out-of-extent parent RHO indices and broken native
mask geometry. Parent wet/native donor support is supported by the
ORIGINAL upstream audit flags but NOT re-computed from ES3K NetCDF here.

Candidate B is optional COMPARISON ONLY; this module never overwrites
the original, activates a candidate, or certifies physical ocean flux.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

EXPECTED_SHAPES={"rho":(290,438),"u":(290,437),"v":(289,438)}
EXPECTED_COUNTS={"rho":1011,"u":1005,"v":1010}
EXPECTED_NORMAL={"south":382,"north":364,"west":0,"east":266}
PARENT_RHO_SHAPE=(732,464)


def wet_perimeter(mask:np.ndarray)->set[tuple[int,int]]:
    wet=np.asarray(mask,dtype=bool)
    if wet.ndim!=2 or min(wet.shape)<2:
        raise ValueError("invalid wet C-grid mask dimensions")
    rim=np.zeros(wet.shape,dtype=bool)
    rim[[0,-1],:]=True
    rim[:,[0,-1]]=True
    return {tuple(map(int,r)) for r in np.argwhere(wet&rim)}


def _must_binary(raw,name:str)->np.ndarray:
    a=np.asarray(np.ma.filled(np.ma.asarray(raw),-999),dtype=float)
    if not np.isfinite(a).all() or not np.isin(a,(0,1)).all():
        raise ValueError(f"{name}: invalid nonbinary or masked wet mask")
    return np.asarray(a,dtype=bool)


def read_masked_grid(grid_path:Path)->tuple[dict,dict]:
    with Dataset(grid_path) as ds:
        masks={}
        for kind,expected_shape in EXPECTED_SHAPES.items():
            key="mask_"+kind
            if key not in ds.variables:
                raise ValueError("real candidate B grid missing "+key)
            masks[kind]=_must_binary(ds[key][:],key)
            if masks[kind].shape!=expected_shape:
                raise ValueError(f"{key} not frozen candidate B shape {expected_shape}")
        if not np.array_equal(masks["u"],masks["rho"][:,:-1]&masks["rho"][:,1:]):
            raise ValueError("actual U mask disagrees with RHO wet face connectivity")
        if not np.array_equal(masks["v"],masks["rho"][:-1,:]&masks["rho"][1:,:]):
            raise ValueError("actual V mask disagrees with RHO wet face connectivity")
        if masks["rho"].sum()!=96104:
            raise ValueError("candidate B wet RHO inventory is not 96104")
        if "h" not in ds.variables:
            raise ValueError("missing physical bathymetry h")
        h=np.asarray(np.ma.filled(np.ma.asarray(ds["h"][:],dtype=float),np.nan))
        if h.shape!=EXPECTED_SHAPES["rho"] or (
            not np.isfinite(h[masks["rho"]]).all()) or (h[masks["rho"]]<=0).any():
            raise ValueError("invalid positive wet RHO bathymetry in real grid")
        for name in ("angle","pm","pn"):
            if name not in ds.variables:
                raise ValueError("missing actual candidate C-grid "+name)
            a=np.asarray(np.ma.filled(np.ma.asarray(ds[name][:],dtype=float),np.nan))
            if a.shape!=EXPECTED_SHAPES["rho"] or not np.isfinite(a[masks["rho"]]).all():
                raise ValueError("invalid wet C-grid "+name)
            if name in ("pm","pn") and np.any(a[masks["rho"]]<=0):
                raise ValueError("nonpositive wet C-grid "+name)
    lengths={kind:len(wet_perimeter(mask)) for kind,mask in masks.items()}
    if lengths!=EXPECTED_COUNTS:
        raise ValueError(f"wrong actual candidate B wet perimeter counts: {lengths}")
    return masks,{"wet_rho_count":int(masks["rho"].sum()),"unique_wet_perimeter_counts":lengths}


def _admit_rows(rows:list,wet:np.ndarray,kind:str,parent_shape:tuple[int,int])->dict:
    if not isinstance(rows,list) or len(rows)!=EXPECTED_COUNTS[kind]:
        raise ValueError(f"{kind}: wrong donor row count")
    keys=set()
    num_coastal_single=num_coastal_multi=0
    max_weight_residual=0.
    donor_count_histogram={}
    for r in rows:
        if kind=="rho":
            key=(r.get("child_eta_rho_zero_based"),r.get("child_xi_rho_zero_based"))
            donors=r.get("donor_eta_xi_zero_based")
            coast=r.get("coastline_visible") is True
        else:
            key=(r.get("child_eta_face_zero_based"),r.get("child_xi_face_zero_based"))
            donors=r.get("donor_parent_rho_eta_xi_zero_based")
            coast=(r.get("GSHHG_L1_coastline_clear") is True and
                   r.get("native_parent_U_and_V_wet_face_support") is True)
        if not all(isinstance(k,int) and not isinstance(k,bool) for k in key):
            raise ValueError(f"{kind}: child receiver indices must be integer")
        if key in keys:
            raise ValueError(f"{kind}: duplicate wet receiver {key}")
        keys.add(key)
        if not (0<=key[0]<wet.shape[0] and 0<=key[1]<wet.shape[1] and wet[key]):
            raise ValueError(f"{kind}: donor receiver not a wet native C-grid target")
        if not coast:
            raise ValueError(f"{kind}: source donor not coast-visible/native-face supported")
        if not isinstance(donors,list) or len(donors)==0 or len(donors)>4:
            raise ValueError(f"{kind}: invalid donor list")
        if any(not isinstance(pair,list) or len(pair)!=2 or
               any(not isinstance(x,int) or isinstance(x,bool) for x in pair) or
               not (0<=pair[0]<parent_shape[0] and 0<=pair[1]<parent_shape[1])
               for pair in donors):
            raise ValueError(f"{kind}: invalid/outside parent RHO eta/xi coordinates")
        if len({tuple(pair) for pair in donors})!=len(donors):
            raise ValueError(f"{kind}: duplicated parent donor node")
        w=np.asarray(r.get("weights",[]),dtype=float)
        if w.ndim!=1 or len(w)!=len(donors) or not np.isfinite(w).all() or (
            w<-1e-12).any() or abs(float(w.sum())-1)>1e-10:
            raise ValueError(f"{kind}: nonpositive/incomplete normalized weights")
        max_weight_residual=max(max_weight_residual,abs(float(w.sum())-1))
        donor_count_histogram[str(len(donors))]=donor_count_histogram.get(str(len(donors)),0)+1
        if len(donors)==1:num_coastal_single+=1
        else:num_coastal_multi+=1
    perimeter=wet_perimeter(wet)
    if keys!=perimeter:
        raise ValueError(f"{kind}: map != actual wet perimeter missing={len(perimeter-keys)} extra={len(keys-perimeter)}")
    return {"verified_native_wet_receiver_count":len(keys),
            "weights_max_sum1_absolute_residual":float(max_weight_residual),
            "single_source_donor_receivers":num_coastal_single,
            "multiple_source_donor_receivers":num_coastal_multi,
            "source_donor_count_histogram":donor_count_histogram,
            "coastline_source_certification":"MANIFEST_AUDIT_FLAG_ONLY"}


def validate_real_candidate_b(grid_path:Path,rho_path:Path,uv_path:Path,
                              parent_shape:tuple[int,int]=PARENT_RHO_SHAPE)->dict:
    masks,geometry=read_masked_grid(grid_path)
    rho=json.loads(Path(rho_path).read_text(encoding="utf-8"))
    uv=json.loads(Path(uv_path).read_text(encoding="utf-8"))
    if rho.get("all_1011_source_RHO_weights_identical_to_original_1017_mapping") is not True:
        raise ValueError("original 1017 source scalar weights provenance missing")
    if rho.get("original_main_and_original_ud1k_grid_untouched") is not True:
        raise ValueError("candidate B original grid preservation not certified")
    if rho.get("actual_steady_3d_ROMs_bry_and_flux")!="NOT_RUN":
        raise ValueError("unexpected physical acceptance status in static RHO manifest")
    if not isinstance(uv.get("reports"),dict):
        raise ValueError("native face manifest reports not found")
    admitted={"rho":_admit_rows(rho["records"],masks["rho"],"rho",parent_shape)}
    for kind in ("u","v"):
        report=uv["reports"].get(kind,{})
        if report.get("native_wet_boundary_face_count")!=EXPECTED_COUNTS[kind] or (
            report.get("unresolved_face_receivers")!=0):
            raise ValueError(f"{kind}: native wet face hold or reported count")
        admitted[kind]=_admit_rows(report["records"],masks[kind],kind,parent_shape)
    native_section={}
    for side,kind in (("south","v"),("north","v"),("west","u"),("east","u")):
        mask=masks[kind]
        normal_edge=(mask[0] if side=="south" else
                     mask[-1] if side=="north" else
                     mask[:,0] if side=="west" else mask[:,-1])
        native_section[side]=int(normal_edge.sum())
    if native_section!=EXPECTED_NORMAL:
        raise ValueError(f"actual native boundary section counts differ: {native_section}")
    return {
        "status":"REAL_GEBCO_GSHHG_OPTION_B_STATIC_PERIMETER_DONOR_MANIFEST_PASS",
        "geometry_origin":"EXISTING_ARCHIVED_REAL_GRID_NO_GEBCO_DOWNLOAD",
        "option_b_status":"COMPARISON_CANDIDATE_NOT_ACTIVE",
        "geometry":geometry,
        "parent_rho_index_bounds_assumed":[int(x) for x in parent_shape],
        "parent_wet_cell_and_native_face_support":"NOT_RECHECKED_HERE_PRIOR_SOURCE_MANIFEST_CERTIFICATION_ONLY",
        "receivers":admitted,
        "wet_native_open_normal_section_counts":native_section,
        "total_wet_native_open_normal_faces":sum(native_section.values()),
        "real_ES3K_hydrodynamic_history":"NOT_AVAILABLE",
        "actual_time_dependent_bry_and_parent_child_mass_flux":"NOT_RUN",
        "real_UD1K_ocean_model_integration":"NOT_RUN",
    }


def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grid",type=Path,required=True)
    p.add_argument("--rho-map",type=Path,required=True)
    p.add_argument("--native-uv-map",type=Path,required=True)
    p.add_argument("--report-json",type=Path,required=True)
    args=p.parse_args()
    result=validate_real_candidate_b(args.grid,args.rho_map,args.native_uv_map)
    args.report_json.parent.mkdir(parents=True,exist_ok=True)
    args.report_json.write_text(json.dumps(result,indent=2)+"\n")
    print("UD1K_REAL_OPTIONB_STATIC_DONOR_PASS",json.dumps({
        "receivers":{k:x["verified_native_wet_receiver_count"]
                     for k,x in result["receivers"].items()},
        "native_normal_faces":result["wet_native_open_normal_section_counts"],
        "real_ocean_run":"NOT_RUN"},sort_keys=True))


if __name__=="__main__":
    main()
