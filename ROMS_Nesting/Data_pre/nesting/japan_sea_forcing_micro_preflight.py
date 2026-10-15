"""Small *offline* Japan Sea GLORYS / ERA5 / TPXO staging interface preflight.

This checks existing no-nesting staged NetCDF contracts at ONE interior
test coordinate and a <=72h synthetic calendar window. It is NOT a source
download, production-domain coverage proof, real forcing file conversion
or an ES3K/UD1K ROMS integration. Times are fixture/test-only, never
written back to frozen case configs.

Inputs are outputs of the existing, unchanged no-nesting download/staging
modules: GLORYS thetao/so/uo/vo/zos, ERA5 normalized atmosphere and
radiation, and TPXO9 elevation/current harmonic constants. Both source
variable dimensions and units are validated, including GLORYS daily
noon vs ERA5 hourly source time coverage.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, date2num, num2date

OCEAN_3D=("thetao","so","uo","vo")
OCEAN_2D=("zos",)
ATM_FIELDS=("Uwind","Vwind","Pair","Tair","Qair","rain","EminusP")
RAD_FIELDS=("swrad","lwrad_down","lwrad")
TIDAL_ELEVATION_POLAR=("tide_Eamp","tide_Ephase")
TIDAL_ELEVATION_COMPLEX=("tide_ERe","tide_EIm")
TIDAL_CURRENT_POLAR=("tide_Cmax","tide_Cmin","tide_Cangle","tide_Cphase")
TIDAL_CURRENT_COMPLEX=("tide_URe","tide_UIm","tide_VRe","tide_VIm")
# Unit variants from common NetCDF CF/Copernicus formats; no automatic
# conversion is silently applied by this admission preflight.
EXPECTED_UNITS={
    "thetao":{"degrees_c","degree_celsius","degrees_celsius","celsius","degree_c"},
    "so":{"1e-3","psu","practical_salinity_unit","1","0.001"},
    "uo":{"m/s","m s-1","m s**-1"},"vo":{"m/s","m s-1","m s**-1"},
    "zos":{"m","meter","metre","meters","metres"},
    "Uwind":{"m/s","m s-1","m s**-1"},"Vwind":{"m/s","m s-1","m s**-1"},
    "Pair":{"mbar","hpa","millibar"},
    "Tair":{"celsius","degree_celsius","degrees_c","degrees_celsius"},
    "Qair":{"percent","%"},"rain":{"m s-1","m/s","m s**-1"},
    "EminusP":{"m s-1","m/s","m s**-1"},
    "swrad":{"w m-2","w/m2","w m**-2"},
    "lwrad_down":{"w m-2","w/m2","w m**-2"},
    "lwrad":{"w m-2","w/m2","w m**-2"},
}
TIME_LIMIT=timedelta(hours=72)


def _unit(s: str)->str:
    return str(s).lower().strip().replace(" ","_").replace("_","_").replace("°","")


def _assert_units(var,name:str)->str:
    unit=getattr(var,"units",None)
    if not isinstance(unit,str) or not unit.strip():
        raise ValueError(f"{name}: missing units; conversion must be explicit")
    val=unit.lower().strip().replace("°","").replace(" ","")
    accepted={v.replace(" ","") for v in EXPECTED_UNITS[name]}
    if val not in accepted:
        raise ValueError(f"{name}: unexpected units {unit!r}; no implicit conversion")
    return unit


def _axis(ds:Dataset,options:tuple[str,...],source:str)->str:
    found=[name for name in options if name in ds.variables and name in ds.dimensions]
    if len(found)!=1:
        raise ValueError(f"{source}: expected exactly one axis from {options}, found {found}")
    return found[0]


def _rectilinear(ds:Dataset,source:str,point:tuple[float,float])->tuple[str,str,dict]:
    lat=_axis(ds,("latitude","lat"),source)
    lon=_axis(ds,("longitude","lon"),source)
    axes={}
    for name in (lat,lon):
        v=ds[name]
        if v.dimensions!=(name,):
            raise ValueError(f"{source} coordinate {name}: require 1D rectilinear axis")
        a=np.asarray(np.ma.filled(np.ma.asarray(v[:],dtype=float),np.nan))
        if len(a)<2 or not np.isfinite(a).all() or not (
                np.all(np.diff(a)>0) or np.all(np.diff(a)<0)):
            raise ValueError(f"{source} coordinate {name}: require sorted finite >=2 points")
        axes[name]=a
    target_lon,target_lat=point
    if not (np.min(axes[lat])<=target_lat<=np.max(axes[lat]) and
            np.min(axes[lon])<=target_lon<=np.max(axes[lon])):
        raise ValueError(f"{source}: test coordinate not within source coordinate extent")
    return lat,lon,{
        "shape_lat_lon":[len(axes[lat]),len(axes[lon])],
        "test_nearest_eta":int(np.argmin(np.abs(axes[lat]-target_lat))),
        "test_nearest_xi":int(np.argmin(np.abs(axes[lon]-target_lon))),
        "coordinate_extent_lon_lat":[float(axes[lon].min()),float(axes[lon].max()),
                                      float(axes[lat].min()),float(axes[lat].max())],
    }


def _times(ds:Dataset,source:str,start:datetime,stop:datetime,max_hours:float)->dict:
    if "time" not in ds.variables or "time" not in ds.dimensions:
        raise ValueError(f"{source}: missing CF time")
    v=ds["time"]
    if v.dimensions!=("time",):
        raise ValueError(f"{source}: CF time must be 1D dimension")
    raw=np.asarray(np.ma.filled(np.ma.asarray(v[:],dtype=float),np.nan))
    if len(raw)<2 or not np.isfinite(raw).all() or not (np.diff(raw)>0).all():
        raise ValueError(f"{source}: time axis must be finite and strictly increasing")
    units=getattr(v,"units","")
    if not isinstance(units,str) or " since " not in units.lower():
        raise ValueError(f"{source}: missing CF time epoch units")
    calendar=getattr(v,"calendar","standard")
    try:
        num2date(raw,units=units,calendar=calendar)
        requested=np.asarray(date2num([start,stop],units=units,calendar=calendar),dtype=float)
        start_s=float(date2num(start,units="seconds since 2000-01-01 00:00:00"))
        stop_s=float(date2num(stop,units="seconds since 2000-01-01 00:00:00"))
        dt_seconds=np.asarray(date2num(num2date(raw,units=units,calendar=calendar),
                            units="seconds since 2000-01-01 00:00:00",
                            calendar=calendar),dtype=float)
    except Exception as exc:
        raise ValueError(f"{source}: unparsable CF time/calendar") from exc
    if raw[0]>requested[0] or raw[-1]<requested[1]:
        raise ValueError(f"{source}: source time does not bracket requested test interval")
    worst=float(np.max(np.diff(dt_seconds))/3600)
    if worst>max_hours+1e-6:
        raise ValueError(f"{source}: source temporal gap {worst:.2f}h exceeds {max_hours:.2f}h")
    if stop_s<=start_s:
        raise ValueError("invalid test window")
    return {"samples":len(raw),"largest_gap_hours":worst,
            "source_first":str(num2date(raw[0],units=units,calendar=calendar)),
            "source_last":str(num2date(raw[-1],units=units,calendar=calendar)),
            "requested_window_bracketed":True}


def _sample(var,time_indices:tuple[int,...]|None,latitude_index:int,longitude_index:int)->bool:
    # Reads at most first/last time, first/last vertical level,
    # and a 3x3 patch around a single test coordinate; never a full
    # multi-month 3D grid. Honors NetCDF masked missing values.
    dims=var.dimensions
    count={d:var.shape[i] for i,d in enumerate(dims)}
    selection=[]
    for dim in dims:
        if dim=="time":
            selection.append(list(time_indices or (0,)))
        elif dim=="depth":
            selection.append([0,count[dim]-1])
        elif dim in ("latitude","lat"):
            selection.append(list(range(max(0,latitude_index-1),
                                        min(count[dim],latitude_index+2))))
        elif dim in ("longitude","lon"):
            selection.append(list(range(max(0,longitude_index-1),
                                        min(count[dim],longitude_index+2))))
        elif dim=="tide_period":
            selection.append([0])
        else:
            raise ValueError(f"unexpected variable dimension {dim!r}")
    # Use orthogonal NetCDF indexing and convert masks to non-finite data.
    arr=var[tuple(selection)]
    checked=np.asarray(np.ma.filled(np.ma.asarray(arr,dtype=float),np.nan))
    return bool(checked.size and np.isfinite(checked).any())


def _fields(ds:Dataset,source:str,names:tuple[str,...],dims:tuple[str,...],
            loc:dict,check_units:bool=True)->dict:
    result={}
    for name in names:
        if name not in ds.variables:
            raise ValueError(f"{source}: missing expected {name}")
        var=ds[name]
        if var.dimensions!=dims:
            raise ValueError(f"{source}: {name} dimensions {var.dimensions} != {dims}")
        unit=_assert_units(var,name) if check_units else getattr(var,"units",None)
        if not _sample(var,(0,len(ds.dimensions["time"])-1) if "time" in dims else None,
                       loc["test_nearest_eta"],loc["test_nearest_xi"]):
            raise ValueError(f"{source}: {name} has no finite values in test-site sample")
        result[name]={"units":unit,"dimensions":list(var.dimensions),
                      "near_site_sample_finite":True}
    return result


def audit_forcing(ocean_path:Path,atmosphere_path:Path,radiation_path:Path,
                  tides_path:Path,*,start:datetime,stop:datetime,
                  lon:float,lat:float,require_uv_tides:bool=True)->dict:
    if stop<=start or stop-start>TIME_LIMIT:
        raise ValueError("test-only preflight requires positive <=72 hour interval; no production year")
    point=(float(lon),float(lat))
    if not np.isfinite(point).all():
        raise ValueError("test coordinate must be finite")
    out={}
    with Dataset(ocean_path) as ds:
        ln,lo,geo=_rectilinear(ds,"GLORYS12V1",point)
        depth=_axis(ds,("depth",),"GLORYS12V1")
        z=np.asarray(np.ma.filled(np.ma.asarray(ds[depth][:],dtype=float),np.nan))
        if ds[depth].dimensions!=(depth,) or len(z)<2 or not np.isfinite(z).all() or (
                z<0).any() or not np.all(np.diff(z)>0):
            raise ValueError("GLORYS12V1 depth coordinate must be nonnegative increasing")
        out["ocean"]={"coordinates":geo,
                      "time":_times(ds,"GLORYS12V1",start,stop,max_hours=36),
                      "depth_count":len(z),
                      "fields":{}}
        out["ocean"]["fields"].update(_fields(
            ds,"GLORYS12V1",OCEAN_3D,("time",depth,ln,lo),geo))
        out["ocean"]["fields"].update(_fields(
            ds,"GLORYS12V1",OCEAN_2D,("time",ln,lo),geo))
    with Dataset(atmosphere_path) as ds:
        ln,lo,geo=_rectilinear(ds,"ERA5_atmosphere",point)
        out["atmosphere"]={"coordinates":geo,
                           "time":_times(ds,"ERA5_atmosphere",start,stop,max_hours=2),
                           "fields":_fields(ds,"ERA5_atmosphere",ATM_FIELDS,
                                            ("time",ln,lo),geo)}
    with Dataset(radiation_path) as ds:
        ln,lo,geo=_rectilinear(ds,"ERA5_radiation",point)
        out["radiation"]={"coordinates":geo,
                          "time":_times(ds,"ERA5_radiation",start,stop,max_hours=2),
                          "fields":_fields(ds,"ERA5_radiation",RAD_FIELDS,
                                           ("time",ln,lo),geo)}
    if (out["atmosphere"]["time"]["samples"]!=out["radiation"]["time"]["samples"] or
            out["atmosphere"]["time"]["source_first"]!=out["radiation"]["time"]["source_first"] or
            out["atmosphere"]["time"]["source_last"]!=out["radiation"]["time"]["source_last"]):
        raise ValueError("ERA5 atmosphere/radiation staged time coverage mismatch")
    with Dataset(tides_path) as ds:
        ln,lo,geo=_rectilinear(ds,"TPXO9",point)
        if "tide_period" not in ds.variables or ds["tide_period"].dimensions!=("tide_period",):
            raise ValueError("TPXO9 requires tide_period harmonic coordinate")
        period=np.asarray(np.ma.filled(np.ma.asarray(ds["tide_period"][:],dtype=float),np.nan))
        if not len(period) or not np.isfinite(period).all() or np.any(period<=0):
            raise ValueError("TPXO9 harmonic periods must be positive finite")
        unit=str(getattr(ds["tide_period"],"units","")).lower().strip()
        if unit not in ("hours","hour"):
            raise ValueError("TPXO9 tide_period must be in hours")
        choice=lambda polar,complex_:(
            polar if all(n in ds.variables for n in polar) else
            complex_ if all(n in ds.variables for n in complex_) else None)
        elevation=choice(TIDAL_ELEVATION_POLAR,TIDAL_ELEVATION_COMPLEX)
        current=choice(TIDAL_CURRENT_POLAR,TIDAL_CURRENT_COMPLEX)
        if elevation is None:
            raise ValueError("TPXO9 missing complete elevation harmonics")
        if require_uv_tides and current is None:
            raise ValueError("TPXO9 missing four current harmonic fields for UV_TIDES")
        out["tides"]={"coordinates":geo,
                      "tide_constituents":len(period),
                      "elevation_representation":"amplitude_phase" if elevation==TIDAL_ELEVATION_POLAR else "complex",
                      "UV_current_representation":("amplitude_phase" if current==TIDAL_CURRENT_POLAR else
                                                  "complex" if current is not None else "ABSENT"),
                      "fields":_fields(ds,"TPXO9",elevation+(current or ()),
                                       ("tide_period",ln,lo),geo,check_units=False)}
    return {"status":"OFFLINE_STAGED_SOURCE_INTERFACE_MICRO_PREFLIGHT_PASS",
            "run_scope":"ONE_INTERIOR_POINT_MAX_72H_NOT_FULL_ES3K_DOMAIN",
            "test_coordinate_lon_lat":[lon,lat],
            "test_start":start.isoformat(),"test_stop":stop.isoformat(),
            "download_or_api_calls":"NONE","ROMS_model_integration":"NOT_RUN",
            "real_ES3K_history":"NOT_RUN","target_UD1K_physics":"NOT_RUN",
            "source_interfaces":out}


def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("ocean","atmosphere","radiation","tides","report"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--start",required=True,help="ISO test datetime only")
    p.add_argument("--stop",required=True,help="ISO test datetime only")
    p.add_argument("--lon",type=float,required=True)
    p.add_argument("--lat",type=float,required=True)
    args=p.parse_args()
    result=audit_forcing(args.ocean,args.atmosphere,args.radiation,args.tides,
                         start=datetime.fromisoformat(args.start),
                         stop=datetime.fromisoformat(args.stop),
                         lon=args.lon,lat=args.lat)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print("JAPAN_SEA_STAGED_SOURCE_OFFLINE_MICRO",json.dumps({
        "status":result["status"],
        "GLORYS_fields":sorted(result["source_interfaces"]["ocean"]["fields"]),
        "ERA5_atm_fields":sorted(result["source_interfaces"]["atmosphere"]["fields"]),
        "ERA5_rad_fields":sorted(result["source_interfaces"]["radiation"]["fields"]),
        "TPXO_elevation":result["source_interfaces"]["tides"]["elevation_representation"],
        "TPXO_uv":result["source_interfaces"]["tides"]["UV_current_representation"],
        "no_download":True,"no_model_run":True
    },sort_keys=True))


if __name__=="__main__":
    main()
