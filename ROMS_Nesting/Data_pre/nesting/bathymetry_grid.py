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
    if typ == "four_corner_transfinite_aeqd_candidate":
        from es3k_corners import corner_grid
        values, dx, dy, _diagnostics=corner_grid(spec)
        return values, dx, dy
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
    if typ == "geodesic_square_from_side":
        if spec.get("grid_id") != "L3_300m":
            raise ValueError("side-anchored square is reserved for L3_300m")
        from l3_square import square_grid_geometry
        values, dx, dy, metadata = square_grid_geometry(spec)
        return values, dx, dy
    if typ == "axis_aligned_lonlat_angular":
        if spec.get("grid_id") != "UD1K":
            raise ValueError("axis_aligned_lonlat_angular currently reserved for UD1K")
        west, east, south_target, north = [
            _float_finite(spec.get(k),k)
            for k in ("lon_min","lon_max","lat_min","lat_max")]
        step=_float_finite(spec.get("nominal_resolution_deg"),"nominal_resolution_deg")
        if not np.isclose(step,1/108,rtol=0,atol=1e-12):
            raise ValueError("UD1K nominal angular resolution must be 1/108 degree")
        if not (-180<west<east<180 and -85<south_target<north<85):
            raise ValueError("invalid geographic angular grid bounds")
        nx_intervals=int(round((east-west)/step))
        ny_intervals=int(round((north-south_target)/step))
        if nx_intervals<3 or ny_intervals<3:
            raise ValueError("UD1K angular bounds too small")
        if (nx_intervals+1)*(ny_intervals+1)>int(spec.get("max_rho_points",500000)):
            raise ValueError("UD1K angular grid exceeds max_rho_points")
        policy=spec.get("angular_boundary_policy","SNAP_TO_EXACT_ANGULAR_STEP")
        if policy=="PRESERVE_EXACT_USER_BOUNDS_NOMINAL_ANGULAR":
            # Four user-given DMS limits are AUTHORITATIVE. Their span
            # is not an integer multiple of 1/108 degree. Choose the
            # nearest integer cell counts, retain exact four boundaries,
            # and report the actual angular increments rather than
            # secretly shifting the east/south limits.
            lon_axis=np.linspace(west,east,nx_intervals+1,dtype=float)
            lat_axis=np.linspace(south_target,north,ny_intervals+1,dtype=float)
            true_dlon=(east-west)/nx_intervals
            true_dlat=(north-south_target)/ny_intervals
            tolerance=_float_finite(spec.get("max_nominal_spacing_deviation_fraction",0.005),
                                    "max_nominal_spacing_deviation_fraction")
            if tolerance<=0 or tolerance>0.1:
                raise ValueError("invalid maximum nominal angular spacing deviation")
            worst=max(abs(true_dlon/step-1),abs(true_dlat/step-1))
            if worst>tolerance:
                raise ValueError(
                    f"UD1K fixed bounds require {worst:.3%} nominal spacing deviation "
                    f"> allowed {tolerance:.3%}; choose new bounds/counts deliberately")
        elif policy=="SNAP_TO_EXACT_ANGULAR_STEP":
            # Legacy scientific reference geometry mode. The requested
            # east/south limits may shift up to half a cell; never
            # select this mode silently for user-specified exact bounds.
            lon_axis=west+np.arange(nx_intervals+1,dtype=float)*step
            lat_axis=north-ny_intervals*step+np.arange(ny_intervals+1,dtype=float)*step
            if (abs(lon_axis[-1]-east)>step/2+1e-12 or
                abs(lat_axis[0]-south_target)>step/2+1e-12):
                raise ValueError("UD1K anchor snapping changed bounds beyond half a cell")
            true_dlon=true_dlat=step
        else:
            raise ValueError(f"unknown UD1K angular_boundary_policy={policy!r}")
        lon,lat=np.meshgrid(lon_axis,lat_axis)
        result:dict[str,np.ndarray]={"lon_rho":lon,"lat_rho":lat}
        for kind,lons,lats in (
            ("u",(lon[:,:-1]+lon[:,1:])/2,lat[:,:-1]),
            ("v",lon[:-1,:],(lat[:-1,:]+lat[1:,:])/2),
            ("psi",(lon[:-1,:-1]+lon[1:,1:])/2,
                   (lat[:-1,:-1]+lat[1:,1:])/2)):
            result["lon_"+kind],result["lat_"+kind]=lons,lats
        center_lat=float(np.mean(lat_axis))
        center_lon=float(np.mean(lon_axis))
        _,_,dx=WGS84.inv(center_lon,center_lat,center_lon+step,center_lat)
        _,_,dy=WGS84.inv(center_lon,center_lat,center_lon,center_lat+step)
        for kind in KINDS:
            lon_loc,lat_loc=result["lon_"+kind],result["lat_"+kind]
            result["x_"+kind]=(lon_loc-west)/true_dlon*dx
            result["y_"+kind]=(lat_loc-lat_axis[0])/true_dlat*dy
        result.update(compute_grid_metrics(lon,lat))
        # Geographic coordinate axes are unrotated; physical sizes
        # still depend on latitude, as captured in WGS84 pm and pn.
        result["angle"]=np.zeros(lon.shape,dtype=float)
        result["f"]=2*7.2921159e-5*np.sin(np.deg2rad(lat))
        return result,dx,dy
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
    raise ValueError("unknown geometry_type: expected four_corner_transfinite_aeqd_candidate, rotated_lcc, geodesic_square_from_side, or axis_aligned_lonlat[_angular]")


def _source_axis_window(axis: np.ndarray, lower: float, upper: float,
                        label: str) -> tuple[slice, np.ndarray, bool]:
    """Smallest covering file slice plus an interpolation-cell halo.

    Handles GEBCO lat/lon stored in either increasing or decreasing
    coordinate order without allocating/reading the global raster.
    """
    axis=np.asarray(axis,dtype=float)
    if axis.ndim!=1 or axis.size<3 or not np.isfinite(axis).all():
        raise ValueError(f"{label}: source coordinate axis invalid")
    descending=bool(axis[0]>axis[-1])
    ordered=axis[::-1] if descending else axis
    if not (np.diff(ordered)>0).all():
        raise ValueError(f"{label}: source coordinate axis must be strictly monotonic")
    if lower<ordered[0] or upper>ordered[-1]:
        raise ValueError(
            "GEBCO subset does not cover full physical grid; increase geographic margin"
        )
    lo=max(0,int(np.searchsorted(ordered,lower,side="right"))-2)
    hi=min(len(ordered),int(np.searchsorted(ordered,upper,side="left"))+2)
    if hi-lo<2 or ordered[lo]>lower or ordered[hi-1]<upper:
        raise ValueError(f"{label}: insufficient GEBCO interpolation halo")
    if descending:
        original=slice(len(ordered)-hi,len(ordered)-lo)
    else:
        original=slice(lo,hi)
    return original,ordered[lo:hi],descending


def _read_bathy_window(path: Path, target_lon: np.ndarray,
                       target_lat: np.ndarray, *,
                       max_source_cells: int=50_000_000
                       ) -> tuple[np.ndarray,np.ndarray,np.ndarray,str,dict]:
    """Open a global rectilinear GEBCO file but read only a bounded window.

    max_source_cells is a hard guard on the extracted window; a single
    global read from variable[:] must not appear anywhere in this code.
    """
    if max_source_cells<4:
        raise ValueError("max_source_cells must be >=4")
    with Dataset(path) as nc:
        def var(*names):
            for name in names:
                if name in nc.variables:
                    return name
            raise ValueError(f"bathymetry missing any of {names}")
        lon_key=var("lon","longitude","x")
        lat_key=var("lat","latitude","y")
        z_key=var("height_above_mean_sea_level","elevation","z","bathymetry","depth","Band1")
        cvlon=nc[lon_key]
        cvlat=nc[lat_key]
        cvz=nc[z_key]
        if cvlon.ndim!=1 or cvlat.ndim!=1:
            raise ValueError("only rectilinear GEBCO bathymetry supported")
        # Loading longitude/latitude 1-D axes is cheap. The 2-D elevation
        # variable is intentionally never loaded until the cropped slice.
        all_lon=np.asarray(cvlon[:],dtype=np.float64)
        all_lat=np.asarray(cvlat[:],dtype=np.float64)
        if len(cvlon.dimensions)!=1 or len(cvlat.dimensions)!=1:
            raise ValueError("GEBCO coordinate variables must be 1D")
        lon_slice,lon,flip_lon=_source_axis_window(
            all_lon,float(np.min(target_lon)),float(np.max(target_lon)),"longitude")
        lat_slice,lat,flip_lat=_source_axis_window(
            all_lat,float(np.min(target_lat)),float(np.max(target_lat)),"latitude")
        cells=len(lon)*len(lat)
        if cells>max_source_cells:
            raise ValueError(f"GEBCO cropped window {cells} cells exceeds "
                             f"max_source_cells={max_source_cells}; "
                             "stage a smaller source or raise explicit memory bound")
        lon_dim=cvlon.dimensions[0]
        lat_dim=cvlat.dimensions[0]
        if cvz.dimensions==(lat_dim,lon_dim):
            clipped=cvz[lat_slice,lon_slice]
        elif cvz.dimensions==(lon_dim,lat_dim):
            clipped=cvz[lon_slice,lat_slice].T
        else:
            raise ValueError("GEBCO raster dimensions are not latitude/longitude")
        z=np.ma.asarray(clipped).astype(np.float64).filled(np.nan)
        if flip_lon: z=z[:,::-1]
        if flip_lat: z=z[::-1,:]
        if z.shape!=(len(lat),len(lon)):
            raise ValueError("GEBCO cropped raster has unexpected shape")
        provenance={
            "reader":"NETCDF_BOUNDED_WINDOW_V1",
            "original_source_shape":[int(cvz.shape[0]),int(cvz.shape[1])],
            "window_shape":[len(lat),len(lon)],
            "window_cells":int(cells),
            "max_source_cells":int(max_source_cells),
            "longitude_file_slice":[lon_slice.start,lon_slice.stop],
            "latitude_file_slice":[lat_slice.start,lat_slice.stop],
            "source_longitude_descending":flip_lon,
            "source_latitude_descending":flip_lat,
            "data_variable":z_key,
        }
    return lon,lat,z,z_key,provenance


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
               synthetic_fixture: bool=False,
               max_source_cells: int=50_000_000) -> dict:
    """Build C-grid candidate with actual bathy, not default 100-m flat ocean."""
    if min_depth_m <= 0 or not np.isfinite(min_depth_m):
        raise ValueError("min_depth_m must be finite positive")
    if spec.get("geometry_status") != "CANDIDATE_APPROXIMATE":
        raise ValueError("explicit geometry_status=CANDIDATE_APPROXIMATE required")
    grid_id = spec.get("grid_id")
    if grid_id not in ("ES3K", "UD1K","L3_300m"):
        raise ValueError("grid_id must be ES3K, UD1K or L3_300m")
    if gshhg_base is None and not allow_gebco_only_mask:
        raise ValueError("provide --gshhg-base or explicitly enable candidate GEBCO-only mask")
    values, dx, dy = make_geometry(spec)
    # Do not start multi-GB GEBCO I/O for a 4-corner candidate that
    # fails the geometric orthogonality gate on geometry alone.
    if spec.get("geometry_type")=="four_corner_transfinite_aeqd_candidate":
        dry_geometry_quality=geodesic_quality(values,dx,dy)
        if dry_geometry_quality["orthogonality_error_max_deg"]>1.0:
            raise ValueError(
                f"ES3K ROT-GATE NOT PASS, "
                f"max orthogonality error "
                f"{dry_geometry_quality['orthogonality_error_max_deg']:.3f}° "
                f">1°; GEBCO not opened. Improve boundary-aware mesh first."
            )
    lon_grid, lat_grid=values["lon_rho"], values["lat_rho"]
    if not (-180 <= lon_grid.min() <= lon_grid.max() <= 180):
        raise ValueError("grid has longitude outside supported GSHHG range")
    lon, lat, z, zvar, bathy_window = _read_bathy_window(
        Path(bathymetry),lon_grid,lat_grid,max_source_cells=max_source_cells)
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
        raise ValueError(
            f"grid orthogonality {quality['orthogonality_error_max_deg']:.3f} deg >1 degree; "
            "reject production candidate. Diagnostic-only ES3K geometry can "
            "be examined using es3k_corners.corner_grid().")
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
        ds.geometry_reference_status=("USER_ANCHORED_CANDIDATE_NOT_SHORELINE_VERIFIED"
                                      if grid_id=="L3_300m"
                                      else "USER_FOUR_CORNER_BATHY_NOT_VALIDATED"
                                      if spec.get("geometry_type")=="four_corner_transfinite_aeqd_candidate"
                                      else "KIM_2020_CORNERS_NOT_VERIFIED")
        ds.geometry_input_json=json.dumps(spec,sort_keys=True)
        if spec.get("geometry_type")=="axis_aligned_lonlat_angular":
            ds.ud1k_boundary_policy=str(spec.get(
                "angular_boundary_policy","SNAP_TO_EXACT_ANGULAR_STEP"))
            ds.ud1k_actual_lon_step_deg=float(
                (values["lon_rho"][0,-1]-values["lon_rho"][0,0])/
                (values["lon_rho"].shape[1]-1))
            ds.ud1k_actual_lat_step_deg=float(
                (values["lat_rho"][-1,0]-values["lat_rho"][0,0])/
                (values["lat_rho"].shape[0]-1))
            ds.ud1k_nominal_step_deg=float(spec["nominal_resolution_deg"])

        if "nominal_resolution_deg" in spec:
            ds.nominal_resolution_deg=float(spec["nominal_resolution_deg"])
            ds.angular_spacing_claim=(
                "LOCAL_METRIC_EQUIVALENT_NOT_EXACT_ANGULAR" if grid_id=="L3_300m"
                else ("GEOGRAPHIC_EXACT_USER_LIMITS_NOMINAL_1_OVER_108_DEG"
                      if spec.get("angular_boundary_policy")=="PRESERVE_EXACT_USER_BOUNDS_NOMINAL_ANGULAR"
                      else "GEOGRAPHIC_EXACT_1_OVER_108_DEG")
                if spec.get("geometry_type")=="axis_aligned_lonlat_angular"
                else "LOCAL_WGS84_METRIC_EQUIVALENT_NOT_EXACT_ANGULAR"
                if spec.get("geometry_type")=="four_corner_transfinite_aeqd_candidate"
                else "NOT_IMPLEMENTED")
        if grid_id=="L3_300m":
            from l3_square import square_corners
            geometry=square_corners(spec)
            ds.coastal_square_corners_lat_lon=json.dumps(geometry["corners_lat_lon"])
            ds.coastal_square_side_m=float(geometry["side_m"])
        ds.shoreline_status=shore_status
        ds.shoreline_source=shp or "NOT_APPLIED"
        ds.bathymetry_source=str(bathymetry)
        ds.bathymetry_variable=zvar
        ds.bathymetry_source_window=json.dumps(bathy_window,sort_keys=True)
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
            "source_window":bathy_window,
            "still_required":["ES3K Kim 2020 orientation provenance" if grid_id=="ES3K" else
                              "verified parent grid and L3 coastline topology",
                              "GSHHG/manual mask review",
                              "bathymetry smoothing and rx0/volume checks",
                              "ROMS rotated-grid 1h/6h actual model test",
                              "forcing and parent-child boundary construction"]}
