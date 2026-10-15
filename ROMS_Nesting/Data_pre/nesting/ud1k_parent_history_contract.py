"""Fail-closed ROMS ES3K history/grid input contract for future UD1K bry forcing.

Checks the *actual* source grid C-grid shapes/masks, physical sigma
metadata, chronological CF time, and finite input values on wet cells.
Never fabricates a ROMS parent history, projects history onto child, or
declares hydrodynamic acceptance. Synthetic fixtures live in tests only.

Usage:
  python .../ud1k_parent_history_contract.py --grid es3k.nc \
      --history es3k_his.nc --report contract.json

Contract currently supports Vtransform=2/Vstretching=4. Other legitimate
ROMS physics must use a separately reviewed depth-transform implementation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
from netCDF4 import Dataset,num2date

try:
    from ud1k_vertical_flux_primitives import stretching4
except ImportError:
    from .ud1k_vertical_flux_primitives import stretching4

_FIELD_DIMS = {
    "zeta":("ocean_time","eta_rho","xi_rho"),
    "temp":("ocean_time","s_rho","eta_rho","xi_rho"),
    "salt":("ocean_time","s_rho","eta_rho","xi_rho"),
    "u":("ocean_time","s_rho","eta_u","xi_u"),
    "v":("ocean_time","s_rho","eta_v","xi_v"),
    "ubar":("ocean_time","eta_u","xi_u"),
    "vbar":("ocean_time","eta_v","xi_v"),
}
_MASK_FOR={"zeta":"rho","temp":"rho","salt":"rho",
           "u":"u","v":"v","ubar":"u","vbar":"v"}


def _as_float(a)->np.ndarray:
    """Forbid masked/missing data from silently passing as valid zero."""
    return np.asarray(np.ma.filled(np.ma.asarray(a,dtype=np.float64),np.nan),dtype=np.float64)


def _scalar(ds:Dataset,key:str)->float:
    if key in ds.variables:
        v=ds.variables[key]
        if v.ndim!=0:
            raise ValueError(f"history {key} must be scalar variable")
        value=float(v[()])
    elif key in ds.ncattrs():
        value=float(ds.getncattr(key))
    else:
        raise ValueError(f"missing required history vertical metadata: {key}")
    if not np.isfinite(value):
        raise ValueError(f"nonfinite vertical parameter {key}")
    return value


def validate_parent_history(grid_path:Path,history_path:Path,*,scan_values:bool=True)->dict:
    """Return a fully explicit metadata/value-audit report; errors fail closed.

    scan_values=True reads every wet time/layer frame in bounded 2D slices,
    so real large 3D fields are never materialized at once.
    """
    with Dataset(grid_path) as g,Dataset(history_path) as h:
        d={}
        for name in ("eta_rho","xi_rho","eta_u","xi_u","eta_v","xi_v"):
            if name not in g.dimensions:
                raise ValueError(f"source grid dimension missing {name}")
            d[name]=len(g.dimensions[name])
        if (d["eta_u"]!=d["eta_rho"] or d["xi_u"]!=d["xi_rho"]-1 or
                d["eta_v"]!=d["eta_rho"]-1 or d["xi_v"]!=d["xi_rho"]):
            raise ValueError("parent ROMS grid violates C-grid stagger")
        if any(k not in g.variables for k in (
                "h","mask_rho","mask_u","mask_v","angle","lon_rho","lat_rho")):
            raise ValueError("parent grid missing ROMS depth/masks/angle/geography")
        rho=_as_float(g["mask_rho"][:])
        u=_as_float(g["mask_u"][:])
        v=_as_float(g["mask_v"][:])
        if not (np.isin(rho,[0,1]).all() and np.isin(u,[0,1]).all()
                and np.isin(v,[0,1]).all()):
            raise ValueError("source grid masks must contain finite binary flags")
        masks={"rho":rho.astype(bool),"u":u.astype(bool),"v":v.astype(bool)}
        if (rho.shape!=(d["eta_rho"],d["xi_rho"]) or
                u.shape!=(d["eta_u"],d["xi_u"]) or
                v.shape!=(d["eta_v"],d["xi_v"]) or
                not np.array_equal(masks["u"],masks["rho"][:,:-1]&masks["rho"][:,1:]) or
                not np.array_equal(masks["v"],masks["rho"][:-1,:]&masks["rho"][1:,:])):
            raise ValueError("inconsistent parent wet C-grid masks")
        depth=_as_float(g["h"][:])
        angle=_as_float(g["angle"][:])
        lon=_as_float(g["lon_rho"][:])
        lat=_as_float(g["lat_rho"][:])
        if any(a.shape!=rho.shape for a in (depth,angle,lon,lat)) or not (
            np.isfinite(depth[masks["rho"]]).all() and
            (depth[masks["rho"]]>0).all() and
            np.isfinite(angle[masks["rho"]]).all() and
            np.isfinite(lon[masks["rho"]]).all() and
            np.isfinite(lat[masks["rho"]]).all()):
            raise ValueError("parent wet grid depth, angle or geographic coordinates invalid")
        if "ocean_time" not in h.variables or "ocean_time" not in h.dimensions:
            raise ValueError("parent ROMS history missing ocean_time coordinate/dimension")
        tv=h["ocean_time"]
        if tv.dimensions!=("ocean_time",):
            raise ValueError("ocean_time coordinate has unexpected dimensions")
        times=_as_float(tv[:])
        if times.ndim!=1 or len(times)<2 or not np.isfinite(times).all() or not (np.diff(times)>0).all():
            raise ValueError("history must have >=2 finite strictly increasing timestamps")
        units=getattr(tv,"units","")
        calendar=getattr(tv,"calendar","standard")
        if not isinstance(units,str) or " since " not in units.lower():
            raise ValueError("ocean_time must carry CF units '<unit> since <epoch>'")
        try:
            converted=num2date(times,units=units,calendar=calendar)
        except Exception as exc:
            raise ValueError("CF history ocean_time epoch/calendar invalid") from exc
        for key in d:
            if key not in h.dimensions or len(h.dimensions[key])!=d[key]:
                raise ValueError(f"source history {key} geometry dimension mismatch")
        if "s_rho" not in h.dimensions or "s_w" not in h.dimensions:
            raise ValueError("history missing sigma coordinate dimensions")
        n=len(h.dimensions["s_rho"])
        if n<2 or len(h.dimensions["s_w"])!=n+1:
            raise ValueError("invalid parent ROMS sigma layer dimensions")
        params={k:_scalar(h,k) for k in (
            "Vtransform","Vstretching","theta_s","theta_b","hc","Tcline")}
        if int(params["Vtransform"])!=2 or int(params["Vstretching"])!=4 or (
                params["Vtransform"]!=2 or params["Vstretching"]!=4):
            raise ValueError("currently supported ES3K depth physics requires Vtransform=2,Vstretching=4")
        if params["hc"]<=0 or params["Tcline"]<=0 or abs(params["Tcline"]-params["hc"])>1e-5:
            raise ValueError("inconsistent Vtransform2 hc/Tcline or nonpositive vertical parameter")
        for at,label,coord in (("rho","s_rho","Cs_r"),("w","s_w","Cs_w")):
            s,cs=stretching4(n,params["theta_s"],params["theta_b"],at=at)
            for vname,expected in ((label,s),(coord,cs)):
                if vname not in h.variables or h[vname].dimensions!=(label,):
                    raise ValueError(f"missing parent sigma coordinate curve {vname}")
                actual=_as_float(h[vname][:])
                if not np.allclose(actual,expected,atol=1e-7,rtol=0):
                    raise ValueError(f"history {vname} inconsistent with Vstretching=4 metadata")
        for name,expected in _FIELD_DIMS.items():
            if name not in h.variables or h[name].dimensions!=expected:
                raise ValueError(f"history {name} must have exact ROMS C-grid dimensions {expected}")
        checks={}
        for name,expected in _FIELD_DIMS.items():
            var=h[name]
            if not np.issubdtype(var.dtype,np.number):
                raise ValueError(f"history {name} must be numeric")
            wet=masks[_MASK_FOR[name]]
            if name=="zeta":
                limit=depth
            for t in range(len(times)):
                if not scan_values:
                    break
                if len(expected)==3:
                    slab=_as_float(var[t,:,:])
                    if not np.isfinite(slab[wet]).all():
                        raise ValueError(f"history {name} contains missing wet field at t={t}")
                    if name=="zeta" and np.any(slab[wet]+depth[wet]<=0):
                        raise ValueError("parent history zeta creates a nonpositive wet water column")
                else:
                    for k in range(n):
                        slab=_as_float(var[t,k,:,:])
                        if not np.isfinite(slab[wet]).all():
                            raise ValueError(f"history {name} wet missing field at t={t} sigma={k}")
            checks[name]={"shape":list(var.shape),"wet_values":
                          "ALL_FRAMES_ALL_LAYERS_FINITE" if scan_values else "NOT_SCANNED_METADATA_ONLY"}
        return {
            "scope":"ES3K_PARENT_ROMS_HISTORY_STRICT_INPUT_CONTRACT",
            "grid":Path(grid_path).name,"history":Path(history_path).name,
            "parent_grid_dimensions":d,"time_count":len(times),
            "time_units":units,"time_calendar":calendar,
            "first_timestamp":str(converted[0]),"last_timestamp":str(converted[-1]),
            "strictly_increasing_time":True,"n_s_rho":n,
            "sigma_physics":params,
            "native_mask_consistency":"PASS",
            "wet_field_checks":checks,
            "full_wet_values_scanned":bool(scan_values),
            "real_child_boundary_remapping":"NOT_RUN",
            "physical_roms_bry_nc_and_hydrodynamics":"NOT_RUN",
        }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parent-grid",type=Path,required=True)
    ap.add_argument("--history",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    ap.add_argument("--metadata-only",action="store_true",
                    help="skip wet data scan, explicitly NOT sufficient for input acceptance")
    a=ap.parse_args()
    report=validate_parent_history(a.parent_grid,a.history,scan_values=not a.metadata_only)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(report,indent=2)+"\n")
    print("ES3K_PARENT_HISTORY_STRICT_CONTRACT",json.dumps({
        "time_count":report["time_count"],"layers":report["n_s_rho"],
        "wet_field_scan":report["full_wet_values_scanned"],
        "source_only_not_UD1K_bry":"YES"},sort_keys=True))


if __name__=="__main__":
    main()
