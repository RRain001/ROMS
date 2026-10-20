"""Tiny offline GLORYS / ERA5 / TPXO staged NetCDF contract regressions."""
from __future__ import annotations

from datetime import datetime,timedelta
from pathlib import Path
import json
import sys
import tempfile
import unittest

import numpy as np
from netCDF4 import Dataset,date2num

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from japan_sea_forcing_micro_preflight import audit_forcing


TIME_EPOCH="hours since 2018-01-01 00:00:00"
START=datetime(2018,1,2)
STOP=datetime(2018,1,3)
SITE=(130.,37.)


def _rect(ds,*,ocean:bool=False):
    lat,lon=("latitude","longitude") if ocean else ("lat","lon")
    ds.createDimension(lat,3)
    ds.createDimension(lon,4)
    ds.createVariable(lat,"f8",(lat,))[:]=[36.,37.,38.]
    ds.createVariable(lon,"f8",(lon,))[:]=[129.,130.,131.,132.]
    return lat,lon


def synthetic_ocean(path:Path)->None:
    with Dataset(path,"w") as f:
        lat,lon=_rect(f,ocean=True)
        f.createDimension("time",None)
        f.createDimension("depth",3)
        t=f.createVariable("time","f8",("time",))
        t.units=TIME_EPOCH
        t.calendar="gregorian"
        t[:]=[12,36,60,84]
        f.createVariable("depth","f8",("depth",))[:]=[0.5,50,200]
        for name,dim,val,units in (
            ("thetao",("time","depth",lat,lon),17.5,"degrees_C"),
            ("so",("time","depth",lat,lon),34.3,"1e-3"),
            ("uo",("time","depth",lat,lon),.17,"m/s"),
            ("vo",("time","depth",lat,lon),-.04,"m/s"),
            ("zos",("time",lat,lon),.12,"m")):
            var=f.createVariable(name,"f4",dim,fill_value=1e35)
            var.units=units
            var[:]=val
        f["thetao"][:,0,0,0]=f["thetao"]._FillValue


def synthetic_era5(path:Path,*,radiation:bool=False)->None:
    with Dataset(path,"w") as f:
        lat,lon=_rect(f)
        f.createDimension("time",None)
        t=f.createVariable("time","f8",("time",))
        t.units=TIME_EPOCH
        t.calendar="gregorian"
        t[:]=np.arange(73,dtype=float)
        fields=(("swrad",200.,"W m-2"),
                ("lwrad_down",280.,"W m-2"),("lwrad",40.,"W m-2")) if radiation else (
                ("Uwind",3.,"m s-1"),("Vwind",1.,"m s-1"),
                ("Pair",1013.,"mbar"),("Tair",17.,"Celsius"),
                ("Qair",60.,"percent"),("rain",1e-6,"m s-1"),
                ("EminusP",-1e-6,"m s-1"))
        for name,value,units in fields:
            var=f.createVariable(name,"f4",("time",lat,lon),fill_value=1e35)
            var.units=units
            var[:]=value


def synthetic_tpxo(path:Path)->None:
    with Dataset(path,"w") as f:
        lat,lon=_rect(f)
        f.createDimension("tide_period",2)
        period=f.createVariable("tide_period","f8",("tide_period",))
        period.units="hours"
        period[:]=[12.42,23.93]
        for name in ("tide_Eamp","tide_Ephase","tide_Cmax","tide_Cmin",
                     "tide_Cangle","tide_Cphase"):
            f.createVariable(name,"f8",("tide_period",lat,lon))[:]=(
                1.0 if name.endswith("amp") else 0.15)


class OfflineExternalForcingMicro(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.ocean=self.root/"SYNTHETIC_GLORYS_daily.nc"
        self.atm=self.root/"SYNTHETIC_ERA5_atm_hourly.nc"
        self.rad=self.root/"SYNTHETIC_ERA5_rad_hourly.nc"
        self.tide=self.root/"SYNTHETIC_TPXO9_harmonics.nc"
        synthetic_ocean(self.ocean)
        synthetic_era5(self.atm)
        synthetic_era5(self.rad,radiation=True)
        synthetic_tpxo(self.tide)

    def run_audit(self,**kwargs):
        options={"start":START,"stop":STOP,"lon":SITE[0],"lat":SITE[1]}
        options.update(kwargs)
        return audit_forcing(self.ocean,self.atm,self.rad,self.tide,**options)

    def test_all_three_public_source_interfaces_and_time_brackets(self):
        r=self.run_audit()
        self.assertEqual(r["status"],"OFFLINE_STAGED_SOURCE_INTERFACE_MICRO_PREFLIGHT_PASS")
        self.assertEqual(set(r["source_interfaces"]["ocean"]["fields"]),
                         {"thetao","so","uo","vo","zos"})
        self.assertEqual(r["source_interfaces"]["ocean"]["time"]["largest_gap_hours"],24.)
        self.assertEqual(r["source_interfaces"]["atmosphere"]["time"]["largest_gap_hours"],1.)
        self.assertEqual(r["source_interfaces"]["radiation"]["time"]["largest_gap_hours"],1.)
        self.assertEqual(r["source_interfaces"]["tides"]["tide_constituents"],2)
        self.assertEqual(r["source_interfaces"]["tides"]["UV_current_representation"],
                         "amplitude_phase")
        self.assertEqual(r["download_or_api_calls"],"NONE")
        self.assertEqual(r["real_ES3K_history"],"NOT_RUN")

    def test_reject_yearlong_or_undefined_window(self):
        with self.assertRaisesRegex(ValueError,"72 hour"):
            self.run_audit(stop=START+timedelta(days=366))
        with self.assertRaisesRegex(ValueError,"72 hour"):
            self.run_audit(stop=START)

    def test_reject_ocean_gap_over_36_hours(self):
        with Dataset(self.ocean,"a") as ds:
            ds["time"][:]=[0,12,60,84]
        with self.assertRaisesRegex(ValueError,"temporal gap"):
            self.run_audit()

    def test_reject_era5_missing_time_coverage(self):
        with Dataset(self.atm,"a") as ds:
            ds["time"][:]=np.arange(73,dtype=float)+30
        with self.assertRaisesRegex(ValueError,"not bracket"):
            self.run_audit()

    def test_reject_era5_radiation_missing_key(self):
        with Dataset(self.rad,"a") as ds:
            ds.renameVariable("swrad","bad_swrad")
        with self.assertRaisesRegex(ValueError,"missing expected swrad"):
            self.run_audit()

    def test_reject_unconverted_surface_pressure_units(self):
        with Dataset(self.atm,"a") as ds:
            ds["Pair"].units="Pa"
        with self.assertRaisesRegex(ValueError,"Pair: unexpected units"):
            self.run_audit()

    def test_reject_nonmonotonic_latitude(self):
        with Dataset(self.ocean,"a") as ds:
            ds["latitude"][:]=[36,38,37]
        with self.assertRaisesRegex(ValueError,"sorted finite"):
            self.run_audit()

    def test_reject_point_outside_requested_spatial_subset(self):
        with self.assertRaisesRegex(ValueError,"not within source coordinate extent"):
            self.run_audit(lon=140.)

    def test_reject_missing_uv_tidal_current_harmonics(self):
        with Dataset(self.tide,"a") as ds:
            ds.renameVariable("tide_Cphase","broken_Cphase")
        with self.assertRaisesRegex(ValueError,"missing four current harmonic"):
            self.run_audit()

    def test_ocean_missing_land_value_does_not_block_nearby_valid_wet(self):
        result=self.run_audit()
        self.assertTrue(result["source_interfaces"]["ocean"]["fields"]["thetao"]
                        ["near_site_sample_finite"])

    def test_reject_missing_ocean_temperature_at_entire_micro_patch(self):
        with Dataset(self.ocean,"a") as ds:
            ds["thetao"][:]=ds["thetao"]._FillValue
        with self.assertRaisesRegex(ValueError,"no finite values"):
            self.run_audit()

    def test_explicit_mock_source_stage_contract_no_network(self):
        # Source documents need no API credentials, no Copernicus requests.
        r=self.run_audit()
        self.assertEqual(r["run_scope"],"ONE_INTERIOR_POINT_MAX_72H_NOT_FULL_ES3K_DOMAIN")
        json.dumps(r)


if __name__=="__main__":
    unittest.main()
