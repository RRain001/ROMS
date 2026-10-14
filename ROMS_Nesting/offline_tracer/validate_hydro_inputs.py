"""Read-only ROMS hydrodynamic file schema gate for future offline HTO.

Structural checks only: validating required fields and time records does
NOT establish a functioning Thyng-style ROMS offline model or physical
time-interpolation/volume-flux consistency.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from netCDF4 import Dataset

REQUIRED={
    "zeta": ("ocean_time","eta_rho","xi_rho"),
    "ubar": ("ocean_time","eta_u","xi_u"),
    "vbar": ("ocean_time","eta_v","xi_v"),
    "u": ("ocean_time","s_rho","eta_u","xi_u"),
    "v": ("ocean_time","s_rho","eta_v","xi_v"),
}
AKS_DIMS=("ocean_time","s_w","eta_rho","xi_rho")


def _sample(var) -> np.ndarray:
    """At most 8 values per spatial dimension and a snapshot at first/last."""
    ix=[]
    for axis,d in enumerate(var.dimensions):
        n=var.shape[axis]
        if axis==0:
            ix.append([0,n-1] if n>1 else [0])
        else:
            ix.append(slice(0,None,max(1,(n+7)//8)))
    array=np.asarray(var[ix[0],*ix[1:]])
    if np.ma.isMaskedArray(array):
        if np.ma.getmaskarray(array).any():
            raise ValueError(f"{var.name}: masked/fill values among sampled interior")
        array=np.asarray(array.data)
    return array


def inspect_hydrodynamics(path: str | Path, *, require_aks: bool=True) -> dict[str,object]:
    """Validate exact C-grid shapes and sampled fields of one history file.

    A passing report is an input-contract preflight, NOT Eulerian physics.
    """
    path=Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    with Dataset(path,"r") as ds:
        if "ocean_time" not in ds.variables:
            raise ValueError("missing ocean_time")
        t=ds.variables["ocean_time"]
        if t.ndim!=1 or t.dimensions!=("ocean_time",):
            raise ValueError("ocean_time must be one-dimensional")
        if len(t)<2:
            raise ValueError("at least two hydrodynamic snapshots required")
        tt=np.asarray(t[:],dtype=np.float64)
        if not np.all(np.isfinite(tt)) or np.any(np.diff(tt)<=0):
            raise ValueError("nonfinite or non-monotonic ocean_time")
        units=getattr(t,"units","")
        if not any(k in units.lower() for k in ("seconds since","days since")):
            raise ValueError("ocean_time must specify seconds/days since epoch")
        for d in ("eta_rho","xi_rho","eta_u","xi_u","eta_v","xi_v","s_rho","s_w"):
            if d not in ds.dimensions:
                raise ValueError(f"missing C-grid dimension {d}")
        nr=ds.dimensions["s_rho"].size
        nw=ds.dimensions["s_w"].size
        if nw!=nr+1:
            raise ValueError("s_w should have one more level than s_rho")
        for ax in ("xi","eta"):
            nrho=ds.dimensions[ax+"_rho"].size
            if ds.dimensions[ax+"_u"].size!=(nrho-1 if ax=="xi" else nrho):
                raise ValueError(f"invalid u C-grid dimension {ax}")
            if ds.dimensions[ax+"_v"].size!=(nrho if ax=="xi" else nrho-1):
                raise ValueError(f"invalid v C-grid dimension {ax}")
        fields={}
        names=dict(REQUIRED)
        name_aks=next((name for name in ("AKs","Aks","aks") if name in ds.variables),None)
        if require_aks and name_aks is None:
            raise ValueError("missing AKs vertical tracer diffusion coefficient: do not assume zero")
        if name_aks is not None:
            names[name_aks]=AKS_DIMS
        for name,dimensions in names.items():
            if name not in ds.variables:
                raise ValueError(f"missing required ROMS field: {name}")
            v=ds.variables[name]
            if v.dimensions!=dimensions:
                raise ValueError(f"{name}: incorrect stagger/dimensions {v.dimensions}, expected {dimensions}")
            values=_sample(v)
            if values.size==0 or not np.all(np.isfinite(values)):
                raise ValueError(f"{name}: nonfinite sampled field")
            if name==name_aks and np.min(values)<0:
                raise ValueError("AKs must be nonnegative")
            fields[name]={"shape":list(v.shape),"dtype":str(v.dtype)}
        return {
            "status":"SCHEMA_PASS_OFFLINE_PHYSICS_NOT_RUN",
            "file":path.name,
            "times":int(len(tt)),
            "time_units":units,
            "time_begin":float(tt[0]),
            "time_end":float(tt[-1]),
            "tracer_vertical_levels":nr,
            "AKs_present":name_aks is not None,
            "fields":fields,
        }
