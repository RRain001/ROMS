"""I4 synthetic rotating GLORYS-to-ROMS vertical free-surface regression.

Checks imported production preprocessors, not a detached toy formula.
Synthetic forcing only: does NOT validate actual CMEMS files or ocean run.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest
import sys

import numpy as np
from netCDF4 import Dataset

ROOT=Path(__file__).resolve().parents[1]
for relative in ("core","nesting","impl/preprocessing"):
    folder=str(ROOT/relative)
    if folder not in sys.path:
        sys.path.insert(0,folder)

from bathymetry_grid import make_geometry
from roms_preprocessing_utils import VerticalConfig,sigma_depths,rotate_to_grid
import create_ocean_ini_from_glorys as initial
import create_ocean_bry_from_glorys as boundary

ES={
 "grid_id":"ES3K","geometry_type":"rotated_lcc",
 "geometry_status":"CANDIDATE_APPROXIMATE","center_lon":131.32,
 "center_lat":37.63,"width_points":15,"height_points":13,
 "dx_m":3000.0,"dy_m":3000.0,"angle_deg":20.0
}


def fixture_grid():
    geom,_,_=make_geometry(ES)
    shape=geom["lon_rho"].shape
    result=SimpleNamespace(**geom)
    result.h=np.full(shape,125.0)
    result.mask_rho=np.ones(shape,dtype=np.int8)
    result.path=Path("rotated_fixture_grid.nc")
    return result


def source_file(path:Path,initial_zeta:float=4.5):
    lon=np.linspace(130.7,131.9,15)
    lat=np.linspace(37.1,38.15,14)
    depths=np.array([0.0,50.0,300.0])
    with Dataset(path,"w") as ds:
        for name,n in (("longitude",len(lon)),("latitude",len(lat)),
                       ("depth",len(depths)),("time",2)):
            ds.createDimension(name,n)
        ds.createVariable("longitude","f8",("longitude",))[:]=lon
        ds.createVariable("latitude","f8",("latitude",))[:]=lat
        ds.createVariable("depth","f8",("depth",))[:]=depths
        t=ds.createVariable("time","f8",("time",))
        t.units="seconds since 2024-01-01 00:00:00"
        t.calendar="gregorian"
        t[:]=[0,86400]
        ssh=ds.createVariable("zos","f8",("time","latitude","longitude"))
        ssh[:]=np.array([initial_zeta,-3.0])[:,None,None]
        for name,values in (
            ("thetao",10.0-0.02*depths),("so",35.0+0.002*depths),
            ("uo",np.full_like(depths,0.32)),("vo",np.full_like(depths,0.12)),
        ):
            var=ds.createVariable(name,"f8",("time","depth","latitude","longitude"))
            var[:]=values[None,:,None,None]
            if name=="thetao":var.units="Celsius"
            if name=="so":var.units="psu"


class DynamicSigmaTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.src=self.root/"glorys_like.nc"
        source_file(self.src)
        self.grid=fixture_grid()
        self.v=VerticalConfig(N=8,theta_s=7.0,theta_b=0.1,
                              Tcline=80,Hmin_m=10,Vtransform=2,Vstretching=4)

    def test_boundary_all_edges_update_sigma_with_sea_level(self):
        with Dataset(self.src) as ds:
            lo,la=ds["longitude"][:],ds["latitude"][:]
            depth=ds["depth"][:]
            temp=np.asarray(ds["thetao"][0],dtype=float)
            salt=np.asarray(ds["so"][0],dtype=float)
            u=np.asarray(ds["uo"][0],dtype=float)
            v=np.asarray(ds["vo"][0],dtype=float)
            for edge in ("west","east","south","north"):
                shape=boundary.edge_target_geometry(self.grid,self.v,edge)
                self.assertLessEqual(max(shape["h"].shape),15)
                result={}
                for level,signal in ((4.5,"high"),(-3.0,"low")):
                    ssh=np.full((len(la),len(lo)),level)
                    state=boundary.interpolate_edge_state(lo,la,depth,ssh,temp,salt,u,v,shape)
                    z,_,hz=sigma_depths(shape["h"],self.v,np.full(shape["h"].shape,level))
                    # GLORYS source only spans depth<=0: above-mean-sea-level
                    # ROMS top-cell centers inherit the shallowest
                    # GLORYS field (do not extrapolate 10+0.02*z>10).
                    expected=10.0+0.02*np.clip(z,-300.0,0.0)
                    np.testing.assert_allclose(state["temp_rho"],expected,rtol=0,atol=1.0e-9)
                    np.testing.assert_allclose(state["zeta_rho"],level,rtol=0,atol=1e-10)
                    self.assertTrue(np.all(np.isfinite(state["u"])))
                    self.assertTrue(np.all(np.isfinite(state["v"])))
                    result[signal]=(state,z,hz)
                high,low=result["high"],result["low"]
                self.assertGreater(float(np.max(np.abs(high[0]["temp_rho"]-low[0]["temp_rho"]))),0.02)
                self.assertAlmostEqual(float((high[2]-low[2]).sum(axis=0).mean()),7.5,delta=1e-8)

    def test_rotated_velocity_roundtrip_east_north(self):
        angle=self.grid.angle
        east=np.full_like(angle,0.32)
        north=np.full_like(angle,0.12)
        ux,veta=rotate_to_grid(east,north,angle)
        np.testing.assert_allclose(ux*np.cos(angle)-veta*np.sin(angle),east,atol=1e-14)
        np.testing.assert_allclose(ux*np.sin(angle)+veta*np.cos(angle),north,atol=1e-14)
        self.assertGreater(float(np.std(ux)),1e-8)

    def test_initial_main_uses_zeta_dependent_sigma_geometry(self):
        args=SimpleNamespace(config=None,src=str(self.src),grid="unused.nc",
                             output=str(self.root/"ini.nc"),profile=None,time=None)
        config={"time_start":"2024-01-01T00:00:00",
                "dataset_id_daily":"synthetic-test","time_mean_center":"12:00:00",
                "roms_time_policy":"daily_mean_to_day_start"}
        case=SimpleNamespace(title="JAPAN_SEA_SYNTHETIC")
        with patch.object(initial,"parse_args",return_value=args), \
             patch.object(initial,"load_glorys_config",return_value=config), \
             patch.object(initial,"build_glorys_paths",return_value=SimpleNamespace(
                 staged_initial=self.src,roms_ini=Path(args.output))), \
             patch.object(initial,"resolve_grid_path",return_value=self.root/"candidate.nc"), \
             patch.object(initial,"load_grid",return_value=self.grid), \
             patch.object(initial,"load_vertical_config",return_value=self.v), \
             patch.object(initial,"load_project_params",return_value={"time":{"start":"2024-01-01T00:00:00"}}), \
             patch.object(initial,"glorys_source_time_from_model_time",side_effect=lambda cfg,date:date), \
             patch.object(initial,"load_case_naming",return_value=case):
            initial.main()
        with Dataset(args.output) as ini:
            self.assertEqual(ini.vertical_interpolation_geometry,
                             "TIME_SPECIFIC_ZETA_SIGMA_VTRANSFORM2")
            self.assertEqual(ini["temp"].shape,(1,8,13,14+1))
            np.testing.assert_allclose(ini["zeta"][0],4.5,atol=1e-11)
            z,_,h=sigma_depths(self.grid.h,self.v,np.full(self.grid.h.shape,4.5))
            np.testing.assert_allclose(ini["temp"][0],10+0.02*np.clip(z,-300.0,0.0),rtol=0,atol=1e-9)
            np.testing.assert_allclose(ini["ubar"][0],
                                       (0.32*np.cos(self.grid.angle)+
                                        0.12*np.sin(self.grid.angle))[:,:-1]*0.5+
                                       (0.32*np.cos(self.grid.angle)+
                                        0.12*np.sin(self.grid.angle))[:,1:]*0.5,
                                       atol=1e-9)
            self.assertTrue(np.all(np.isfinite(ini["v"][...])))


if __name__=="__main__":
    unittest.main()
