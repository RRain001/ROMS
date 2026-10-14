"""I3 *candidate* ROMS grids from rectilinear GEBCO + optional real GSHHG.

Independent nesting-only grid construction. Output is NEVER an accepted
ES3K/UD1K scientific grid without externally audited geometry,
shoreline correction, smoothing, and ROMS spin-up.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import label as connected_components
from pyproj import Geod

from rotated_grid import RotatedGridSpec, create_geometry, geodesic_quality

_CORE = Path(__file__).resolve().parents[1] / "core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))
from grid_metrics import compute_grid_metrics, METHOD

WGS84 = Geod(ellps="WGS84")
KINDS = ("rho", "u", "v", "psi")
SHAPES = {
    "rho": ("eta_rho", "xi_rho"),
    "u": ("eta_u", "xi_u"),
    "v": ("eta_v", "xi_v"),
    "psi": ("eta_psi", "xi_psi"),
}
NESTING_ONLY = "CANDIDATE_NOT_VALIDATED_FOR_ROMS"


def _float_finite(value: object, name: str) -> float:
    if value is None:
        raise ValueError(f"{name} must be provided explicitly; no inferred Kim-2020 corners")
    x = float(value)
    if not np.isfinite(x):
        raise ValueError(f"{name} must be finite")
    return x


def make_geometry(spec: dict) -> tuple[dict[str, np.ndarray], float, float]:
    """One explicit candidate specification; no implicit real ES3K corners."""
    typ = spec.get("geometry_type")
    if typ == "rotated_lcc":
        if spec.get("grid_id") != "ES3K":
            raise ValueError("rotated_lcc candidate currently reserved for ES3K")
        req = ("center_lon", "center_lat", "width_points",
               "height_points", "dx_m", "dy_m", "angle_deg")
        for k in req:
            _float_finite(spec.get(k), k)
        rotated = RotatedGridSpec(
            center_lon=float(spec["center_lon"]),
            center_lat=float(spec["center_lat"]),
            width_points=int(spec["width_points"]),
            height_points=int(spec["height_points"]),
            dx_m=float(spec["dx_m"]), dy_m=float(spec["dy_m"]),
            angle_deg=float(spec["angle_deg"]),
            std_parallel_south_deg=spec.get("std_parallel_south_deg"),
            std_parallel_north_deg=spec.get("std_parallel_north_deg"),
        )
        if rotated.width_points != float(spec["width_points"]) or rotated.height_points != float(spec["height_points"]):
            raise ValueError("rho point counts must be integers")
        result = create_geometry(rotated)
        return result, rotated.dx_m, rotated.dy_m
    if typ == "axis_aligned_lonlat":
        if spec.get("grid_id") != "UD1K":
            raise ValueError("axis_aligned_lonlat candidate currently reserved for UD1K")
        box = [_float_finite(spec.get(k), k) for k in ("lon_min", "lon_max", "lat_min", "lat_max")]
        west, east, south, north = box
        spacing = _float_finite(spec.get("resolution_m"), "resolution_m")
        if not (-180 < west < east <= 180 and -85 < south < north < 85 and spacing > 0):
            raise ValueError("invalid lon/lat bounds or resolution")
        # Latitude/longitude axes are genuinely aligned: angle=0 everywhere.
        midlat = (north + south) / 2
        width = WGS84.inv(west, midlat, east, midlat)[2]
        height = WGS84.inv((west+east)/2, south, (west+east)/2, north)[2]
        nx = max(3, int(np.ceil(width / spacing)) + 1)
        ny = max(3, int(np.ceil(height / spacing)) + 1)
        if nx * ny > int(spec.get("max_rho_points", 2_000_000)):
            raise ValueError("too many rho points; inspect requested domain and spacing")
        lon, lat = np.meshgrid(np.linspace(west, east, nx), np.linspace(south, north, ny))
        result: dict[str, np.ndarray] = {}
        result["lon_rho"], result["lat_rho"] = lon, lat
        # Midpoint coordinates are exact on the straight lat/lon lines.
        for key, lons, lats in (
            ("u", (lon[:, :-1]+lon[:, 1:])/2, lat[:, :-1]),
            ("v", lon[:-1, :], (lat[:-1, :]+lat[1:, :])/2),
            ("psi", (lon[:-1, :-1]+lon[1:, 1:])/2, (lat[:-1, :-1]+lat[1:, 1:])/2),
        ):
            result["lon_"+key], result["lat_"+key] = lons, lats
        for kind in KINDS:
            lo, la = result["lon_"+kind], result["lat_"+kind]
            result["x_"+kind] = (lo - west) / (east-west) * width
            result["y_"+kind] = (la - south) / (north-south) * height
        result.update(compute_grid_metrics(lon,lat))
        result["angle"] = np.zeros(lon.shape)
        result["f"] = 2 * 7.2921159e-5 * np.sin(np.deg2rad(lat))
        return result, spacing, spacing
    raise ValueError("geometry_type must be rotated_lcc or axis_aligned_lonlat")


def _read_bathy(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    with Dataset(path) as nc:
        def var(*names):
            for name in names:
                if name in nc.variables:
                    return name
            raise ValueError(f"bathymetry missing any of {names}")
        lon_key = var("lon", "longitude", "x")
        lat_key = var("lat", "latitude", "y")
        z_key = var("elevation", "z", "bathymetry", "depth", "Band1")
        lon = np.asarray(nc[lon_key][:], dtype=float)
        lat = np.asarray(nc[lat_key][:], dtype=float)
        # GEBCO elevation is often an integer NetCDF variable. Cast the
        # masked array to floating point *before* filling NaN.
        z = np.ma.asarray(nc[z_key][:]).astype(np.float64).filled(np.nan)
    if lon.ndim != 1 or lat.ndim != 1:
        raise ValueError("only rectilinear GEBCO bathymetry supported")
    if z.shape == (lon.size, lat.size) and z.shape != (lat.size, lon.size):
        z = z.T
    if z.shape != (lat.size, lon.size):
        raise ValueError("bathymetry dimensions do not match latitude/longitude")
    if lon[0] > lon[-1]:
        lon, z = lon[::-1], z[:, ::-1]
    if lat[0] > lat[-1]:
        lat, z = lat[::-1], z[::-1, :]
    if not (np.diff(lon)>0).all() or not (np.diff(lat)>0).all():
        raise ValueError("GEBCO coordinate axes must be strictly increasing")
    return lon, lat, z, z_key


def _read_gshhg_land(spec: dict, lon: np.ndarray, lat: np.ndarray, root: Path,
                     resolution: str) -> tuple[np.ndarray, str]:
    # Reuse the existing *copied* GSHHG classifier, not the original main version.
    pre = Path(__file__).resolve().parents[1] / "impl" / "preprocessing"
    if str(pre) not in sys.path:
        sys.path.insert(0, str(pre))
    from shoreline import bbox_from_grid, classify_land_mask, load_shoreline_geometry
    cfg = {
        "dataset": "GSHHG", "version": "2.3.7",
        "base_dir": str(root), "default_resolution": resolution, "level": 1,
    }
    geom = load_shoreline_geometry(cfg, bbox_from_grid(lon, lat), resolution=resolution, level=1)
    land = classify_land_mask(geom, lon, lat)
    return np.asarray(land, dtype=bool), str(geom.shapefile_path)


def build_grid(spec: dict, bathymetry: Path, output: Path, *,
               min_depth_m: float=10.0, gshhg_base: Path | None=None,
               gshhg_resolution: str="h", allow_gebco_only_mask: bool=False,
               synthetic_fixture: bool=False) -> dict:
    """Build C-grid candidate with actual bathy, not default 100-m flat ocean."""
    if min_depth_m <= 0 or not np.isfinite(min_depth_m):
        raise ValueError("min_depth_m must be finite positive")
    if spec.get("geometry_status") != "CANDIDATE_APPROXIMATE":
        raise ValueError("explicit geometry_status=CANDIDATE_APPROXIMATE required")
    grid_id = spec.get("grid_id")
    if grid_id not in ("ES3K", "UD1K"):
        raise ValueError("only the first two grid domains may be built before L3 is defined")
    if gshhg_base is None and not allow_gebco_only_mask:
        raise ValueError("provide --gshhg-base or explicitly enable candidate GEBCO-only mask")
    values, dx, dy = make_geometry(spec)
    lon_grid, lat_grid=values["lon_rho"], values["lat_rho"]
    if not (-180 <= lon_grid.min() <= lon_grid.max() <= 180):
        raise ValueError("grid has longitude outside supported GSHHG range")
    lon, lat, z, zvar = _read_bathy(Path(bathymetry))
    if not (lon[0] <= lon_grid.min() and lon[-1] >= lon_grid.max() and
            lat[0] <= lat_grid.min() and lat[-1] >= lat_grid.max()):
        raise ValueError("GEBCO subset does not cover full physical grid; increase geographic margin")
    z_on_grid = RegularGridInterpolator((lat, lon), z, bounds_error=True)(
        np.column_stack([lat_grid.ravel(), lon_grid.ravel()])
    ).reshape(lon_grid.shape)
    if not np.isfinite(z_on_grid).all():
        raise ValueError("GEBCO interpolation produced missing/nonfinite bathymetry")
    gebco_water = z_on_grid < 0
    if gshhg_base is not None:
        gshhg_land, shp = _read_gshhg_land(spec, lon_grid, lat_grid, gshhg_base, gshhg_resolution)
        water = gebco_water & ~gshhg_land
        shore_status="GSHHG_L1_INTERSECTED_WITH_GEBCO"
    else:
        shp=""
        water=gebco_water
        shore_status="GEBCO_ONLY_SHORELINE_NOT_VALIDATED"
    if not np.any(water):
        raise ValueError("candidate contains no wet rho cells")
    values["h"] = np.where(water, np.maximum(-z_on_grid,min_depth_m), min_depth_m)
    values["mask_rho"] = water.astype("i1")
    values["mask_u"]=(water[:, :-1] & water[:, 1:]).astype("i1")
    values["mask_v"]=(water[:-1, :] & water[1:, :]).astype("i1")
    values["mask_psi"]=(water[:-1, :-1] & water[1:, :-1] & water[:-1, 1:] & water[1:, 1:]).astype("i1")
    quality=geodesic_quality(values,dx,dy)
    # Report rather than silently smooth steep bathymetry.  Source-side
    # GEBCO clipping and island connectivity still require manual review.
    connected, wet_components = connected_components(water)
    h=values["h"]
    wets_x=water[:,:-1] & water[:,1:]
    wets_y=water[:-1,:] & water[1:,:]
    r_x=np.abs(h[:,:-1]-h[:,1:])/(h[:,:-1]+h[:,1:])
    r_y=np.abs(h[:-1,:]-h[1:,:])/(h[:-1,:]+h[1:,:])
    quality["rx0_unsmoothed_wet_max"]=float(max(
        np.max(r_x[wets_x],initial=0),np.max(r_y[wets_y],initial=0)))
    quality["wet_connected_components"]=int(wet_components)
    quality["wet_rho_cells"]=int(water.sum())
    if quality["orthogonality_error_max_deg"] > 1.0:
        raise ValueError("grid orthogonality >1 degree; reject geometry")
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    ny, nx=lon_grid.shape
    sizes={"eta_rho":ny,"xi_rho":nx,"eta_u":ny,"xi_u":nx-1,
           "eta_v":ny-1,"xi_v":nx,"eta_psi":ny-1,"xi_psi":nx-1}
    with Dataset(output,"w",format="NETCDF4") as ds:
        for k,v in sizes.items():
            ds.createDimension(k,v)
        ds.title=f"{grid_id} JAPAN_SEA ROTATED/AXIS candidate grid (NOT ACCEPTED)"
        ds.grid_id=str(grid_id)
        ds.geometry_status=NESTING_ONLY
        ds.geometry_reference_status="KIM_2020_CORNERS_NOT_VERIFIED"
        ds.shoreline_status=shore_status
        ds.shoreline_source=shp or "NOT_APPLIED"
        ds.bathymetry_source=str(bathymetry)
        ds.bathymetry_variable=zvar
        ds.grid_metrics_method=METHOD
        ds.actual_bathymetry_interpolated="TRUE"
        ds.bathymetry_smoothing_status="NOT_RUN"
        ds.synthetic_test_only="TRUE" if synthetic_fixture else "FALSE"
        ds.quality_json=json.dumps(quality,sort_keys=True)
        for name,arr in values.items():
            if name in ("mask_rho","mask_u","mask_v","mask_psi"):
                kind=name.removeprefix("mask_")
                var=ds.createVariable(name,"i1",SHAPES[kind],zlib=True,complevel=1)
            else:
                kind=next((k for k in KINDS if name.endswith("_"+k)),"rho")
                var=ds.createVariable(name,"f8",SHAPES[kind],zlib=True,complevel=1)
            var[:]=arr
            if name=="h": var.units="m"
            if name=="angle": var.units="radian"
            if name in ("pm","pn"): var.units="m-1"
            if name in ("lon_rho","lon_u","lon_v","lon_psi"): var.units="degrees_east"
            if name in ("lat_rho","lat_u","lat_v","lat_psi"): var.units="degrees_north"
        ds.createVariable("spherical","i4").assignValue(1)
        ds.createVariable("xl","f8").assignValue((nx-1)*dx)
        ds.createVariable("el","f8").assignValue((ny-1)*dy)
    return {"status":NESTING_ONLY,"grid_id":grid_id,"output":str(output),
            "rho_shape":[ny,nx],"wet_fraction":float(water.mean()),
            "h_min":float(values["h"].min()),"h_max":float(values["h"].max()),
            "shoreline_status":shore_status,"quality":quality,
            "still_required":["Kim 2020 ES3K geometry provenance","GSHHG/manual mask review",
                              "bathymetry smoothing and rx0/volume checks",
                              "ROMS rotated-grid 1h/6h actual model test",
                              "forcing and parent-child boundary construction"]}
