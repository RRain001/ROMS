"""Read-only coastal fallback candidate audit for unresolved ES3K->UD1K RHO points.

A triangle is eligible ONLY when its three donor RHO vertices lie in one
immediately adjacent parent 2x2 RHO quad, all three vertices are wet, the
receiver lies within the triangle, and projected barycentric weights are
nonnegative. No nearest-wet interpolation, arbitrary Delaunay stitching,
off-domain extrapolation or child-mask mutation is permitted.

For an eligible triangle, independent GSHHG Level-1 coastline linework
must not intersect its geographic triangle. These are *static candidate
checks*, not production ROMS physical interpolation/flux acceptance.
"""
from __future__ import annotations

from pathlib import Path
import json
import sys

import numpy as np
from netCDF4 import Dataset
from pyproj import CRS, Transformer
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, LineString

_PRE = Path(__file__).resolve().parents[1] / "impl" / "preprocessing"
if str(_PRE) not in sys.path:
    sys.path.insert(0, str(_PRE))
from shoreline import BoundingBox, load_shoreline_geometry


def _candidate_index(xy: np.ndarray, wet: np.ndarray):
    """All 3-wet donor RHO triangles in a single 2x2 logical parent cell."""
    if xy.shape != (*wet.shape, 2) or wet.ndim != 2 or min(wet.shape) < 2:
        raise ValueError("incompatible parent xy/mask")
    v = np.stack((wet[:-1, :-1], wet[:-1, 1:],
                  wet[1:, 1:], wet[1:, :-1]), axis=-1)
    valid = (v.sum(axis=-1) == 3)
    quad = np.argwhere(valid)
    corners = np.stack((xy[:-1, :-1], xy[:-1, 1:],
                        xy[1:, 1:], xy[1:, :-1]), axis=-2)[valid]
    node_offsets = np.array([[0, 0], [0, 1], [1, 1], [1, 0]], dtype=int)
    wetv = v[valid]
    tri_xyz = corners[wetv].reshape(-1, 3, 2)
    vertex_ij = (quad[:, None, :] + node_offsets[None, :, :])[wetv].reshape(-1, 3, 2)
    centroids = tri_xyz.mean(axis=1)
    radius = float(np.max(np.linalg.norm(tri_xyz-centroids[:, None, :],axis=2))) if len(quad) else 0.0
    return tri_xyz, vertex_ij, centroids, radius


def _barycentric(triangle: np.ndarray, point: np.ndarray) -> np.ndarray | None:
    """Signed projected barycentric weights; reject degenerate geometry."""
    edges = np.column_stack((triangle[0]-triangle[2],
                             triangle[1]-triangle[2]))
    det = float(np.linalg.det(edges))
    scale = float(np.max(np.linalg.norm(triangle[1:]-triangle[0], axis=1)))
    if scale < 1e-6 or abs(det) < 1e-9 * scale * scale:
        return None
    uv = np.linalg.solve(edges, point-triangle[2])
    w = np.array([uv[0], uv[1], 1.0-uv.sum()], dtype=float)
    if w.min() < -1e-10 or w.max() > 1 + 1e-10:
        return None
    w = np.maximum(w, 0.)
    return w / w.sum()


def _shoreline_parts(gshhg_base: Path, bbox: BoundingBox, *, resolution: str):
    cfg={"dataset":"GSHHG", "version":"2.3.7",
         "base_dir":str(gshhg_base),"default_resolution":resolution,"level":1}
    coast=load_shoreline_geometry(cfg,bbox,resolution=resolution,level=1)
    parts=[]
    for record in coast.records:
        for p in record.parts:
            lo=np.min(p,axis=0)
            hi=np.max(p,axis=0)
            parts.append((np.array([lo[0],lo[1],hi[0],hi[1]],dtype=float),p))
    return parts,coast


def _crosses_coast(triangle_lonlat: np.ndarray, coast_parts: list) -> bool:
    """True on *any* shoreline intersection; reject even a coastline touch."""
    tri=Polygon(triangle_lonlat)
    xmin,ymin,xmax,ymax=tri.bounds
    for bounds,coords in coast_parts:
        if (bounds[2] < xmin or bounds[0] > xmax or
                bounds[3] < ymin or bounds[1] > ymax):
            continue
        if LineString(coords).intersects(tri):
            return True
    return False


def classify_points(parent_xy: np.ndarray, parent_lonlat: np.ndarray,
                    parent_wet: np.ndarray, target_xy: np.ndarray,
                    target_lonlat: np.ndarray, coastline_parts: list) -> list[dict]:
    """Classify target geometries; no fallback if no enclosing coastal triangle."""
    if parent_xy.shape != parent_lonlat.shape:
        raise ValueError("inconsistent parent projected/geographic grid")
    targets=np.asarray(target_xy,dtype=float)
    lo=np.asarray(target_lonlat,dtype=float)
    tri_xyz,tri_nodes,centers,radius=_candidate_index(parent_xy,np.asarray(parent_wet,dtype=bool))
    tree=cKDTree(centers) if len(centers) else None
    out=[]
    for p,geo in zip(targets,lo):
        candidates=[]
        if tree is not None:
            nearby=tree.query_ball_point(p,np.nextafter(radius,np.inf))
            for q in nearby:
                weight=_barycentric(tri_xyz[q],p)
                if weight is None:
                    continue
                nodes=tri_nodes[q]
                corners=parent_lonlat[nodes[:,0],nodes[:,1]]
                distances=np.linalg.norm(tri_xyz[q]-p[None,:],axis=1)
                if max(distances) > 2.5*max(
                        np.linalg.norm(tri_xyz[q][1]-tri_xyz[q][0]),
                        np.linalg.norm(tri_xyz[q][2]-tri_xyz[q][0]),
                        np.linalg.norm(tri_xyz[q][2]-tri_xyz[q][1])):
                    continue
                coast_hit=_crosses_coast(corners,coastline_parts)
                candidates.append({
                    "donor_eta_xi_zero_based":nodes.astype(int).tolist(),
                    "donor_lonlat":corners.astype(float).tolist(),
                    "weights":weight.astype(float).tolist(),
                    "sum_weights":float(weight.sum()),
                    "min_weight":float(weight.min()),
                    "max_donor_distance_m":float(max(distances)),
                    "coastline_intersection":bool(coast_hit),
                    "same_parent_2x2_three_wet_vertices":True,
                    "parent_wet_four_neighbor_connected_within_quad":True,
                })
        candidates.sort(key=lambda v:v["max_donor_distance_m"])
        safe=[q for q in candidates if not q["coastline_intersection"]]
        if safe:
            status="COASTLINE_CLEAR_LOCAL_TRIANGLE_STATIC_CANDIDATE"
            chosen=safe[0]
        elif candidates:
            status="ENCLS_THREE_WET_TRIANGLE_BUT_CROSSES_GSHHG_L1_COAST"
            chosen=candidates[0]
        else:
            status="NO_ENCLOSING_LOCAL_THREE_WET_PARENT_RHO_TRIANGLE"
            chosen=None
        out.append({"status":status, "candidate_count":len(candidates),
                    "no_coastline_intersection_candidate_count":len(safe),
                    "best_candidate":chosen})
    return out


def review_current(parent_grid: Path, child_grid: Path, preflight: Path,
                   gshhg_base: Path, *, resolution: str = "h") -> dict:
    """Accept exactly the real-current-UD1K previously audited uncovered list."""
    with Dataset(parent_grid) as f:
        p_lon=np.asarray(f["lon_rho"][:])
        p_lat=np.asarray(f["lat_rho"][:])
        wet=np.asarray(f["mask_rho"][:],dtype=bool)
        if str(f.getncattr("grid_id"))!="ES3K":
            raise ValueError("parent must be ES3K")
    with Dataset(child_grid) as f:
        c_lon=np.asarray(f["lon_rho"][:])
        c_lat=np.asarray(f["lat_rho"][:])
        c_wet=np.asarray(f["mask_rho"][:],dtype=bool)
        if str(f.getncattr("grid_id"))!="UD1K":
            raise ValueError("child must be UD1K")
    base=json.loads(Path(preflight).read_text())
    audit=base["full_wet_parent_quad_stencil"]
    points=audit["uncovered_sample_ij_lonlat"]
    if not (len(points)==audit["without_full_wet_parent_rho_quad"]==27 and
            list(c_wet.shape)==[290,438] and base["wet_boundary_points_checked"]==1017):
        raise ValueError("unexpected source preflight; refuse to mix UD1K domains")
    ll=[];ijk=[]
    for point in points:
        j=int(point["eta_rho_zero_based"]);i=int(point["xi_rho_zero_based"])
        if not (0<=j<c_wet.shape[0] and 0<=i<c_wet.shape[1]
                and (j in (0,c_wet.shape[0]-1) or i in (0,c_wet.shape[1]-1))
                and c_wet[j,i]):
            raise ValueError("preflight indexed dry or interior RHO point")
        if abs(c_lon[j,i]-point["lon"])>1e-9 or abs(c_lat[j,i]-point["lat"])>1e-9:
            raise ValueError("preflight longitude/latitude drift")
        ll.append((point["lon"],point["lat"]));ijk.append((j,i))
    lo=np.asarray(ll,dtype=float)
    crs=CRS.from_proj4(f"+proj=aeqd +lat_0={float(p_lat.mean())} +lon_0={float(p_lon.mean())} +datum=WGS84 +units=m +no_defs")
    tr=Transformer.from_crs("EPSG:4326",crs,always_xy=True)
    px,py=tr.transform(p_lon,p_lat)
    tx,ty=tr.transform(lo[:,0],lo[:,1])
    parent_xy=np.stack((px,py),axis=-1)
    bbox=BoundingBox(float(lo[:,0].min()-.15),float(lo[:,0].max()+.15),
                     float(lo[:,1].min()-.15),float(lo[:,1].max()+.15))
    shoreline,meta=_shoreline_parts(Path(gshhg_base),bbox,resolution=resolution)
    if not shoreline:
        raise ValueError("GSHHG shoreline source returned no Level1 polygons")
    classifications=classify_points(parent_xy,np.stack((p_lon,p_lat),axis=-1),
                                    wet,np.column_stack((tx,ty)),lo,shoreline)
    records=[{"child_eta_rho_zero_based":int(j),"child_xi_rho_zero_based":int(i),
              "child_lon":float(lon),"child_lat":float(lat),**status}
             for (j,i),(lon,lat),status in zip(ijk,ll,classifications)]
    keys=["COASTLINE_CLEAR_LOCAL_TRIANGLE_STATIC_CANDIDATE",
          "ENCLS_THREE_WET_TRIANGLE_BUT_CROSSES_GSHHG_L1_COAST",
          "NO_ENCLOSING_LOCAL_THREE_WET_PARENT_RHO_TRIANGLE"]
    counts={k:sum(x["status"]==k for x in records) for k in keys}
    assert sum(counts.values())==27
    return {
        "scope":"ONLY_27_CURRENT_UD1K_PRELIMINARY_RHO_COASTAL_STENCIL_GAPS",
        "method":"SINGLE_PARENT_2x2_QUAD_EXACT_THREE_WET_VERTICES_AND_BARYCENTRIC_ENCLOSURE",
        "source_parent":Path(parent_grid).name,
        "source_child":Path(child_grid).name,
        "GSHHG":"2.3.7_L1_"+resolution,
        "GSHHG_shapefile_path":str(meta.shapefile_path),
        "GSHHG_coastline_parts_loaded":len(shoreline),
        "GSHHG_bounding_box_wsen":[bbox.west,bbox.south,bbox.east,bbox.north],
        "status_counts":counts,
        "records":records,
        "disposition":"GEOMETRY_AND_COASTLINE_PREFLIGHT_ONLY",
        "caveats":["Does not search triangles composed from arbitrary non-adjacent wet donors.",
                   "No local triangle is NOT proof of a fundamentally unresolvable waterway.",
                   "Coastline-clear is necessary but not sufficient for physically valid ROMS bry.nc.",
                   "RHO only; U/V staggering, sigma vertical remapping and normal flux NOT_RUN."],
        "physical_validation":"NOT_RUN",
        "source_masks_modified":False,
    }
