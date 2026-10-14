"""Conformal four-corner ES3K diagnostic in ellipsoidal WGS84 LCC.

Complex holomorphic polynomial maps the corners of a logical rectangle
to the user's exact four corners in a WGS84 Lambert conformal conic map.
Unlike bilinear transfinite interpolation, its *projected* coordinate
curves are orthogonal. Geodesic ROMS cell orthogonality, injectivity,
perimeter containment, and scale variations are audited independently.

An acceptable orthogonality diagnostic DOES NOT validate a science grid:
edges necessarily curve, 1/36 degree is local-metric *nominal* only,
GEBCO/GSHHG masks and hydrodynamics are NOT RUN.
"""
from __future__ import annotations

from math import isfinite
import numpy as np
from pyproj import CRS, Geod, Transformer
from shapely.geometry import Polygon

from es3k_corners import user_corner_inputs

WGS84=Geod(ellps="WGS84")


def conformal_corner_grid(spec:dict, *, sample_scale:int=1
                         )->tuple[dict[str,np.ndarray],float,float,dict]:
    corners=user_corner_inputs({**spec,
         "geometry_type":"four_corner_transfinite_aeqd_candidate"})
    if spec.get("geometry_type")!="four_corner_conformal_lcc_candidate":
        raise ValueError("expected four_corner_conformal_lcc_candidate geometry")
    if not isinstance(sample_scale,int) or isinstance(sample_scale,bool) or sample_scale<1:
        raise ValueError("sample_scale must be positive integer")
    aspect=float(spec.get("logical_rectangle_aspect",2.1))
    if not isfinite(aspect) or not 1.5<=aspect<=3.5:
        raise ValueError("logical_rectangle_aspect outside tested 1.5–3.5")
    lon0=float(np.mean([v[1] for v in corners.values()]))
    lat0=float(np.mean([v[0] for v in corners.values()]))
    proj=CRS.from_proj4(
        f"+proj=lcc +lat_1=35 +lat_2=50 +lat_0={lat0} "
        f"+lon_0={lon0} +datum=WGS84 +units=m +no_defs")
    forward=Transformer.from_crs("EPSG:4326",proj,always_xy=True)
    inverse=Transformer.from_crs(proj,"EPSG:4326",always_xy=True)
    complex_corner={}
    for key,(lat,lon) in corners.items():
        x,y=forward.transform(lon,lat)
        complex_corner[key]=complex(float(x),float(y))
    z_src=np.array([0+0j,1+0j,1+1j*aspect,1j*aspect])
    z_dst=np.array([complex_corner[k] for k in ("W","S","E","N")])
    # Unique cubic holomorphic interpolant; same source coordinates
    # feed RHO/U/V/PSI to maintain C-grid consistency.
    coeff=np.polynomial.polynomial.polyfit(z_src,z_dst,3)
    derivative=np.polynomial.polynomial.polyder(coeff)
    def edge(k1,k2):
        a,b=corners[k1],corners[k2]
        return float(WGS84.inv(a[1],a[0],b[1],b[0])[2])
    step=1/36
    _,_,dx_nom=WGS84.inv(lon0,lat0,lon0+step,lat0)
    _,_,dy_nom=WGS84.inv(lon0,lat0,lon0,lat0+step)
    xi_len=(edge("W","S")+edge("N","E"))/2
    eta_len=(edge("W","N")+edge("S","E"))/2
    nxi_full=max(4,int(round(xi_len/dx_nom)))
    neta_full=max(4,int(round(eta_len/dy_nom)))
    nxi=max(4,int(round(nxi_full/sample_scale)))
    neta=max(4,int(round(neta_full/sample_scale)))
    if (nxi+1)*(neta+1)>int(spec.get("max_rho_points",900000)):
        raise ValueError("ES3K conformal grid exceeds candidate rho memory ceiling")
    output={}
    for suffix,(count_eta,count_xi,shift_eta,shift_xi) in {
        "rho":(neta+1,nxi+1,0,0),
        "u":(neta+1,nxi,0,.5),
        "v":(neta,nxi+1,.5,0),
        "psi":(neta,nxi,.5,.5),
    }.items():
        eta=(np.arange(count_eta,dtype=float)+shift_eta)/neta
        xi=(np.arange(count_xi,dtype=float)+shift_xi)/nxi
        w=xi[None,:]+1j*aspect*eta[:,None]
        z=np.polynomial.polynomial.polyval(w,coeff)
        x,y=z.real,z.imag
        lon,lat=inverse.transform(x,y)
        output["x_"+suffix]=np.asarray(x)
        output["y_"+suffix]=np.asarray(y)
        output["lon_"+suffix]=np.asarray(lon)
        output["lat_"+suffix]=np.asarray(lat)
    lon,lat=output["lon_rho"],output["lat_rho"]
    # Check both local conformal orientation and finite element topology.
    w_full=np.linspace(0,1,nxi+1)[None,:]+1j*aspect*np.linspace(0,1,neta+1)[:,None]
    dz=np.polynomial.polynomial.polyval(w_full,derivative)
    min_deriv=float(np.min(np.abs(dz)))
    if min_deriv<1e-9 or not np.isfinite(min_deriv):
        raise ValueError("conformal polynomial derivative vanishes on grid")
    x,y=output["x_rho"],output["y_rho"]
    e_x=np.diff(x,axis=1)
    e_y=np.diff(y,axis=1)
    n_x=np.diff(x,axis=0)
    n_y=np.diff(y,axis=0)
    det=e_x[:-1]*n_y[:,:-1]-e_y[:-1]*n_x[:,:-1]
    if not (np.isfinite(det).all() and (det>0).all()):
        raise ValueError("conformal candidate contains inverted/degenerate cells")
    ring=np.vstack((
        np.column_stack((x[0],y[0])),
        np.column_stack((x[1:,-1],y[1:,-1])),
        np.column_stack((x[-1,-2::-1],y[-1,-2::-1])),
        np.column_stack((x[-2:0:-1,0],y[-2:0:-1,0]))))
    outline=Polygon(ring)
    if not outline.is_valid or outline.area<=0:
        raise ValueError("ES3K polynomial edge self-intersects")
    from grid_metrics import compute_grid_metrics
    output.update(compute_grid_metrics(lon,lat))
    output["f"]=2*7.2921159e-5*np.sin(np.deg2rad(lat))
    az_xi,_,dx_edges=WGS84.inv(lon[:,:-1],lat[:,:-1],lon[:,1:],lat[:,1:])
    az_eta,_,dy_edges=WGS84.inv(lon[:-1,:],lat[:-1,:],lon[1:,:],lat[1:,:])
    angle=np.empty(lon.shape,dtype=float)
    angle[:,:-1]=np.deg2rad(90-np.asarray(az_xi))
    angle[:,-1]=angle[:,-2]
    output["angle"]=np.arctan2(np.sin(angle),np.cos(angle))
    # A direct *geodetic* orthogonality check, not merely a
    # theoretical conformal claim based on map projection.
    theta=np.deg2rad(az_xi[:-1,:]-az_eta[:,:-1])
    error=np.rad2deg(np.arcsin(np.clip(np.abs(np.cos(theta)),0,1)))
    corner_indices={"W":(0,0),"S":(0,-1),"N":(-1,0),"E":(-1,-1)}
    corner_error={}
    for key,(j,i) in corner_indices.items():
        target_lat,target_lon=corners[key]
        corner_error[key]=float(WGS84.inv(
            lon[j,i],lat[j,i],target_lon,target_lat)[2])
    report={
        "status":"GEOMETRY_CANDIDATE_NOT_VALIDATED",
        "method":"WGS84_LCC_HOLOMORPHIC_CUBIC_FOUR_CORNER_DIAGNOSTIC",
        "geometry_type":"four_corner_conformal_lcc_candidate",
        "boundaries":"CURVED_EDGES_FIXED_FOUR_USER_CORNERS",
        "nominal_angular_spacing":"1/36 degree",
        "sampling_interpretation":"LOCAL_METRIC_EQUIVALENT_NOT_EXACT_ANGULAR",
        "logical_rectangle_aspect":aspect,
        "sample_scale":sample_scale,
        "full_estimated_rho_shape":[neta_full+1,nxi_full+1],
        "actual_rho_shape":[neta+1,nxi+1],
        "orthogonality_threshold_deg":1.0,
        "orthogonality_error_max_deg":float(error.max()),
        "orthogonality_error_p95_deg":float(np.quantile(error,.95)),
        "orthogonality_error_mean_deg":float(error.mean()),
        "orthogonality_gate":(
            "PRELIMINARY_PASS_ONLY" if error.max()<=1.0 else "NOT_PASS"),
        "corner_max_wgs84_error_m":max(corner_error.values()),
        "corner_error_m":corner_error,
        "jacobian_min_projected_m2":float(det.min()),
        "jacobian_max_projected_m2":float(det.max()),
        "polynomial_derivative_min_projected_m":min_deriv,
        "polynomial_derivative_max_projected_m":float(np.max(np.abs(dz))),
        "valid_non_self_intersecting_perimeter":True,
        "geodesic_dx_min_m":float(dx_edges.min()),
        "geodesic_dx_max_m":float(dx_edges.max()),
        "geodesic_dy_min_m":float(dy_edges.min()),
        "geodesic_dy_max_m":float(dy_edges.max()),
        "nominal_local_dx_m":float(dx_nom),
        "nominal_local_dy_m":float(dy_nom),
        "corner_input_lat_lon":{k:list(corners[k]) for k in ("W","N","E","S")},
        "GEBCO_GSHHG":"NOT_RUN",
        "hydrodynamics":"NOT_RUN",
        "ROMS_integration":"NOT_RUN"
    }
    return output,dx_nom*sample_scale,dy_nom*sample_scale,report
