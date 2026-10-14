"""I6 L3 side-anchored offshore square on WGS84.

The *perimeter* is a 48.75-km local AEQD planar square, with the user's
two geodetic anchors as EXACT RHO corner coordinates. Its mesh sampling
uses the local metric equivalents of the NOMINAL 1/324 degree longitude
and latitude increments; it is NOT an exact constant-dlongitude,
constant-dlatitude grid. Distinguish this explicitly in every output.
"""
from __future__ import annotations

from math import ceil, isfinite
import numpy as np
from pyproj import CRS, Geod, Transformer

WGS84 = Geod(ellps="WGS84")
L3 = "L3_300m"
DENOMINATOR = 324


def square_corners(spec: dict) -> dict:
    """Return A,B,C,D with A->B the supplied coastal side and A->D offshore."""
    if spec.get("grid_id") != L3 or spec.get("geometry_type") != "geodesic_square_from_side":
        raise ValueError("expected L3_300m geodesic_square_from_side")
    if spec.get("offshore_side") != "right_of_A_to_B":
        raise ValueError("choose seaward right-hand side of A->B explicitly")
    if abs(float(spec.get("nominal_resolution_deg", -1))-1/DENOMINATOR)>1e-12:
        raise ValueError("L3 nominal resolution must be 1/324 degree")
    a = spec["side_start_A"]
    b = spec["side_end_B"]
    for vertex in (a,b):
        if len(vertex)!=2 or not all(isfinite(float(t)) for t in vertex):
            raise ValueError("side anchors must be finite [latitude,longitude]")
    a_lat,a_lon=map(float,a)
    b_lat,b_lon=map(float,b)
    if not (30<a_lat<42 and 30<b_lat<42 and 124<a_lon<137 and 124<b_lon<137):
        raise ValueError("L3 anchors outside the selected southern Japan Sea region")
    azimuth,_,length=WGS84.inv(a_lon,a_lat,b_lon,b_lat)
    if not (1000<length<200000):
        raise ValueError("implausible L3 coastal side length")
    lon0=(a_lon+b_lon)/2
    lat0=(a_lat+b_lat)/2
    crs=CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m +no_defs")
    forward=Transformer.from_crs("EPSG:4326",crs,always_xy=True)
    reverse=Transformer.from_crs(crs,"EPSG:4326",always_xy=True)
    a_xy=np.asarray(forward.transform(a_lon,a_lat),dtype=np.float64)
    b_xy=np.asarray(forward.transform(b_lon,b_lat),dtype=np.float64)
    eta_step=b_xy-a_xy
    xi_step=np.array([eta_step[1],-eta_step[0]])
    d_xy=a_xy+xi_step
    c_xy=b_xy+xi_step
    c_lon,c_lat=reverse.transform(*c_xy)
    d_lon,d_lat=reverse.transform(*d_xy)
    corners={
        "A":[a_lat,a_lon],
        "B":[b_lat,b_lon],
        "C":[c_lat,c_lon],
        "D":[d_lat,d_lon],
    }
    all_lon=[v[1] for v in corners.values()]
    all_lat=[v[0] for v in corners.values()]
    return {
        "corners_lat_lon":corners,
        "bounds_deg":{"west":min(all_lon),"east":max(all_lon),
                      "south":min(all_lat),"north":max(all_lat)},
        "side_m":float(length),
        "area_local_planar_km2":float(np.dot(eta_step,eta_step)/1e6),
        "azimuth_A_to_B_deg_cw_from_north":float(azimuth),
        "local_proj_crs":crs.to_proj4(),
        "local_origin_lon_lat":[lon0,lat0],
        "xy_A":a_xy,"xy_B":b_xy,"xy_C":c_xy,"xy_D":d_xy,
        "forward":forward,"reverse":reverse,
    }


def square_grid_geometry(spec: dict) -> tuple[dict[str,np.ndarray],float,float,dict]:
    """Actual ROMS staggered C-grid candidate preserving anchored square."""
    from grid_metrics import compute_grid_metrics

    corners=square_corners(spec)
    lat0,lon0=corners["local_origin_lon_lat"][1],corners["local_origin_lon_lat"][0]
    delta=1/DENOMINATOR
    _,_,dx_nom=WGS84.inv(lon0,lat0,lon0+delta,lat0)
    _,_,dy_nom=WGS84.inv(lon0,lat0,lon0,lat0+delta)
    L=corners["side_m"]
    nxi=max(3,int(round(L/dx_nom)))
    neta=max(3,int(round(L/dy_nom)))
    max_points=int(spec.get("max_rho_points",500_000))
    if (nxi+1)*(neta+1)>max_points:
        raise ValueError("L3 rho grid exceeds max_rho_points")
    dx=L/nxi
    dy=L/neta
    a=corners["xy_A"]
    eta=(corners["xy_B"]-a)
    xi=np.array([eta[1],-eta[0]])
    result:dict[str,np.ndarray]={}
    dims={"rho":(neta+1,nxi+1,0,0),
          "u":(neta+1,nxi,0,.5),
          "v":(neta,nxi+1,.5,0),
          "psi":(neta,nxi,.5,.5)}
    for kind,(ny,nx,shift_eta,shift_xi) in dims.items():
        t=(np.arange(ny,dtype=float)+shift_eta)/neta
        s=(np.arange(nx,dtype=float)+shift_xi)/nxi
        xy=a[None,None,:]+t[:,None,None]*eta[None,None,:]+s[None,:,None]*xi[None,None,:]
        xx,yy=xy[...,0],xy[...,1]
        lon,lat=corners["reverse"].transform(xx,yy)
        result["x_"+kind]=xx
        result["y_"+kind]=yy
        result["lon_"+kind]=np.asarray(lon)
        result["lat_"+kind]=np.asarray(lat)
    result.update(compute_grid_metrics(result["lon_rho"],result["lat_rho"]))
    # ROMS angle is from geographic east to positive xi, in radians.
    # Compute azimuth geodesically for each row; the last xi column
    # inherits its nearest valid xi-face angle.
    az_xi,_,_ = WGS84.inv(result["lon_rho"][:,:-1],
                           result["lat_rho"][:,:-1],
                           result["lon_rho"][:,1:],
                           result["lat_rho"][:,1:])
    angle=np.empty(result["lon_rho"].shape,dtype=float)
    angle[:,:-1]=np.deg2rad(90.0-np.asarray(az_xi))
    angle[:,-1]=angle[:,-2]
    result["angle"]=angle
    result["f"]=2*7.2921159e-5*np.sin(np.deg2rad(result["lat_rho"]))

    # Do not claim exact 1/324-degree increments in map coordinates.
    report={
        "grid_id":L3,"geometry_status":"CANDIDATE_APPROXIMATE",
        "perimeter":"WGS84_LOCAL_AEQD_SQUARE_ANCHORED_AB_OFFSHORE",
        "nominal_angular_resolution_fraction":"1/324 deg",
        "nominal_angular_resolution_deg":delta,
        "nominal_vs_actual":"ANGULAR_EQUIVALENT_LOCAL_METRIC_NOT_CONSTANT_DDEG",
        "axis_stagger":"xi_A_to_D_offshore__eta_A_to_B_coast",
        "edge_intervals":{"xi":nxi,"eta":neta},
        "rho_shape":[neta+1,nxi+1],
        "local_nominal_spacing_m":{"xi":float(dx_nom),"eta":float(dy_nom)},
        "actual_projected_spacing_m":{"xi":float(dx),"eta":float(dy)},
        "relative_spacing_deviation":{
            "xi":float(dx/dx_nom-1),"eta":float(dy/dy_nom-1)},
        "corners_lat_lon":corners["corners_lat_lon"],
        "bounds_deg":corners["bounds_deg"],
        "side_m":L,
        "area_local_planar_km2":corners["area_local_planar_km2"],
        "azimuth_A_to_B_deg_cw_from_north":
            corners["azimuth_A_to_B_deg_cw_from_north"],
        "scientific_validation":"NOT_RUN",
        "GSHHG_shoreline_mask":"NOT_RUN",
        "UD1K_parent_nesting":"NOT_RUN",
    }
    return result,dx,dy,report
