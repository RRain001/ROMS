"""Write/validate complete ROMS bry_unlimit.cdl-shaped SYNTHETIC schema fixture.

This is intentionally NOT a production ES3K->UD1K bry generator: only
precomputed arrays may be supplied, no parent velocity/time interpolation
occurs here. Creates a valid dimension/metadata/variable contract for
all FOUR sides and fails closed for missing or nonfinite *wet* values.
Dry arrays use explicit fill_value, never fabricated wet=0 fields.

Based on ROMS_Nesting/roms_src/roms/Data/ROMS/CDL/bry_unlimit.cdl.
A physical production writer must supply audited actual ROMS history,
coastline-safe stencils, horizontal + vertical transfers, and flux checks.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
from netCDF4 import Dataset, num2date

try:
    from ud1k_vertical_flux_primitives import stretching4
except ImportError:
    from .ud1k_vertical_flux_primitives import stretching4

_NAMES={"zeta":("rho","m"),"temp":("rho","degree_Celsius"),
        "salt":("rho","1e-3"),"u":("u","m s-1"),"v":("v","m s-1"),
        "ubar":("u","m s-1"),"vbar":("v","m s-1")}
_SIDES=("south","north","west","east")
_STAGGER={"rho":("eta_rho","xi_rho"),"u":("eta_u","xi_u"),
          "v":("eta_v","xi_v")}
_FILL=np.float32(1.0e35)


def _to_float(v)->np.ndarray:
    return np.asarray(np.ma.filled(np.ma.asarray(v,dtype=np.float64),np.nan))


def boundary_spec(grid:Dataset,side:str,name:str,n:int,nt:int)->tuple[tuple[str,...],np.ndarray]:
    """Actual C-grid boundary axes including tangential velocity components."""
    if side not in _SIDES or name not in _NAMES:
        raise ValueError("unknown boundary side or ROMS field")
    loc=_NAMES[name][0]
    eta,xi=_STAGGER[loc]
    axis=xi if side in ("south","north") else eta
    wet=_to_float(grid["mask_"+loc][:]).astype(bool)
    perimeter=wet[0,:] if side=="south" else (
        wet[-1,:] if side=="north" else wet[:,0] if side=="west" else wet[:,-1])
    dimensions=(("bry_time","s_rho",axis) if name in ("temp","salt","u","v")
                else ("bry_time",axis))
    shape=(nt,n,len(perimeter)) if len(dimensions)==3 else (nt,len(perimeter))
    return dimensions,np.asarray(perimeter,dtype=bool)


def validate_prepared(grid:Dataset,prepared:dict,time_s:np.ndarray,*,n:int,
                      units:str,calendar:str="gregorian")->dict:
    times=np.asarray(time_s,dtype=float)
    if times.ndim!=1 or len(times)<2 or not np.isfinite(times).all() or not (np.diff(times)>0).all():
        raise ValueError("bry_time must have >=2 finite strictly ascending timestamps")
    if not isinstance(units,str) or " since " not in units.lower():
        raise ValueError("invalid CF bry_time epoch units")
    try:
        num2date(times,units=units,calendar=calendar)
    except Exception as exc:
        raise ValueError("invalid CF bry_time epoch") from exc
    if not isinstance(n,int) or n<2:
        raise ValueError("ROMS s_rho must have at least two layers")
    if set(prepared)!=set(_SIDES):
        raise ValueError("all four ROMS sides required; non-open sides may be dry")
    validated={}
    for side in _SIDES:
        if set(prepared[side])!=set(_NAMES):
            raise ValueError(f"missing complete ROMS forcing fields at {side}")
        for name in _NAMES:
            dimensions,wet=boundary_spec(grid,side,name,n,len(times))
            wanted=(len(times),n,len(wet)) if len(dimensions)==3 else (len(times),len(wet))
            arr=_to_float(prepared[side][name])
            if arr.shape!=wanted:
                raise ValueError(f"{name}_{side} shape {arr.shape} != {wanted}")
            if not np.isfinite(arr).all():
                raise ValueError(f"{name}_{side} has NaN/Inf, possibly on a wet face")
            if len(wet) and not wet.any():
                # Closed-water/west side is still a legal all-dry ROMS slab,
                # but any values are placeholders and not interpreted.
                pass
            validated[name+"_"+side]={"shape":list(arr.shape),
                                      "wet_perimeter_count":int(wet.sum()),
                                      "dimensions":list(dimensions)}
    return validated


def write_synthetic_schema_fixture(grid_path:Path,out_path:Path,prepared:dict,
                                   time_s:np.ndarray,*,n:int=4,
                                   hc:float=50.,theta_s:float=5.,theta_b:float=1.,
                                   time_units:str="seconds since 2000-01-01 00:00:00",
                                   time_calendar:str="gregorian")->dict:
    """Opt-in fixture writer ONLY. Reject existing output (no overwrite)."""
    src=Path(grid_path);dst=Path(out_path)
    if src.resolve()==dst.resolve() or dst.exists():
        raise ValueError("never overwrite grid or an existing boundary file")
    s,c=stretching4(n,theta_s,theta_b,at="rho")
    sw,cw=stretching4(n,theta_s,theta_b,at="w")
    with Dataset(src) as grid:
        validated=validate_prepared(grid,prepared,time_s,n=n,units=time_units,
                                    calendar=time_calendar)
        sizes={d:len(grid.dimensions[d]) for d in (
            "eta_rho","xi_rho","eta_u","xi_u","eta_v","xi_v")}
        dst.parent.mkdir(parents=True,exist_ok=True)
        with Dataset(dst,"w",format="NETCDF4") as f:
            f.createDimension("bry_time",None)
            f.createDimension("s_rho",n)
            f.createDimension("s_w",n+1)
            for dim,sz in sizes.items():
                f.createDimension(dim,sz)
            f.setncattr("type","BOUNDARY FORCING")
            f.setncattr("Conventions","CF-1.8")
            f.setncattr("source_grid",src.name)
            f.setncattr("workflow_status","SYNTHETIC_SCHEMA_TEST_ONLY_NOT_ROMS_PHYSICS")
            f.setncattr("WARNING","Not computed from ES3K physical ocean history; prohibited for production ROMS")
            for name,val in (("spherical",1),("Vtransform",2),("Vstretching",4),
                             ("theta_s",theta_s),("theta_b",theta_b),
                             ("hc",hc),("Tcline",hc)):
                v=f.createVariable(name,"i4" if name in ("spherical","Vtransform","Vstretching") else "f8")
                v.assignValue(val)
            for name,values,dimension in (
                ("s_rho",s,"s_rho"),("Cs_r",c,"s_rho"),
                ("s_w",sw,"s_w"),("Cs_w",cw,"s_w")):
                v=f.createVariable(name,"f8",(dimension,))
                v[:]=values
            for name in ("h","lon_rho","lat_rho","lon_u","lat_u","lon_v","lat_v"):
                if name not in grid.variables:
                    raise ValueError(f"grid {name} missing")
                original=grid[name]
                var=f.createVariable(name,"f8",original.dimensions)
                var[:]=original[:]
                if name=="h":var.units="meter"
            t=f.createVariable("bry_time","f8",("bry_time",))
            t.units=time_units
            t.calendar=time_calendar
            t.long_name="open boundary conditions time"
            t[:]=time_s
            for side in _SIDES:
                for field,(loc,units) in _NAMES.items():
                    dims,wet=boundary_spec(grid,side,field,n,len(time_s))
                    var=f.createVariable(field+"_"+side,"f4",dims,fill_value=_FILL,
                                         zlib=True,complevel=1)
                    var.units=units
                    var.time="bry_time"
                    var[:]=_to_float(prepared[side][field]).astype(np.float32)
    with Dataset(dst) as f:
        if f.getncattr("workflow_status")!="SYNTHETIC_SCHEMA_TEST_ONLY_NOT_ROMS_PHYSICS":
            raise ValueError("fixture classification not preserved")
        if len(f.dimensions["bry_time"])!=len(time_s):
            raise ValueError("output bry_time length changed")
        for side in _SIDES:
            for field in _NAMES:
                name=field+"_"+side
                if tuple(f[name].dimensions)!=tuple(validated[name]["dimensions"]):
                    raise ValueError(f"output variable {name} dimensions changed")
    return {"scope":"COMPLETE_ROMs_BRY_UNLIMIT_CDL_DIMENSION_VARIABLE_CONTRACT",
            "status":"SYNTHETIC_SCHEMA_TEST_ONLY",
            "time_count":int(len(time_s)),"s_rho_count":n,
            "complete_field_variables":len(_SIDES)*len(_NAMES),
            "source_grid":src.name,"output":dst.name,
            "bry_time_units":time_units,"bry_time_calendar":time_calendar,
            "values":{"dry_perimeter":"synthetic fixture",
                      "wet_perimeter":"synthetic fixture, never physical ES3K history"},
            "actual_real_parent_ocean_history":"NOT_AVAILABLE",
            "real_one_way_open_boundary_physics":"NOT_RUN",
            "validated_boundary_shapes":validated}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--child-grid",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--synthetic-fixture-only",action="store_true",required=True)
    p.add_argument("--synthetic-n-levels",type=int,default=4,help="fixture-only N; e.g. 41 to inspect full-size geometry")
    a=p.parse_args()
    prepared={}
    with Dataset(a.child_grid) as grid:
        for side in _SIDES:
            prepared[side]={}
            for field in _NAMES:
                _,wet=boundary_spec(grid,side,field,a.synthetic_n_levels,2)
                shape=(2,a.synthetic_n_levels,len(wet)) if field in ("temp","salt","u","v") else (2,len(wet))
                # Non-zero synthetic profiles: supply an actual array at EVERY
                # perimeter position, even when all-dry. Dry is not physics.
                vals={"zeta":.12,"temp":13.5,"salt":33.5,
                      "u":.18,"v":-.08,"ubar":.18,"vbar":-.08}[field]
                prepared[side][field]=np.full(shape,vals,dtype=np.float64)
    report=write_synthetic_schema_fixture(a.child_grid,a.output,prepared,
                                          np.array([0.,3600.]),n=a.synthetic_n_levels)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(report,indent=2)+"\n")
    print("UD1K_SYNTHETIC_BOUNDARY_FILE_SCHEMA_CONTRACT",json.dumps({
        "variables":report["complete_field_variables"],
        "times":report["time_count"],
        "levels":report["s_rho_count"],
        "real_parent_history":"NOT_RUN"},sort_keys=True))


if __name__=="__main__":
    main()
