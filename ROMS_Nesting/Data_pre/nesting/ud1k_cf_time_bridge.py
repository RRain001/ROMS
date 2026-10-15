"""Explicit CF epoch/calendar bridge from target UD1K bry_time to ES3K history.

A source-history remapper must never treat target MJD days as numeric parent
"seconds since ..." values. This testable adapter transforms actual calendar
dates, refuses temporal extrapolation/gaps and records BOTH numeric axes.
Input date ranges are synthetic until actual ES3K ocean history is supplied.
"""
from __future__ import annotations

import numpy as np
from netCDF4 import date2num,num2date


def _normalize_calendar(calendar:str)->str:
    if not isinstance(calendar,str) or not calendar.strip():
        raise ValueError("CF calendar must be explicit and nonempty")
    value=calendar.strip().lower()
    # CF "gregorian" and "standard" denote the same mixed Julian/Gregorian
    # calendar, but proleptic Gregorian is deliberately a separate choice.
    return "standard" if value=="gregorian" else value


def _dates(values:np.ndarray,units:str,calendar:str,role:str):
    if not isinstance(units,str) or " since " not in units.lower():
        raise ValueError(f"{role} CF units must specify an epoch")
    try:
        result=num2date(values,units=units,calendar=calendar)
        return np.atleast_1d(result)
    except Exception as exc:
        raise ValueError(f"{role} CF time units/calendar invalid") from exc


def bridge_target_to_parent_cf_time(
    requested:np.ndarray,parent:np.ndarray,*,parent_units:str,
    parent_calendar:str="standard",target_units:str|None=None,
    target_calendar:str|None=None,max_gap_hours:float=3.
)->dict:
    """Map target CF dates to parent numeric time (same physical instants).

    Passing target_units=None means requested values are already in the
    parent-native units; this is a legacy preview compatibility path and is
    **explicitly labeled**. For actual bry_time, always pass target_units
    and target_calendar and export the original requested values unchanged.
    """
    source=np.asarray(parent,dtype=float)
    target=np.asarray(requested,dtype=float)
    if (source.ndim!=1 or target.ndim!=1 or len(source)<2 or len(target)<2
            or not np.isfinite(source).all() or not np.isfinite(target).all()
            or not np.all(np.diff(source)>0) or not np.all(np.diff(target)>0)):
        raise ValueError("source and requested times must be finite strictly increasing >=2")
    cal=_normalize_calendar(parent_calendar)
    parent_dates=_dates(source,parent_units,cal,"parent")
    if not np.isfinite(max_gap_hours) or max_gap_hours<=0:
        raise ValueError("max_parent_gap_hours must be finite positive")
    try:
        tsec=np.asarray(date2num(parent_dates,
            "seconds since 2000-01-01 00:00:00",calendar=cal),dtype=float)
    except Exception as exc:
        raise ValueError("parent CF time cannot convert to physical seconds") from exc
    gaps=np.diff(tsec)/3600.
    if not np.isfinite(gaps).all() or np.any(gaps<=0) or np.max(gaps)>max_gap_hours+1e-10:
        raise ValueError("parent history time gap exceeds configured bound")
    if target_units is None:
        if target_calendar is not None:
            raise ValueError("target_calendar specified without target_units")
        in_parent=target.copy()
        numeric_status="SOURCE_NATIVE_CF_UNITS_NO_TARGET_CALENDAR_CONVERSION"
        target_calendar_result=cal
        target_units_result=parent_units
    else:
        if target_calendar is None:
            raise ValueError("target calendar must be explicit for epoch conversion")
        tgt_cal=_normalize_calendar(target_calendar)
        if tgt_cal!=cal:
            raise ValueError("parent and target CF calendars differ: explicit conversion unsupported")
        target_dates=_dates(target,target_units,tgt_cal,"target")
        try:
            in_parent=np.asarray(date2num(target_dates,parent_units,calendar=cal),dtype=float)
        except Exception as exc:
            raise ValueError("target CF timestamps cannot map into parent epoch") from exc
        target_calendar_result=tgt_cal
        target_units_result=target_units
        numeric_status="TARGET_CF_EPOCH_TO_SOURCE_HISTORY_EPOCH_CONVERTED"
    if not np.isfinite(in_parent).all() or not np.all(np.diff(in_parent)>0):
        raise ValueError("converted parent numeric times invalid or not increasing")
    # Account only for floating-point date conversion rounding near exact
    # frame endpoints; no material temporal extrapolation is authorized.
    tol=max(1e-9,1e-11*max(1.,abs(source[0]),abs(source[-1])))
    if in_parent[0]<source[0]-tol or in_parent[-1]>source[-1]+tol:
        raise ValueError("target CF time outside parent history coverage")
    in_parent=np.clip(in_parent,source[0],source[-1])
    return {
        "parent_time_values":in_parent,
        "bry_time_values":target.copy(),
        "parent_history_time_units":parent_units,
        "parent_history_calendar":cal,
        "bry_time_units":target_units_result,
        "bry_time_calendar":target_calendar_result,
        "parent_max_gap_hours":float(np.max(gaps)),
        "max_gap_hours_allowed":float(max_gap_hours),
        "time_axis_mapping_status":numeric_status,
        "temporal_extrapolation":"FORBIDDEN",
    }
