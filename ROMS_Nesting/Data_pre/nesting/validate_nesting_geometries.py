"""I3/I5 independent parent-child grid geometry and wet-interface preflight.

Uses actual curvilinear RHO footprints, not lon/lat bounding boxes.
Geometry PASS is necessary but NOT sufficient for one-way ROMS nesting:
no external barotropic/baroclinic BC, vertical remapping, or flux coupling
is validated here.
"""
from __future__ import annotations

from pathlib import Path
import json

import numpy as np
from netCDF4 import Dataset
from pyproj import CRS,Transformer
from shapely.geometry import Polygon, Point
from scipy.spatial import cKDTree


def _grid(path: Path) -> dict:
    path=Path(path)
    with Dataset(path) as f:
        keys=("lon_rho","lat_rho","mask_rho","pm","pn")
        for key in keys:
            if key not in f.variables:
                raise ValueError(f"{path.name}: missing {key}")
        data={k:np.asarray(f[k][:]) for k in keys}
        data.update(id=str(getattr(f,"grid_id","")),
                    status=str(getattr(f,"geometry_status","UNKNOWN")),
                    synthetic=str(getattr(f,"synthetic_test_only","UNKNOWN")))
    if data["lon_rho"].ndim!=2 or min(data["lon_rho"].shape)<7:
        raise ValueError(f"{path.name}: grid too small for parent/child margins")
    for key in ("lon_rho","lat_rho","mask_rho","pm","pn"):
        if data[key].shape!=data["lon_rho"].shape:
            raise ValueError(f"{path.name}: inconsistent rho field {key}")
    if not (np.isfinite(data["lon_rho"]).all() and
            np.isfinite(data["lat_rho"]).all() and
            np.isfinite(data["pm"]).all() and np.isfinite(data["pn"]).all()):
        raise ValueError(f"{path.name}: nonfinite geometry metrics")
    if not ((data["pm"]>0).all() and (data["pn"]>0).all()):
        raise ValueError(f"{path.name}: invalid metrics")
    if not np.isin(data["mask_rho"],[0,1]).all():
        raise ValueError(f"{path.name}: mask must be binary")
    return data


def _rim(arr: np.ndarray, n: int=0) -> np.ndarray:
    """One continuous perimeter of a logically rectangular rho grid."""
    ny,nx=arr.shape
    if not (0<=n<min(nx,ny)//2):
        raise ValueError("parent interior margin exceeds grid")
    return np.concatenate((arr[n,n:nx-n],arr[n+1:ny-n,nx-n-1],
                           arr[ny-n-1,nx-n-2:n-1:-1] if n>0 else arr[ny-n-1,nx-2::-1],
                           arr[ny-n-2:n:-1,n]))


def _xy(xform: Transformer, lon, lat) -> np.ndarray:
    xx,yy=xform.transform(lon,lat)
    return np.column_stack((xx,yy))



def _full_wet_quad_coverage(parent_xy: np.ndarray, parent_wet: np.ndarray,
                            child_boundary_xy: np.ndarray, *,
                            nearest_quads: int = 16) -> np.ndarray:
    """Diagnostic: boundary points geometrically inside an all-wet parent RHO quad.

    This identifies coastal locations where the nearest wet RHO point is NOT
    enough to construct an ordinary four-corner interpolation stencil. It is
    deliberately *not* a proof of interpolation, conservative flux or
    ROMS boundary-condition readiness.
    """
    xy = np.asarray(parent_xy, dtype=np.float64)
    wet = np.asarray(parent_wet, dtype=bool)
    targets = np.asarray(child_boundary_xy, dtype=np.float64)
    if (xy.ndim != 3 or xy.shape[2] != 2 or xy.shape[:2] != wet.shape
            or targets.ndim != 2 or targets.shape[1] != 2
            or not np.isfinite(xy).all() or not np.isfinite(targets).all()
            or nearest_quads < 1):
        raise ValueError("invalid parent wet quad stencil geometry")
    eligible = (wet[:-1, :-1] & wet[:-1, 1:]
                & wet[1:, :-1] & wet[1:, 1:])
    quads = np.argwhere(eligible)
    covered = np.zeros(len(targets), dtype=bool)
    if not len(quads) or not len(targets):
        return covered
    centers = (xy[:-1, :-1] + xy[:-1, 1:]
               + xy[1:, 1:] + xy[1:, :-1]) / 4.0
    nearest_count = min(nearest_quads, len(quads))
    _, candidate_ids = cKDTree(centers[eligible]).query(
        targets, k=nearest_count)
    candidate_ids = np.asarray(candidate_ids).reshape(len(targets), -1)
    for n, (position, ids) in enumerate(zip(targets, candidate_ids)):
        point = Point(float(position[0]), float(position[1]))
        for quad_id in ids:
            j, i = quads[int(quad_id)]
            corners = (xy[j, i], xy[j, i + 1],
                       xy[j + 1, i + 1], xy[j + 1, i])
            polygon = Polygon(corners)
            if polygon.is_valid and polygon.area > 0 and polygon.covers(point):
                covered[n] = True
                break
    return covered


def check_pair(parent_grid: Path, child_grid: Path, *,
               margin_parent_rho_cells: int=2,
               wet_parent_search_cells: float=2.0) -> dict:
    if margin_parent_rho_cells<1:
        raise ValueError("margin must be >=1 parent rho cells")
    if not (np.isfinite(wet_parent_search_cells) and wet_parent_search_cells>0):
        raise ValueError("wet-parent search radius invalid")
    p=_grid(parent_grid)
    c=_grid(child_grid)
    if (p["id"],c["id"]) not in (("ES3K","UD1K"),("UD1K","L3_300m")):
        raise ValueError("expected ES3K parent and UD1K child OR UD1K parent and L3_300m child")
    if p["status"]!="CANDIDATE_NOT_VALIDATED_FOR_ROMS" or c["status"]!="CANDIDATE_NOT_VALIDATED_FOR_ROMS":
        raise ValueError("only audited I3 candidate grids are supported in this preflight")
    if p["lon_rho"].shape[0]<2*margin_parent_rho_cells+5 or p["lon_rho"].shape[1]<2*margin_parent_rho_cells+5:
        raise ValueError("parent too small for requested interior margin")
    lon0=float(np.mean(p["lon_rho"]))
    lat0=float(np.mean(p["lat_rho"]))
    if not (-180<lon0<180 and -85<lat0<85):
        raise ValueError("parent near unsupported projection pole/dateline")
    crs=CRS.from_proj4(f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m +no_defs")
    tr=Transformer.from_crs("EPSG:4326",crs,always_xy=True)
    plon,plat=_rim(p["lon_rho"],margin_parent_rho_cells),_rim(p["lat_rho"],margin_parent_rho_cells)
    clon,clat=_rim(c["lon_rho"]),_rim(c["lat_rho"])
    inner=Polygon(_xy(tr,plon,plat))
    child=Polygon(_xy(tr,clon,clat))
    if not (inner.is_valid and child.is_valid and inner.area>0 and child.area>0):
        raise ValueError("invalid or self-crossing projected nested grid perimeter")
    is_inside=bool(inner.contains(child))  # strict: no touching buffered rim
    pcell=float(np.median(1.0/np.sqrt(p["pm"]*p["pn"])))
    ccell=float(np.median(1.0/np.sqrt(c["pm"]*c["pn"])))
    if not is_inside:
        return {"status":"FAIL","reason":f'{c["id"]} intersects/outside buffered {p["id"]} footprint',
                "margin_parent_rho_cells":margin_parent_rho_cells,
                "parent_grid_id":p["id"],"child_grid_id":c["id"],
                "distance_to_buffered_parent_m":0.0,
                "resolution_ratio":pcell/ccell,
                "physical_nesting":"NOT_RUN"}
    from shapely.geometry import Point
    # Child footprint is within the parent; report *minimum* distance
    # from child polygon to buffered parent ring (not a proof of flux).
    gap=float(inner.boundary.distance(child))
    if gap<=0:
        raise ValueError("child touches parent buffered perimeter")
    child_wet=c["mask_rho"].astype(bool)
    # Only wet child perimeter cells require parent wet coverage.
    boundary=np.zeros(child_wet.shape,bool)
    boundary[[0,-1],:]=True
    boundary[:,[0,-1]]=True
    wet_boundary=boundary & child_wet
    if not wet_boundary.any():
        raise ValueError("UD1K has no open-water wet boundary cells")
    wet_parent=p["mask_rho"].astype(bool)
    if not wet_parent.any():
        raise ValueError("ES3K has no wet cells")
    pwet=_xy(tr,p["lon_rho"][wet_parent],p["lat_rho"][wet_parent])
    cwet=_xy(tr,c["lon_rho"][wet_boundary],c["lat_rho"][wet_boundary])
    distance,_=cKDTree(pwet).query(cwet,k=1)
    distance=np.asarray(distance)
    max_gap=float(np.max(distance))
    wet_coverage=bool(np.all(distance<=wet_parent_search_cells*pcell))
    parent_xy = _xy(tr, p["lon_rho"].ravel(), p["lat_rho"].ravel()).reshape(
        (*wet_parent.shape, 2))
    full_quad = _full_wet_quad_coverage(parent_xy, wet_parent, cwet)
    first_missing = np.flatnonzero(~full_quad)[:12]
    stencil_diagnostic = {
        "method": "PROJECTED_ALL_FOUR_WET_PARENT_RHO_QUAD_CONTAINS_CHILD_POINT",
        "candidate_nearest_quads": 16,
        "child_wet_boundary_rho_points": int(len(full_quad)),
        "with_full_wet_parent_rho_quad": int(full_quad.sum()),
        "without_full_wet_parent_rho_quad": int((~full_quad).sum()),
        "fraction_with_full_wet_quad": float(full_quad.mean()),
        "first_uncovered_lon_lat": [
            [float(c["lon_rho"][wet_boundary][i]),
             float(c["lat_rho"][wet_boundary][i])] for i in first_missing
        ],
        "disposition": ("FULL_WET_RHO_QUAD_DIAGNOSTIC_ONLY"
                        if full_quad.all() else
                        "COASTAL_STENCIL_REVIEW_REQUIRED_NOT_A_PHYSICS_FAILURE"),
        "physical_velocity_rotation_vertical_remap_and_flux": "NOT_RUN",
    }
    return {
        "status":"PASS_PRELIMINARY_ONLY" if wet_coverage else "FAIL",
        "parent_grid_id":p["id"],"child_grid_id":c["id"],
        "reason":"preflight footprint and parent wet coverage" if wet_coverage else "child wet boundary lacks nearby parent wet cells",
        "margin_parent_rho_cells":margin_parent_rho_cells,
        "buffered_parent_boundary_gap_min_m":gap,
        "wet_boundary_points_checked":int(wet_boundary.sum()),
        "farthest_nearest_parent_wet_m":max_gap,
        "full_wet_parent_quad_stencil":stencil_diagnostic,
        "wet_parent_search_cells":wet_parent_search_cells,
        "parent_nominal_cell_m":pcell,
        "child_nominal_cell_m":ccell,
        "resolution_ratio":pcell/ccell,
        "parent_synthetic":p["synthetic"],
        "child_synthetic":c["synthetic"],
        "physics_validation":"NOT_RUN",
        "vertical_remapping":"NOT_RUN",
        "conservative_boundary_fluxes":"NOT_RUN",
    }
