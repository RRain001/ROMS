"""Real, independent UD1K U/V *receiver face* coastline donor preflight.

Each child U/V face is evaluated at its actual lon_u/lat_u or lon_v/lat_v;
never reuses a child RHO receiver coordinate or its RHO weights. Source
candidate donors are parent RHO nodes whose ROMS C-grid U *and* V native
faces exist and are wet. Weights support *collocated parent velocity vector*
sampling then local-angle rotation onto a child face (NOT direct parent
U-face to child U-face conservative interpolation).

Priority:
1. enclosing, convex, coastline-clear 4-wet/4-supported parent RHO quad;
2. enclosing coastline-clear 3-vertex triangle from one parent 2x2 RHO
   quad, with each vertex wet and face-supported;
3. bounded distance (2.5 parent cells), coast-visible, wet graph-connected
   multi/single-donor source fallback, marked as EXTRAPOLATION.
Never cross real GSHHG Level 1 coastline or silently fill zeros/dry faces.

RHO scalar weights and geometry remain unchanged. True ROMS dynamic
bry.nc, individual U/V parent native-face mapping, sigma-z and flux NOT_RUN.
"""
from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
import json
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset
from pyproj import CRS, Transformer
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, Point

_ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(_ROOT))
from ud1k_full_rho_boundary_map import inverse_bilinear
from ud1k_wet_triangle_review import _barycentric,_crosses_coast,_shoreline_parts
from ud1k_coastal_waterpath_fallback import classify_visible_wet_donors
from ud1k_boundary_cgrid_velocity import rotate_parent_to_child_rho
from shoreline import BoundingBox


def supported_rho_for_both_native_faces(wet:np.ndarray)->np.ndarray:
    """Native U/V face support at RHO (no proxy from mere RHO wetness)."""
    m=np.asarray(wet,dtype=bool)
    if m.ndim!=2 or min(m.shape)<3:
        raise ValueError("RHO wet mask too small")
    u=m[:,:-1]&m[:,1:]
    v=m[:-1,:]&m[1:,:]
    u_at=np.zeros_like(m)
    v_at=np.zeros_like(m)
    u_at[:,:-1]|=u
    u_at[:,1:]|=u
    v_at[:-1,:]|=v
    v_at[1:,:]|=v
    return m&u_at&v_at


def wet_perimeter_ij(mask:np.ndarray)->np.ndarray:
    """Unique row-major wet perimeter of a *native staggered* mask."""
    wet=np.asarray(mask,dtype=bool)
    if wet.ndim!=2 or min(wet.shape)<2:
        raise ValueError("native staggered wet mask must be 2D")
    rim=np.zeros_like(wet)
    rim[0,:]=rim[-1,:]=True
    rim[:,0]=rim[:,-1]=True
    return np.argwhere(rim&wet)


def generate_face_records(parent_xy:np.ndarray,parent_ll:np.ndarray,
                          parent_wet:np.ndarray,
                          child_xy:np.ndarray,child_ll:np.ndarray,
                          child_face_mask:np.ndarray,
                          coast_parts:list,*,parent_cell_m:float,
                          face_kind:str)->dict:
    """Exactly one donor row per native wet U/V perimeter face, four sides.

    A graph of qualifying source RHO nodes is used for bounded nearshore
    extrapolation; this is deliberately more restrictive than mere wet RHO.
    """
    if face_kind not in ("u","v"):
        raise ValueError("face_kind must be 'u' or 'v'")
    if child_xy.shape!=(*child_face_mask.shape,2) or child_ll.shape!=child_xy.shape:
        raise ValueError("invalid native staggered receiver geometry")
    support=supported_rho_for_both_native_faces(parent_wet)
    if parent_xy.shape!=(*support.shape,2) or parent_ll.shape!=parent_xy.shape:
        raise ValueError("invalid parent RHO geometry")
    # All parent 2x2 quads with at least 3 wet/face-supported corners.
    good=(support[:-1,:-1].astype(int)+support[:-1,1:].astype(int)+
          support[1:,1:].astype(int)+support[1:,:-1].astype(int))>=3
    anchors=np.argwhere(good)
    if len(anchors)==0:
        raise ValueError("no 3-supported-vertex ES3K quads")
    jj,ii=anchors[:,0],anchors[:,1]
    corner_nodes=np.stack((
        np.column_stack((jj,ii)),np.column_stack((jj,ii+1)),
        np.column_stack((jj+1,ii+1)),np.column_stack((jj+1,ii))),axis=1)
    quads=parent_xy[corner_nodes[:,:,0],corner_nodes[:,:,1]]
    center=np.mean(quads,axis=1)
    radius=float(np.linalg.norm(quads-center[:,None,:],axis=2).max())
    tree=cKDTree(center)
    receivers=wet_perimeter_ij(child_face_mask)
    if not len(receivers):
        raise ValueError("no wet staggered receiver boundary faces")
    target_xy=child_xy[receivers[:,0],receivers[:,1]]
    candidates=tree.query_ball_point(target_xy,r=np.nextafter(radius,np.inf))
    output=[]
    counts=Counter()
    child_ny,child_nx=child_face_mask.shape
    for (cj,ci),target,quad_indices in zip(receivers,target_xy,candidates):
        cj,ci=int(cj),int(ci)
        lonlat=child_ll[cj,ci]
        options=[]
        for q in quad_indices:
            nodes=corner_nodes[q]
            sample_xy=quads[q]
            iswet=support[nodes[:,0],nodes[:,1]]
            if iswet.all():
                w=inverse_bilinear(sample_xy,target)
                if w is not None:
                    geographic=parent_ll[nodes[:,0],nodes[:,1]]
                    if not _crosses_coast(geographic,coast_parts):
                        dist=float(np.linalg.norm(sample_xy-target,axis=1).max())
                        options.append((0,dist,"FOUR_SUPPORTED_PARENT_RHO_BILINEAR",nodes,w))
            # Three-supported subtriangles (also if four-wet quad crosses coast).
            for selection in combinations(range(4),3):
                local=np.array(selection,dtype=int)
                if not iswet[local].all():
                    continue
                tri_nodes=nodes[local]
                xy=sample_xy[local]
                weights=_barycentric(xy,target)
                if weights is None:
                    continue
                geo=parent_ll[tri_nodes[:,0],tri_nodes[:,1]]
                if _crosses_coast(geo,coast_parts):
                    continue
                dist=float(np.linalg.norm(xy-target,axis=1).max())
                options.append((1,dist,"THREE_SUPPORTED_PARENT_RHO_TRIANGLE",tri_nodes,weights))
        if options:
            options.sort(key=lambda x:(x[0],x[1]))
            priority,dist,method,nodes,weights=options[0]
            source="ENCLOSING_LOCAL_2x2_PARENT_QUAD"
            enclosing=True
        else:
            alt=classify_visible_wet_donors(
                parent_xy,parent_ll,support,target,lonlat,coast_parts,
                median_cell_m=parent_cell_m,max_cell_radius=2.5,
                max_donors=4,max_graph_hops=8)
            donors=alt.get("selected_donors",[])
            if not donors:
                method="HOLD_NO_COAST_VISIBLE_CGRID_FACE_SUPPORTED_PARENT_DONORS"
                output.append({"child_eta_face_zero_based":cj,
                               "child_xi_face_zero_based":ci,
                               "child_lon":float(lonlat[0]),"child_lat":float(lonlat[1]),
                               "status":method,"diagnostics":alt})
                counts[method]+=1
                continue
            nodes=np.array([[s["eta_rho_zero_based"],s["xi_rho_zero_based"]] for s in donors],dtype=int)
            weights=np.array([s["weight"] for s in donors],dtype=float)
            dist=float(alt["max_selected_distance_m"])
            method=("COAST_VISIBLE_FACE_SUPPORTED_MULTI_IDW_EXTRAPOLATION" if len(nodes)>1
                    else "COAST_VISIBLE_FACE_SUPPORTED_SINGLE_EXTRAPOLATION")
            source="BOUNDED_WET_VISIBLE_CGRID_FACE_SUPPORTED_RHO"
            enclosing=False
        if (not np.isfinite(weights).all() or (weights<0).any()
                or abs(float(weights.sum())-1)>1e-10
                or not support[nodes[:,0],nodes[:,1]].all()):
            raise ValueError("invalid actual C-grid-face-supported donor weights")
        row={
            "child_eta_face_zero_based":cj,
            "child_xi_face_zero_based":ci,
            "child_lon":float(lonlat[0]),"child_lat":float(lonlat[1]),
            "logical_sides":[s for s,flag in (("south",cj==0),("north",cj==child_ny-1),
                       ("west",ci==0),("east",ci==child_nx-1)) if flag],
            "method":method,"source_kind":source,"enclosing_geometry":enclosing,
            "GSHHG_L1_coastline_clear":True,
            "donor_parent_rho_eta_xi_zero_based":nodes.astype(int).tolist(),
            "weights":np.asarray(weights,dtype=float).tolist(),
            "max_parent_donor_distance_m":dist,
            "native_parent_U_and_V_wet_face_support":True,
            "parent_values_are_native_face_collocated_at_rho":True,
        }
        output.append(row)
        counts[method]+=1
    sidecounts={s:sum(s in r["logical_sides"] for r in output if "logical_sides" in r)
                for s in ("south","north","west","east")}
    unsupported=counts.get("HOLD_NO_COAST_VISIBLE_CGRID_FACE_SUPPORTED_PARENT_DONORS",0)
    return {
        "scope":f"UD1K_NATIVE_{face_kind.upper()}_STAGGERED_WET_FACE_PERIMETER",
        "parent_sources":"ES3K_COLLOCATED_NATIVE_U_AND_V_WET_FACE_SUPPORTED_RHO",
        "source_position_precision":"ACTUAL_CHILD_NATIVE_LON_LAT_FACE",
        "target_face_kind":face_kind,
        "native_receiver_shape_eta_xi":list(child_face_mask.shape),
        "native_wet_boundary_face_count":int(len(receivers)),
        "side_counts_corner_overlap":sidecounts,
        "counts_by_source_method":dict(counts),
        "unresolved_face_receivers":int(unsupported),
        "native_coordinate_mapping_must_not_reuse_RHO_receiver_weights":True,
        "is_true_parent_direct_U_to_child_U_or_V_to_child_V_remap":False,
        "physical_sigma_z_barotropic_flux_and_bry_nc":"NOT_RUN",
        "no_mask_modified":True,
        "records":output,
    }


def rotate_parent_collocated_to_child_face(u_parent:np.ndarray,v_parent:np.ndarray,
                                           parent_wet:np.ndarray,
                                           parent_angle_rho:np.ndarray,
                                           child_angle_face:np.ndarray,
                                           report:dict)->dict:
    """Evaluate source native U/V, angle-rotate, interpolate at true child face.

    Existing collocation implementation operates on arbitrary target (j,i)
    array as an abstract 2D index; explicitly labels result as *face*
    to prevent confusing it with RHO diagnostics.
    """
    if report["unresolved_face_receivers"]:
        raise ValueError("no valid face velocity donor stencil for every target")
    records=[]
    for r in report["records"]:
        records.append({
            "child_eta_rho_zero_based":r["child_eta_face_zero_based"],
            "child_xi_rho_zero_based":r["child_xi_face_zero_based"],
            "donor_eta_xi_zero_based":r["donor_parent_rho_eta_xi_zero_based"],
            "weights":r["weights"],
        })
    out=rotate_parent_to_child_rho(
        u_parent,v_parent,parent_wet,parent_angle_rho,child_angle_face,records)
    kind=report["target_face_kind"]
    return {
        "face_kind":kind,
        "child_axis_velocity_at_actual_face":
            out["child_u_axis_at_rho_only"] if kind=="u" else out["child_v_axis_at_rho_only"],
        "east_at_actual_face":out["east_at_child_rho"],
        "north_at_actual_face":out["north_at_child_rho"],
        "parent_velocity_interpolation":"NATIVE_PARENT_UV_COLLOCATED_TO_WET_RHO_SOURCES",
        "actual_ROMS_parent_velocity_timeseries":"NOT_RUN",
        "physical_sigma_z_or_flux_or_bry_nc":"NOT_RUN",
    }


def run(parent:Path,child:Path,gshhg_base:Path)->dict:
    with Dataset(parent) as f:
        plon=np.asarray(f["lon_rho"][:],dtype=float)
        plat=np.asarray(f["lat_rho"][:],dtype=float)
        pwet=np.asarray(f["mask_rho"][:],dtype=bool)
        ap=np.asarray(f["angle"][:],dtype=float)
        pm=np.asarray(f["pm"][:],dtype=float)
        pn=np.asarray(f["pn"][:],dtype=float)
    with Dataset(child) as f:
        clon=np.asarray(f["lon_rho"][:],dtype=float)
        clat=np.asarray(f["lat_rho"][:],dtype=float)
        crho=np.asarray(f["mask_rho"][:],dtype=bool)
        ac=np.asarray(f["angle"][:],dtype=float)
        src={}
        for kind in ("u","v"):
            for key in ("lon_"+kind,"lat_"+kind,"mask_"+kind):
                if key not in f.variables:
                    raise ValueError(f"native child C-grid variable missing: {key}")
                src[key]=np.asarray(f[key][:])
    if crho.shape!=(290,438) or ac.shape!=crho.shape or plon.shape!=pwet.shape:
        raise ValueError("changed current UD1K or parent grid")
    if not np.array_equal(src["mask_u"].astype(bool),(crho[:,:-1]&crho[:,1:])) or not np.array_equal(
            src["mask_v"].astype(bool),(crho[:-1,:]&crho[1:,:])):
        raise ValueError("ROMS face masks not derived from wet RHO adjacency")
    bbox=BoundingBox(float(clon.min()-.3),float(clon.max()+.3),
                     float(clat.min()-.3),float(clat.max()+.3))
    coast,meta=_shoreline_parts(gshhg_base,bbox,resolution="h")
    if not coast:
        raise ValueError("real GSHHG shoreline required")
    tr=Transformer.from_crs("EPSG:4326",CRS.from_proj4(
        f"+proj=aeqd +lat_0={plat.mean()} +lon_0={plon.mean()} +datum=WGS84 +units=m +no_defs"
    ),always_xy=True)
    px,py=tr.transform(plon,plat)
    pxy=np.stack((px,py),axis=-1)
    pll=np.stack((plon,plat),axis=-1)
    parent_cell_m=float(np.median(1/np.sqrt(pm*pn)))
    reports={}
    for kind in ("u","v"):
        lon=src["lon_"+kind]
        lat=src["lat_"+kind]
        mask=src["mask_"+kind].astype(bool)
        x,y=tr.transform(lon,lat)
        xy=np.stack((x,y),axis=-1)
        report=generate_face_records(pxy,pll,pwet,xy,np.stack((lon,lat),axis=-1),
                                     mask,coast,parent_cell_m=parent_cell_m,face_kind=kind)
        native_angle=((ac[:,:-1]+ac[:,1:])/2 if kind=="u"
                       else (ac[:-1,:]+ac[1:,:])/2)
        native_u=np.ones((1,pwet.shape[0],pwet.shape[1]-1),dtype=float)
        native_v=np.zeros((1,pwet.shape[0]-1,pwet.shape[1]),dtype=float)
        if report["unresolved_face_receivers"]==0:
            out=rotate_parent_collocated_to_child_face(
                native_u,native_v,pwet,ap,native_angle,report)
            result=out["child_axis_velocity_at_actual_face"]
            if result.shape!=(1,report["native_wet_boundary_face_count"]) or not np.isfinite(result).all():
                raise ValueError("invalid real-geometry synthetic face rotation probe")
            report["synthetic_native_U1_V0_local_angle_rotation_probe"]={
                "all_finite":True,"returned_velocity_shape":list(result.shape),
                "min_velocity":float(result.min()),
                "max_velocity":float(result.max()),
                "real_roms_dynamic_velocity":"NOT_RUN",
            }
        reports[kind]=report
    return {
        "scope":"CURRENT_UD1K_ACTUAL_NATIVE_U_AND_V_FACE_BOTH_PERIMETERS",
        "same_ES3K_GEBCO2026_native15s_GSHHG237_High_L1":True,
        "parent_name":parent.name,"child_name":child.name,
        "ES3K_parent_cell_m_median":parent_cell_m,
        "coastline_source_shapefile":str(meta.shapefile_path),
        "reports":reports,
        "all_current_parent_child_masks_unchanged":True,
        "real_UD1K_u_v_ubar_vbar_bry_flux_validation":"NOT_RUN",
    }


def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("parent-grid","child-grid","gshhg-base","output-json"):
        p.add_argument("--"+key,type=Path,required=True)
    a=p.parse_args()
    result=run(a.parent_grid,a.child_grid,a.gshhg_base)
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(result,indent=2)+"\n")
    for kind,report in result["reports"].items():
        print("UD1K_ACTUAL_NATIVE_"+kind.upper()+"_FACE_WET_PERIMETER",
              json.dumps({"count":report["native_wet_boundary_face_count"],
                          "sides":report["side_counts_corner_overlap"],
                          "methods":report["counts_by_source_method"],
                          "unresolved":report["unresolved_face_receivers"]},sort_keys=True))
    print("REAL_NATIVE_FACE_STATIC_MAPPING_ONLY; TRUE_DYNAMIC_BRY_NOT_RUN")


if __name__=="__main__":
    main()
