"""Geographic ES3K -> current UD1K *RHO* open-perimeter scalar mapping audit.

- Every wet UD1K RHO perimeter point appears exactly once, even at corners.
- Ordinary donor: exact enclosing 4-wet ES3K curvilinear quadrilateral,
  with invertible *bilinear* projected coordinate weights, not nearest wet.
- For the 27 previously unresolved points: preserve the separately audited
  coast-visible triangle / bounded wet-only extrapolation source mapping.
- Every four-wet quad also gets GSHHG level-1 polygon-boundary intersection
  diagnostics. If it crosses coastline, this is explicitly flagged; never
  silently treat a four-wet-vertex stencil as safe over a peninsula.
- Completely separate from ROMS run configuration, actual bry.nc, staggered
  U/V, sigma-vertical remapping and normal-volume flux. ALL NOT_RUN.

This script and its NetCDF source grids are read-only. No grid masks edited.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset
from pyproj import CRS, Transformer
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon

_LOCAL=Path(__file__).resolve().parent
sys.path.insert(0,str(_LOCAL))
from ud1k_wet_triangle_review import _shoreline_parts,_crosses_coast
from ud1k_boundary_rho_fallback_map import apply_scalar_stencils
from shoreline import BoundingBox


def inverse_bilinear(corners: np.ndarray,target: np.ndarray) -> np.ndarray | None:
    """Inverse physical-space bilinear quad map in [SW,SE,NE,NW] order.

    Mathematically affine fields are reproduced under this bilinear map.
    Fails closed for nonconvex quads, nonfinite or stalled iteration.
    """
    p=np.asarray(corners,dtype=float)
    q=np.asarray(target,dtype=float)
    if p.shape!=(4,2) or q.shape!=(2,) or not np.isfinite(p).all() or not np.isfinite(q).all():
        raise ValueError("expected finite quad [4,2] and point [2]")
    poly=Polygon(p)
    if not (poly.is_valid and poly.area>1e-8 and poly.equals(poly.convex_hull)):
        return None
    if not poly.buffer(1e-6).covers(Point(float(q[0]),float(q[1]))):
        return None
    origin=p[0]
    vx=p[1]-origin
    vy=p[3]-origin
    cross=p[0]-p[1]+p[2]-p[3]
    size=max(float(np.linalg.norm(vx)),float(np.linalg.norm(vy)),1.)
    if abs(float(np.linalg.det(np.column_stack([vx,vy]))))<1e-12*size**2:
        return None
    # Bilinear physical map p(s,t) = origin+s*vx+t*vy+s*t*cross.
    try:
        uv=np.linalg.solve(np.column_stack([vx,vy]),q-origin)
    except np.linalg.LinAlgError:
        return None
    for _ in range(24):
        s,t=map(float,uv)
        resid=origin+s*vx+t*vy+s*t*cross-q
        if float(np.linalg.norm(resid))<1e-7:
            break
        jac=np.column_stack([vx+t*cross,vy+s*cross])
        if abs(float(np.linalg.det(jac)))<1e-13*size**2:
            return None
        uv=uv-np.linalg.solve(jac,resid)
    s,t=map(float,uv)
    if float(np.linalg.norm(origin+s*vx+t*vy+s*t*cross-q))>1e-6:
        return None
    if min(s,t)<-1e-9 or max(s,t)>1+1e-9:
        return None
    s,t=float(np.clip(s,0,1)),float(np.clip(t,0,1))
    w=np.array([(1-s)*(1-t),s*(1-t),s*t,(1-s)*t],dtype=float)
    if not np.isfinite(w).all() or w.min()<0 or abs(w.sum()-1)>1e-11:
        return None
    return w


def _prepare_parent_quads(parent_xy: np.ndarray,wet:np.ndarray):
    eligible=wet[:-1,:-1]&wet[:-1,1:]&wet[1:,1:]&wet[1:,:-1]
    anchors=np.argwhere(eligible)
    j=anchors[:,0]
    i=anchors[:,1]
    four=np.stack((parent_xy[j,i],parent_xy[j,i+1],
                   parent_xy[j+1,i+1],parent_xy[j+1,i]),axis=1)
    cent=four.mean(axis=1)
    radius=float(np.max(np.linalg.norm(four-cent[:,None,:],axis=2))) if len(four) else 0.
    return anchors,four,cent,radius


def assemble(parent_xy:np.ndarray,parent_lonlat:np.ndarray,
             parent_wet:np.ndarray,child_xy:np.ndarray,child_lonlat:np.ndarray,
             child_wet:np.ndarray,fallback:dict,coast_parts:list)->dict:
    """All actual wet RHO perimeter positions, deterministic row-major order."""
    pwet=np.asarray(parent_wet,dtype=bool)
    cwet=np.asarray(child_wet,dtype=bool)
    boundary=np.zeros_like(cwet)
    boundary[0,:]=boundary[-1,:]=True
    boundary[:,0]=boundary[:,-1]=True
    pairs=np.argwhere(cwet&boundary)
    if len(pairs)!=1017 or cwet.shape!=(290,438):
        raise ValueError("current UD1K wet boundary geometry changed unexpectedly")
    back={}
    for r in fallback["records"]:
        key=(int(r["child_eta_rho_zero_based"]),int(r["child_xi_rho_zero_based"]))
        if key in back:
            raise ValueError("duplicate fallback RHO")
        back[key]=r
    if len(back)!=27:
        raise ValueError("requires exactly 27 coastal RHO mappings")
    anchors,quads,cent,radius=_prepare_parent_quads(parent_xy,pwet)
    if not len(quads):
        raise ValueError("no valid wet donor quads")
    tree=cKDTree(cent)
    coords=child_xy[pairs[:,0],pairs[:,1]]
    nearby=tree.query_ball_point(coords,r=np.nextafter(radius,np.inf))
    ordinary=[]
    backrows=[]
    conflicts=[]
    for (j,i),target,indices in zip(pairs,coords,nearby):
        j,i=int(j),int(i)
        key=(j,i)
        geo=child_lonlat[j,i]
        if key in back:
            row=dict(back[key])
            if abs(float(row["child_lon"])-float(geo[0]))>1e-9 or abs(float(row["child_lat"])-float(geo[1]))>1e-9:
                raise ValueError("fallback lon/lat mismatch")
            if not cwet[j,i]:
                raise ValueError("fallback child dry")
            nodes=np.asarray(row["donor_eta_xi_zero_based"],dtype=int)
            weights=np.asarray(row["weights"],dtype=float)
            if not pwet[nodes[:,0],nodes[:,1]].all() or (weights<0).any() or not np.isclose(weights.sum(),1,atol=1e-10):
                raise ValueError("invalid fallback donor geometry/weights")
            row["source_kind"]="COAST_VISIBLE_PREVIOUSLY_AUDITED_FALLBACK"
            backrows.append(row)
            continue
        options=[]
        for n in indices:
            w=inverse_bilinear(quads[n],target)
            if w is None:
                continue
            a,b=map(int,anchors[n])
            nodes=np.array([[a,b],[a,b+1],[a+1,b+1],[a+1,b]],dtype=int)
            lonlat=parent_lonlat[nodes[:,0],nodes[:,1]]
            crosses=_crosses_coast(lonlat,coast_parts)
            dist=float(np.linalg.norm(quads[n]-target[None,:],axis=1).max())
            options.append((crosses,dist,nodes,w))
        if not options:
            raise ValueError(f"wet current UD1K RHO boundary {(j,i)} has no full quad or audited fallback")
        options.sort(key=lambda t:(t[0],t[1]))
        crosses,dist,nodes,weights=options[0]
        row={
            "child_eta_rho_zero_based":j,"child_xi_rho_zero_based":i,
            "child_lon":float(geo[0]),"child_lat":float(geo[1]),
            "method":"BILINEAR_FOUR_WET_PARENT_RHO_PROJECTED_AEQD",
            "source_kind":"ALL_WET_PARENT_QUAD",
            "donor_eta_xi_zero_based":nodes.astype(int).tolist(),
            "weights":weights.tolist(),
            "maximum_donor_distance_m":dist,
            "enclosing_geometry":True,
            "GSHHG_level1_coastline_intersection":bool(crosses),
            "coastline_visible":not bool(crosses),
            "boundary_physical_acceptance":"NOT_RUN",
        }
        ordinary.append(row)
        if crosses:
            conflicts.append({"eta_rho_zero_based":j,"xi_rho_zero_based":i,
                              "lon":float(geo[0]),"lat":float(geo[1])})
    if len(ordinary)!=990 or len(backrows)!=27:
        raise ValueError(f"unexpected source breakdown 4wet={len(ordinary)}, fallback={len(backrows)}")
    allrows=sorted(ordinary+backrows,key=lambda r:(r["child_eta_rho_zero_based"],r["child_xi_rho_zero_based"]))
    if len({(r["child_eta_rho_zero_based"],r["child_xi_rho_zero_based"]) for r in allrows})!=len(pairs):
        raise ValueError("duplicated receiver RHO wet perimeter")
    return {
        "scope":"CURRENT_UD1K_ALL_1017_WET_RHO_PERIMETER_POINTS",
        "mapping":"BILINEAR_990_FOUR_WET_PLUS_PRESERVED_27_FALLBACK",
        "counts":{"ordinary_four_wet_quad":len(ordinary),
                  "audited_27_fallback":len(backrows),
                  "total_wet_perimeter":len(allrows),
                  "ordinary_quad_crosses_GSHHG_level1":len(conflicts)},
        "ordinary_quad_coastline_conflicts":conflicts,
        "all_rows_geometrically_mapped":True,
        "no_land_mask_modification":True,
        "invalid_status":"UNVERIFIED_IF_ANY_FOUR_WET_QUAD_CROSSES_GSHHG",
        "ROMS_staggered_velocity_vertical_transport_flux_validation":"NOT_RUN",
        "records":allrows,
    }


def run(parent:Path,child:Path,fallback_json:Path,gshhg_base:Path)->dict:
    with Dataset(parent) as f:
        plon=np.asarray(f["lon_rho"][:],dtype=float)
        plat=np.asarray(f["lat_rho"][:],dtype=float)
        pwet=np.asarray(f["mask_rho"][:],dtype=bool)
        h=np.asarray(f["h"][:],dtype=float)
    with Dataset(child) as f:
        clon=np.asarray(f["lon_rho"][:],dtype=float)
        clat=np.asarray(f["lat_rho"][:],dtype=float)
        cwet=np.asarray(f["mask_rho"][:],dtype=bool)
    coast_bbox=BoundingBox(float(clon.min()-.3),float(clon.max()+.3),
                          float(clat.min()-.3),float(clat.max()+.3))
    coasts,meta=_shoreline_parts(gshhg_base,coast_bbox,resolution="h")
    if not coasts:
        raise ValueError("real GSHHG 2.3.7 h L1 shoreline missing")
    crs=CRS.from_proj4(f"+proj=aeqd +lat_0={plat.mean()} +lon_0={plon.mean()} +datum=WGS84 +units=m +no_defs")
    tf=Transformer.from_crs("EPSG:4326",crs,always_xy=True)
    px,py=tf.transform(plon,plat)
    cx,cy=tf.transform(clon,clat)
    state=assemble(np.stack((px,py),axis=-1),
                   np.stack((plon,plat),axis=-1),pwet,
                   np.stack((cx,cy),axis=-1),
                   np.stack((clon,clat),axis=-1),cwet,
                   json.loads(fallback_json.read_text()),coasts)
    vals=apply_scalar_stencils(h,state["records"])
    const=apply_scalar_stencils(np.ones_like(h),state["records"])
    if not np.isfinite(vals).all() or not np.allclose(const,1,atol=1e-12,rtol=0):
        raise ValueError("failed native full-boundary scalar numerical smoke")
    state["real_data_numeric_check"]={
        "parent_depth_samples_all_finite":True,
        "constant_field_max_abs_err":float(np.max(abs(const-1))),
        "sampled_parent_depth_min_m":float(vals.min()),
        "sampled_parent_depth_max_m":float(vals.max()),
        "source_geometry":"GEBCO2026_NATIVE15S_GSHHG237_HIGH",
        "scalar_time_dependent_bry_generation":"NOT_RUN",
    }
    return state


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("parent-grid","child-grid","fallback-manifest","gshhg-base","output-json"):
        ap.add_argument("--"+name,type=Path,required=True)
    args=ap.parse_args()
    result=run(args.parent_grid,args.child_grid,args.fallback_manifest,args.gshhg_base)
    args.output_json.parent.mkdir(parents=True,exist_ok=True)
    args.output_json.write_text(json.dumps(result,indent=2)+"\n")
    print("UD1K_FULL_WET_RHO_BOUNDARY_COUNTS",json.dumps(result["counts"],sort_keys=True))
    print("UD1K_FULL_RHO_NUMERIC",json.dumps(result["real_data_numeric_check"],sort_keys=True))
    print("NOT_A_PRODUCTION_BRY_FILE")


if __name__=="__main__":
    main()
