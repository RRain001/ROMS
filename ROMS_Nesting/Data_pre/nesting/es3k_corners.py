"""I2 ES3K *diagnostic* four-corner curvilinear candidate geometry.

Preserves the user's precise W,N,E,S RHO corner coordinates. Builds a
bilinear transfinite interpolation in a local AEQD metric chart, then
uses independent WGS84 geodesics for ROMS metric/angle diagnostics.
This is the **first geometry candidate only**: four arbitrary corners
need not admit a 1-degree orthogonal map; the production I3 gate must
FAIL CLOSED until a boundary-aware elliptic grid/physical masks pass.

The target 1/36 degree is treated as a local longitude/latitude
METRIC-EQUIVALENT sampling target; DO NOT label these grid cells exactly
1/36 degree in an unverified rotated angular coordinate system.
"""
from __future__ import annotations

import numpy as np
from pyproj import CRS, Geod, Transformer

WGS84=Geod(ellps="WGS84")
KEYS=("W","N","E","S")
DEFAULT_MAX_RHO=900_000


def user_corner_inputs(spec: dict) -> dict[str, tuple[float,float]]:
    if spec.get("grid_id")!="ES3K":
        raise ValueError("four-corner generator only accepts ES3K")
    if spec.get("geometry_type")!="four_corner_transfinite_aeqd_candidate":
        raise ValueError("expected four_corner_transfinite_aeqd_candidate geometry")
    if abs(float(spec.get("nominal_resolution_deg",-1))-1/36)>1e-12:
        raise ValueError("ES3K nominal resolution must be 1/36 degree")
    raw=spec.get("user_corners_lat_lon")
    if not isinstance(raw,dict) or set(raw)!=set(KEYS):
        raise ValueError("ES3K W N E S corners required")
    points:dict[str,tuple[float,float]]={}
    for key in KEYS:
        pair=raw[key]
        if not isinstance(pair,(list,tuple)) or len(pair)!=2:
            raise ValueError(f"ES3K {key} latitude/longitude pair invalid")
        lat,lon=float(pair[0]),float(pair[1])
        if not (np.isfinite(lat) and np.isfinite(lon)
                and 20<lat<60 and 115<lon<160):
            raise ValueError(f"ES3K {key} outside accepted Japan Sea vicinity")
        points[key]=(lat,lon)
    # Fail closed if the submitted spec differs from the authoritative
    # four vertices, while still allowing downsampled test builds.
    expected={"W":(37.821077,121.9),
              "N":(52.,141.327943),
              "E":(45.616255,150.4),
              "S":(30.8,131.471973)}
    if points!=expected:
        raise ValueError("ES3K user-supplied corners have changed; do not silently move domain")
    return points


def corner_grid(spec:dict, *,
                sample_scale:int=1
               ) -> tuple[dict[str,np.ndarray],float,float,dict]:
    """Make W→S as positive xi; W→N as positive eta.

    sample_scale>1 gives a cheap coarse geometric diagnostic and is
    NEVER an accepted-resolution scientific grid. Actual rho point
    counts are derived from adjacent WGS84 edge lengths and nominal
    1/36 degree local metric equivalents, not from image pixels.
    """
    corners=user_corner_inputs(spec)
    if not isinstance(sample_scale,int) or sample_scale<1:
        raise ValueError("sample_scale must be a positive integer")
    latc=float(np.mean([v[0] for v in corners.values()]))
    lonc=float(np.mean([v[1] for v in corners.values()]))
    chart=CRS.from_proj4(
        f"+proj=aeqd +lat_0={latc} +lon_0={lonc} +datum=WGS84 +units=m +no_defs")
    tf=Transformer.from_crs("EPSG:4326",chart,always_xy=True)
    back=Transformer.from_crs(chart,"EPSG:4326",always_xy=True)
    xy={k:np.asarray(tf.transform(lon,lat),dtype=float)
        for k,(lat,lon) in corners.items()}
    def edge(a,b):
        return float(WGS84.inv(corners[a][1],corners[a][0],
                               corners[b][1],corners[b][0])[2])
    step=1/36
    _,_,dx_target=WGS84.inv(lonc,latc,lonc+step,latc)
    _,_,dy_target=WGS84.inv(lonc,latc,lonc,latc+step)
    Lxi=(edge("W","S")+edge("N","E"))/2
    Leta=(edge("W","N")+edge("S","E"))/2
    intervals_xi=max(4,int(round(Lxi/dx_target)))
    intervals_eta=max(4,int(round(Leta/dy_target)))
    nx=max(4,int(round(intervals_xi/sample_scale)))
    ny=max(4,int(round(intervals_eta/sample_scale)))
    max_rho=int(spec.get("max_rho_points",DEFAULT_MAX_RHO))
    if (ny+1)*(nx+1)>max_rho:
        raise ValueError("ES3K candidate too many rho points, use sample_scale or audit memory")
    # Non-collapsing convex projected quadrilateral check.
    area_sign=[]
    for a,b,c in (("W","S","E"),("S","E","N"),("E","N","W"),("N","W","S")):
        ab=xy[b]-xy[a];ac=xy[c]-xy[a]
        area_sign.append(float(np.linalg.det(np.stack((ab,ac),axis=1))))
    if not (all(v>0 for v in area_sign) or all(v<0 for v in area_sign)):
        raise ValueError("ES3K projected perimeter non-convex/self-intersecting")
    output={}
    for kind,(iy,ix,eta_offset,xi_offset) in {
        "rho":(ny+1,nx+1,0,0),
        "u":(ny+1,nx,0,.5),
        "v":(ny,nx+1,.5,0),
        "psi":(ny,nx,.5,.5),
    }.items():
        eta=((np.arange(iy)+eta_offset)/ny)[:,None,None]
        xi=((np.arange(ix)+xi_offset)/nx)[None,:,None]
        # Convex projected bilinear map: corners are kept EXACTLY fixed.
        coords=((1-xi)*(1-eta)*xy["W"]+
                xi*(1-eta)*xy["S"]+
                (1-xi)*eta*xy["N"]+
                xi*eta*xy["E"])
        lon,lat=back.transform(coords[:,:,0],coords[:,:,1])
        output["x_"+kind]=coords[:,:,0]
        output["y_"+kind]=coords[:,:,1]
        output["lon_"+kind]=np.asarray(lon,dtype=float)
        output["lat_"+kind]=np.asarray(lat,dtype=float)
    from grid_metrics import compute_grid_metrics
    output.update(compute_grid_metrics(output["lon_rho"],output["lat_rho"]))
    output["f"]=2*7.2921159e-5*np.sin(np.deg2rad(output["lat_rho"]))
    lon,lat=output["lon_rho"],output["lat_rho"]
    az_xi,_,_=WGS84.inv(lon[:,:-1],lat[:,:-1],lon[:,1:],lat[:,1:])
    az_eta,_,_=WGS84.inv(lon[:-1,:],lat[:-1,:],lon[1:,:],lat[1:,:])
    angle=np.empty(lon.shape,dtype=float)
    angle[:,:-1]=np.deg2rad(90-np.asarray(az_xi))
    angle[:,-1]=angle[:,-2]
    output["angle"]=np.arctan2(np.sin(angle),np.cos(angle))
    # Independent WGS84 directional comparison at every valid cell.
    theta_xi=np.deg2rad(90-np.asarray(az_xi[:-1,:]))
    theta_eta=np.deg2rad(90-np.asarray(az_eta[:,:-1]))
    err=np.rad2deg(np.arcsin(np.clip(
        np.abs(np.cos(theta_xi-theta_eta)),0,1)))
    # Physical grid spacings, NOT constant 1/36-degree.
    dx=1/output["pm"]
    dy=1/output["pn"]
    corner_map={"W":(0,0),"N":(-1,0),
                "E":(-1,-1),"S":(0,-1)}
    max_corner_error=0.0
    for k,(row,col) in corner_map.items():
        lt,ln=corners[k]
        d=WGS84.inv(ln,lt,lon[row,col],lat[row,col])[2]
        max_corner_error=max(max_corner_error,float(d))
    report={
        "status":"GEOMETRY_CANDIDATE_NOT_VALIDATED",
        "method":"WGS84_AEQD_BILINEAR_TRANSFINITE_V1",
        "boundaries":"FIXED_USER_FOUR_CORNERS",
        "nominal_angular_spacing":"1/36 degree",
        "sampling_interpretation":"LOCAL_METRIC_EQUIVALENT_NOT_EXACT_ANGULAR",
        "sample_scale":sample_scale,
        "full_estimated_rho_shape":[intervals_eta+1,intervals_xi+1],
        "actual_rho_shape":[ny+1,nx+1],
        "corner_max_wgs84_error_m":max_corner_error,
        "orthogonality_gate":"NOT_PASS" if float(err.max())>1.0 else "PRELIMINARY_PASS_ONLY",
        "orthogonality_threshold_deg":1.0,
        "orthogonality_error_max_deg":float(err.max()),
        "orthogonality_error_p95_deg":float(np.quantile(err,.95)),
        "orthogonality_error_mean_deg":float(err.mean()),
        "geodesic_dx_min_m":float(dx.min()),
        "geodesic_dx_max_m":float(dx.max()),
        "geodesic_dy_min_m":float(dy.min()),
        "geodesic_dy_max_m":float(dy.max()),
        "nominal_local_dx_m":float(dx_target),
        "nominal_local_dy_m":float(dy_target),
        "corner_input_lat_lon":{k:list(corners[k]) for k in KEYS},
        "parent_child_wet_coverage":"NOT_RUN",
        "geographical_shoreline":"NOT_RUN",
        "ROMS_integration":"NOT_RUN",
    }
    return output,float(dx_target)*sample_scale,float(dy_target)*sample_scale,report
