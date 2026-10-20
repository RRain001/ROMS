"""Read-only comparison: retain UD1K's dominant 4-neighbor ocean wet component.

The original user-approved 290x438 bathymetric grid is NOT modified.
Write a new, opt-in NETCDF4 candidate that only removes RHO wet cells in
small components not four-neighbor connected to the dominant Sea of Japan
water body. Native C-grid mask_u/mask_v/mask_psi are reconstructed from
the resulting mask_rho with canonical ROMS staggering, preserving other
grid and bathymetry fields. No extra geographical coastline editing,
arbitrary coastal clipping or geometry/bounds changes.

Results are still static candidates, not accepted ROMS physical runs.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil

import numpy as np
from netCDF4 import Dataset
from scipy.ndimage import label


FOUR_NEIGHBOR=np.array([[0,1,0],[1,1,1],[0,1,0]],dtype=np.uint8)


def connected_core_masks(mask_rho:np.ndarray)->tuple[dict,dict]:
    """Main ocean is largest 4-connected component, all smaller pools retained in audit."""
    old=np.asarray(mask_rho,dtype=bool)
    if old.ndim!=2 or old.size==0 or not old.any():
        raise ValueError("expected nonempty RHO wet mask")
    components,n=label(old,structure=FOUR_NEIGHBOR)
    sizes=np.bincount(components.ravel(),minlength=n+1)
    largest=int(np.argmax(sizes[1:])+1)
    if sizes[largest] <= old.sum()/2:
        raise ValueError("no unambiguous dominant connected ocean component")
    kept=components==largest
    rho_removed=np.argwhere(old&~kept)
    component_info=[]
    for c in range(1,n+1):
        pts=np.argwhere(components==c)
        lo=pts.min(axis=0);hi=pts.max(axis=0)
        boundary=int(np.sum((pts[:,0]==0)|(pts[:,0]==old.shape[0]-1)|
                            (pts[:,1]==0)|(pts[:,1]==old.shape[1]-1)))
        component_info.append({
            "component_label":c,"RHO_wet_cell_count":int(sizes[c]),
            "bbox_eta_xi_zero_based":[lo.tolist(),hi.tolist()],
            "wet_perimeter_rho_count":boundary,
            "kept_as_dominant_ocean":bool(c==largest),
        })
    def masks(m):
        return {
            "mask_rho":m.astype("i1"),
            "mask_u":(m[:,:-1]&m[:,1:]).astype("i1"),
            "mask_v":(m[:-1,:]&m[1:,:]).astype("i1"),
            "mask_psi":(m[:-1,:-1]&m[:-1,1:]&m[1:,:-1]&m[1:,1:]).astype("i1"),
        }
    old_masks=masks(old)
    new_masks=masks(kept)
    diff={}
    for key in old_masks:
        wet_old=old_masks[key].astype(bool)
        wet_new=new_masks[key].astype(bool)
        perimeter=np.zeros_like(wet_old,dtype=bool)
        perimeter[0,:]=perimeter[-1,:]=True
        perimeter[:,0]=perimeter[:,-1]=True
        diff[key]={
            "old_wet_total":int(wet_old.sum()),
            "new_wet_total":int(wet_new.sum()),
            "removed_total":int((wet_old&~wet_new).sum()),
            "old_wet_perimeter":int((wet_old&perimeter).sum()),
            "new_wet_perimeter":int((wet_new&perimeter).sum()),
            "removed_wet_perimeter":int((wet_old&~wet_new&perimeter).sum()),
        }
    return new_masks,{
        "scope":"SEPARATE_UD1K_ONLY_DOMINANT_4_CONNECTED_WET_COMPONENT_CANDIDATE",
        "source_shape_eta_rho_xi_rho":list(old.shape),
        "wet_component_count":n,
        "dominant_component_label":largest,
        "components":component_info,
        "removed_RHO_points_eta_xi_zero_based":rho_removed.tolist(),
        "component_mask_differences":diff,
        "method":"FOUR_NEIGHBOR_WET_GRAPH_CONNECTED_LARGEST_COMPONENT_ONLY",
        "only_independent_disconnected_pool_wet_RHO_removed":True,
        "geographic_grid_extent_and_spacing_unchanged":True,
        "coastline_input_resolution_unchanged":True,
        "source_grid_modified":False,
        "physical_one_way_bry_nc_and_current_validation":"NOT_RUN",
    }


def make_candidate(original:Path,output:Path,report_path:Path)->dict:
    src=Path(original)
    dst=Path(output)
    if not src.exists() or src.resolve()==dst.resolve() or dst.exists():
        raise ValueError("source missing / destination same or already exists (never overwrite)")
    with Dataset(src) as f:
        if any(key not in f.variables for key in ("mask_rho","mask_u","mask_v","mask_psi","h")):
            raise ValueError("not a complete ROMS C-grid bathymetric input")
        original_masks={key:np.asarray(f[key][:],dtype=np.int8)
                        for key in ("mask_rho","mask_u","mask_v","mask_psi")}
        original_rho=original_masks["mask_rho"].astype(bool)
        if original_rho.shape!=(290,438):
            raise ValueError("this frozen UD1K case requires 290x438")
        original_h=np.asarray(f["h"][:])
        old_attrs=dict(f.__dict__)
        lon=np.asarray(f["lon_rho"][:],float)
        lat=np.asarray(f["lat_rho"][:],float)
    derived,report=connected_core_masks(original_rho)
    for k in derived:
        if not np.array_equal(original_masks[k], (
            original_rho.astype("i1") if k=="mask_rho" else
            (original_rho[:,:-1]&original_rho[:,1:]).astype("i1") if k=="mask_u" else
            (original_rho[:-1,:]&original_rho[1:,:]).astype("i1") if k=="mask_v" else
            (original_rho[:-1,:-1]&original_rho[:-1,1:]&original_rho[1:,:-1]&original_rho[1:,1:]).astype("i1")
        )):
            raise ValueError("source C-grid mask inconsistent with original wet RHO")
    if report["component_mask_differences"]["mask_rho"]["removed_total"]!=20:
        raise ValueError("unexpected current user real grid island count; no automatic mask changes")
    if report["component_mask_differences"]["mask_v"]["new_wet_perimeter"]!=1013:
        raise ValueError("unexpected native V perimeter count after removing isolated pockets")
    report["removed_RHO_geocoordinates"]=[
        {"eta_rho":int(j),"xi_rho":int(i),"lon":float(lon[j,i]),"lat":float(lat[j,i])}
        for j,i in report["removed_RHO_points_eta_xi_zero_based"]]
    # Make a NEW artifact, never in-place editing of user's frozen original.
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dst)
    with Dataset(dst,"a") as f:
        for k,v in derived.items():
            if f[k].shape!=v.shape:
                raise ValueError("native C-grid variable shape mismatch")
            f[k][:]=v
        f.setncattr("connected_core_candidate_status","EXPERIMENTAL_SEPARATE_READ_ONLY_SOURCE_NOT_ACCEPTED")
        f.setncattr("connected_core_method","largest 4-neighbor RHO wet component only")
        f.setncattr("connected_core_source_grid",src.name)
    with Dataset(src) as original_ds,Dataset(dst) as candidate:
        for key in ("h","lon_rho","lat_rho","pm","pn","angle"):
            if not np.array_equal(original_ds[key][:],candidate[key][:]):
                raise ValueError("candidate altered static bathymetry or grid coordinate")
        for k,v in derived.items():
            if not np.array_equal(candidate[k][:],v):
                raise ValueError("saved mask mismatch")
        if not np.array_equal(original_ds["mask_rho"][:],original_masks["mask_rho"]):
            raise ValueError("source mask was modified")
    report.update({
        "original_grid_file":src.name,
        "separate_candidate_grid_file":dst.name,
        "original_wet_RHO_eta0_xi30":bool(original_rho[0,30]),
        "new_wet_RHO_eta0_xi30":bool(derived["mask_rho"][0,30]),
        "original_wet_V_eta0_xi30":bool(original_masks["mask_v"][0,30]),
        "new_wet_V_eta0_xi30":bool(derived["mask_v"][0,30]),
        "original_coordinate_and_bathymetry_arrays_bitwise_unchanged":True,
        "candidate_written_and_read_back":True,
        "candidate_promoted_for_real_hydrodynamics":False,
    })
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,indent=2)+"\n")
    print("UD1K_DOMINANT_OCEAN_WET_CORE_ONLY",json.dumps({
        "components":report["wet_component_count"],
        "removed_RHO":report["component_mask_differences"]["mask_rho"]["removed_total"],
        "removed_U":report["component_mask_differences"]["mask_u"]["removed_total"],
        "removed_V":report["component_mask_differences"]["mask_v"]["removed_total"],
        "new_wet_RHO_perimeter":report["component_mask_differences"]["mask_rho"]["new_wet_perimeter"],
        "new_wet_U_perimeter":report["component_mask_differences"]["mask_u"]["new_wet_perimeter"],
        "new_wet_V_perimeter":report["component_mask_differences"]["mask_v"]["new_wet_perimeter"],
        "one_unresolved_old_V_0_30_removed_from_disconnected_pool":not report["new_wet_V_eta0_xi30"],
    },sort_keys=True))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("original-grid","output-grid","report-json"):
        p.add_argument("--"+k,required=True,type=Path)
    a=p.parse_args()
    make_candidate(a.original_grid,a.output_grid,a.report_json)


if __name__=="__main__":
    main()
