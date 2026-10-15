"""Actual existing GLORYS/ERA5/TPXO -> ROMS converters on tiny synthetic files.

Calls production `main()` of five *existing nested preprocessing modules*.
Only configuration/grid resolution are injected to keep the entire numerical
interpolation and NetCDF write/read paths authentic and extremely cheap.
No real downloads, Secret reads, grids or ROMS integrations.
"""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
import tempfile
import unittest

import numpy as np
from netCDF4 import Dataset,num2date

BASE=Path(__file__).resolve().parents[1]
for relative in ("core","nesting","impl/preprocessing"):
    source=str(BASE/relative)
    if source not in sys.path:
        sys.path.insert(0,source)

import create_ocean_ini_from_glorys as ini
import create_ocean_bry_from_glorys as bry
import create_atm_forcing_from_era5 as atm
import create_rad_forcing_from_era5 as rad
import create_tides_from_tpxo as tides

from roms_preprocessing_utils import GridData,VerticalConfig
from japan_sea_forcing_micro_preflight import audit_forcing
from test_japan_sea_forcing_micro_preflight import synthetic_ocean,synthetic_era5,synthetic_tpxo


def synthetic_grid_data()->GridData:
    nj,ni=4,5
    jj,ii=np.indices((nj,ni))
    lon=129.5+ii*.3
    lat=36.45+jj*.3
    return GridData(
        path=Path("SYNTHETIC_only_nesting_ES3K_grid.nc"),
        lon_rho=lon,lat_rho=lat,
        lon_u=.5*(lon[:,:-1]+lon[:,1:]),
        lat_u=.5*(lat[:,:-1]+lat[:,1:]),
        lon_v=.5*(lon[:-1,:]+lon[1:,:]),
        lat_v=.5*(lat[:-1,:]+lat[1:,:]),
        h=np.full((nj,ni),125.),mask_rho=np.ones((nj,ni),dtype=np.int8),
        angle=np.full((nj,ni),.2),
        pm=np.full((nj,ni),1/2900.),pn=np.full((nj,ni),1/3300.),
    )


class ExistingProductionConverterMicro(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.ocean=self.root/"SYNTHETIC_GLORYS_daily.nc"
        self.atm=self.root/"SYNTHETIC_ERA5_atm_hourly.nc"
        self.rad=self.root/"SYNTHETIC_ERA5_rad_hourly.nc"
        self.tpxo=self.root/"SYNTHETIC_TPXO9_harmonics.nc"
        synthetic_ocean(self.ocean)
        synthetic_era5(self.atm)
        synthetic_era5(self.rad,radiation=True)
        synthetic_tpxo(self.tpxo)
        self.grid=synthetic_grid_data()
        self.vertical=VerticalConfig(N=4,theta_s=5.0,theta_b=.1,
                                    Tcline=50,Hmin_m=10,Vtransform=2,Vstretching=4)
        self.config={
            "time_start":"2018-01-02T00:00:00",
            "time_stop":"2018-01-03T00:00:00",
            "time_mean_center":"12:00:00",
            "roms_time_policy":"daily_mean_to_day_start",
            "dataset_id_daily":"cmems_mod_glo_phy_my_0.083deg_P1D-m",
        }
        self.params={
            "time":{"start":"2018-01-02T00:00:00",
                    "stop":"2018-01-03T00:00:00"},
            "tides":{"zero_phase_date":"2018-01-01T00:00:00",
                     "phase_convention":"OTPS"},
        }
        self.names=SimpleNamespace(title="SYNTHETIC Japan Sea test")
        self.dummy_path=self.root/"SYNTHETIC_only_ES3K.nc"
        self.outputs={
            "ini":self.root/"SYNTHETIC_only_ROMS_ini.nc",
            "bry":self.root/"SYNTHETIC_only_ROMS_outer_bry.nc",
            "atm":self.root/"SYNTHETIC_only_ROMS_atm.nc",
            "rad":self.root/"SYNTHETIC_only_ROMS_rad.nc",
            "tpxo":self.root/"SYNTHETIC_only_ROMS_tides.nc",
        }

    def _call(self,module,*,source:Path,output:Path,kind:str)->None:
        kw={"src":str(source),"grid":str(self.dummy_path),"output":str(output)}
        if kind=="ini":
            kw.update(config=None,time="2018-01-02T00:00:00",profile=None)
        elif kind=="bry":
            kw.update(config=None,start="2018-01-02T00:00:00",
                      stop="2018-01-03T00:00:00",profile=None)
        elif kind=="tpxo":
            kw.update(start=None,stop=None,profile=None,zero_phase_date="20180101",
                      require_uv=True,report_dir=str(self.root))
        args=SimpleNamespace(**kw)
        with ExitStack() as stack:
            for name,value in (
                ("parse_args",lambda:args),
                ("resolve_grid_path",lambda *a,**k:self.dummy_path),
                ("load_grid",lambda *a,**k:self.grid),
                ("load_case_naming",lambda:self.names),
            ):
                stack.enter_context(patch.object(module,name,value))
            if kind in ("ini","bry"):
                stack.enter_context(patch.object(
                    module,"load_glorys_config",lambda *a,**k:self.config))
                # Override only config/path routing, not any interpolation.
                stack.enter_context(patch.object(
                    module,"build_glorys_paths",lambda *a,**k:SimpleNamespace(
                        staged_initial=self.ocean,staged_boundary=self.ocean,
                        roms_ini=self.outputs["ini"],roms_bdy=self.outputs["bry"])))
                stack.enter_context(patch.object(
                    module,"load_vertical_config",lambda:self.vertical))
            if kind=="ini":
                stack.enter_context(patch.object(
                    module,"load_project_params",lambda:self.params))
            if kind=="tpxo":
                stack.enter_context(patch.object(
                    module,"load_project_params",lambda:self.params))
            module.main()

    def run_all(self)->None:
        audit=audit_forcing(self.ocean,self.atm,self.rad,self.tpxo,
                            start=datetime(2018,1,2),stop=datetime(2018,1,3),
                            lon=130.,lat=37.)
        self.assertEqual(audit["download_or_api_calls"],"NONE")
        for mod,src,name in (
            (ini,self.ocean,"ini"),(bry,self.ocean,"bry"),
            (atm,self.atm,"atm"),(rad,self.rad,"rad"),
            (tides,self.tpxo,"tpxo"),
        ):
            self._call(mod,source=src,output=self.outputs[name],kind=name)

    def test_actual_five_converters_write_matching_roms_netcdf(self):
        self.run_all()
        for file in self.outputs.values():
            self.assertTrue(file.is_file() and file.stat().st_size>200)
        expected_u=.17*np.cos(.2)-.04*np.sin(.2)
        expected_v=-.17*np.sin(.2)-.04*np.cos(.2)
        with Dataset(self.outputs["ini"]) as d:
            self.assertEqual(d["temp"].shape,(1,4,4,5))
            self.assertEqual(d["u"].shape,(1,4,4,4))
            self.assertEqual(d["v"].shape,(1,4,3,5))
            self.assertEqual(d["ubar"].shape,(1,4,4))
            self.assertEqual(d["vbar"].shape,(1,3,5))
            np.testing.assert_allclose(d["temp"][:],17.5,atol=1e-6)
            np.testing.assert_allclose(d["salt"][:],34.3,atol=1e-5)
            np.testing.assert_allclose(d["zeta"][:],.12,atol=1e-6)
            np.testing.assert_allclose(d["u"][:],expected_u,atol=1e-6)
            np.testing.assert_allclose(d["v"][:],expected_v,atol=1e-6)
            np.testing.assert_allclose(d["ubar"][:],expected_u,atol=1e-6)
            np.testing.assert_allclose(d["vbar"][:],expected_v,atol=1e-6)
            np.testing.assert_allclose(d["dye_01"][:],0)
            self.assertTrue(d.getncattr("source_time").startswith("2018-01-02T12:00"))
        with Dataset(self.outputs["bry"]) as d:
            for side,axis in (("south","xi_rho"),("north","xi_rho"),
                              ("west","eta_rho"),("east","eta_rho")):
                self.assertEqual(d["zeta_"+side].dimensions,("zeta_time",axis))
                np.testing.assert_allclose(d["zeta_"+side][:],.12,atol=1e-6)
                np.testing.assert_allclose(d["temp_"+side][:],17.5,atol=1e-6)
                np.testing.assert_allclose(d["salt_"+side][:],34.3,atol=1e-5)
                np.testing.assert_allclose(d["u_"+side][:],expected_u,atol=1e-6)
                np.testing.assert_allclose(d["v_"+side][:],expected_v,atol=1e-6)
                np.testing.assert_allclose(d["ubar_"+side][:],expected_u,atol=1e-6)
                np.testing.assert_allclose(d["vbar_"+side][:],expected_v,atol=1e-6)
            self.assertEqual(len(d.dimensions["zeta_time"]),2)
            self.assertTrue(np.all(np.diff(d["zeta_time"][:])>0))
            self.assertTrue(d.getncattr("source_time_start").startswith("2018-01-02T12:00"))
        with Dataset(self.outputs["atm"]) as d:
            self.assertEqual(d["Uwind"].shape,(73,4,5))
            for name,expected in (("Uwind",3.),("Vwind",1.),("Pair",1013.),
                                  ("Tair",17.),("Qair",60.),("rain",1e-6)):
                np.testing.assert_allclose(d[name][:],expected,atol=1e-5)
            # The downloader's already-normalized EminusP is SIGNED.
            np.testing.assert_allclose(d["EminusP"][:],-1e-6,atol=1e-12)
            np.testing.assert_allclose(d["swflux"][:],-1e-6,atol=1e-12)
        with Dataset(self.outputs["rad"]) as d:
            self.assertEqual(d["swrad"].shape,(73,4,5))
            for name,expected in (("swrad",200.),("lwrad_down",280.),("lwrad",40.)):
                np.testing.assert_allclose(d[name][:],expected,atol=1e-6)
        with Dataset(self.outputs["tpxo"]) as d:
            self.assertEqual(d["tide_Eamp"].shape,(2,4,5))
            self.assertEqual(d["tide_Cmax"].shape,(2,4,5))
            self.assertEqual(float(d["zero_phase_date"][()]),20180101.)
            self.assertEqual(d["tide_period"][:].tolist(),[12.42,23.93])
            np.testing.assert_allclose(d["tide_Eamp"][:],1.,atol=1e-12)

    def test_era5_signed_e_minus_p_preserved_not_double_subtracted(self):
        self._call(atm,source=self.atm,output=self.outputs["atm"],kind="atm")
        with Dataset(self.outputs["atm"]) as f:
            self.assertTrue(np.all(f["EminusP"][:]<0))
            np.testing.assert_allclose(f["EminusP"][:],-1e-6,atol=1e-12)

    def test_era5_wrong_pre_normalized_flux_units_fail_closed(self):
        with Dataset(self.atm,"a") as f:
            f["EminusP"].units="mm/day"
        with self.assertRaisesRegex(ValueError,"signed m/s"):
            self._call(atm,source=self.atm,output=self.outputs["atm"],kind="atm")
        self.assertFalse(self.outputs["atm"].exists())

    def test_tpxo_incomplete_uv_constituents_are_rejected_without_zero_fabrication(self):
        with Dataset(self.tpxo,"a") as f:
            f.renameVariable("tide_Cphase","SYNTHETIC_broken_phase")
        with self.assertRaisesRegex(SystemExit,"UV_TIDES requested"):
            self._call(tides,source=self.tpxo,output=self.outputs["tpxo"],kind="tpxo")
        self.assertFalse(self.outputs["tpxo"].exists())

    def test_era5_hourly_values_are_not_time_averaged_away(self):
        with Dataset(self.atm,"a") as f:
            f["Pair"][1,:,:]=1009.
        self._call(atm,source=self.atm,output=self.outputs["atm"],kind="atm")
        with Dataset(self.outputs["atm"]) as f:
            np.testing.assert_allclose(f["Pair"][0],1013.,atol=1e-6)
            np.testing.assert_allclose(f["Pair"][1],1009.,atol=1e-6)
            self.assertEqual(len(f.dimensions["pair_time"]),73)

    def test_era5_radiation_hourly_values_do_not_get_reaccumulated(self):
        with Dataset(self.rad,"a") as f:
            f["swrad"][1,:,:]=350.
        self._call(rad,source=self.rad,output=self.outputs["rad"],kind="rad")
        with Dataset(self.outputs["rad"]) as f:
            np.testing.assert_allclose(f["swrad"][0],200.,atol=1e-6)
            np.testing.assert_allclose(f["swrad"][1],350.,atol=1e-6)
            self.assertEqual(len(f.dimensions["srf_time"]),73)


if __name__=="__main__":
    unittest.main()
