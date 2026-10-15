"""Offline-only bounded GLORYS micro subset safety and staged CF NetCDF tests."""
from __future__ import annotations

import json
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from netCDF4 import Dataset

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"nesting"))
from japan_sea_glorys_micro_plan import (
    MAX_SAVED_FILE_BYTES, TEST_BOUNDS, SOURCE_VARIABLES_3D,
    SOURCE_VARIABLES_2D, plan,validate_small_plan,
    audit_downloaded_sample,execute_single_micro_download,main)


def synthetic_tiny_glorys_fixture(path:Path):
    """Synthetic schema fixture, expressly NOT a true Marine download."""
    with Dataset(path,"w") as ds:
        ds.setncattr("source_status","SYNTHETIC_SCHEMA_ONLY")
        for axis,size in (("time",3),("depth",4),("latitude",4),("longitude",4)):
            ds.createDimension(axis,size)
        t=ds.createVariable("time","f8",("time",))
        t.units="hours since 2018-01-01 00:00:00"
        t.calendar="gregorian"
        t[:]=[12,36,60]
        ds.createVariable("depth","f8",("depth",))[:]=[.5,5.,50.,200.]
        ds.createVariable("latitude","f8",("latitude",))[:]=[36.8,36.9,37.,37.1]
        ds.createVariable("longitude","f8",("longitude",))[:]=[129.8,129.9,130.,130.1]
        for name in SOURCE_VARIABLES_3D+SOURCE_VARIABLES_2D:
            dims=(("time","depth","latitude","longitude")
                  if name in SOURCE_VARIABLES_3D
                  else ("time","latitude","longitude"))
            var=ds.createVariable(name,"f4",dims,fill_value=np.float32(1e35))
            var.units=("degrees_C" if name=="thetao" else
                       "1e-3" if name=="so" else
                       "m" if name=="zos" else "m/s")
            var[:]=15. if name=="thetao" else .1


class GLORYSMicroSampleContract(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.sample=self.root/"SYNTHETIC_not_reanalysis.nc"
        synthetic_tiny_glorys_fixture(self.sample)

    def test_exact_small_bbox_window_depth_and_variable_list(self):
        cfg=validate_small_plan(plan())
        self.assertEqual(cfg["longitude_latitude_bbox"],[129.75,130.25,36.75,37.25])
        self.assertEqual(cfg["requested_days"],2)
        self.assertEqual(cfg["max_depth_m"],300.)
        self.assertEqual(cfg["all_variables"],["thetao","so","uo","vo","zos"])
        self.assertLess(cfg["max_accepted_output_file_bytes"],6*1024*1024)
        self.assertTrue(cfg["no_full_ES3K_download"])
        self.assertTrue(cfg["no_roms_integration"])

    def test_real_case_glorys_config_loads_through_existing_no_nesting_loader(self):
        # Launch fresh process: the shared case context is computed at
        # module import time. Do not leak another test's current-case env.
        import subprocess
        env=os.environ.copy()
        env["ROMS_CASE_NAME"]="JAPAN_SEA"
        repo_root=ROOT.parents[1]
        script=(
            "import sys;"
            "sys.path.insert(0,'ROMS_Nesting/Data_pre/core');"
            "from ocean_source_utils import load_glorys_config;"
            "a=load_glorys_config();"
            "assert a['dataset_id_daily']=='cmems_mod_glo_phy_my_0.083deg_P1D-m';"
            "assert a['variables_3d']==['thetao','so','uo','vo'];"
            "assert a['variables_2d']==['zos'];"
            "assert a['boundary_download_strategy']=='edge_bands';"
            "assert a['configuration_status']=='SOURCE_METADATA_ONLY_NO_PRODUCTION_YEAR_APPROVED'"
        )
        result=subprocess.run([sys.executable,"-c",script],
            cwd=repo_root,env=env,check=False,capture_output=True,text=True,
            timeout=12)
        self.assertEqual(result.returncode,0,msg=result.stderr[:800])

    def test_reject_modified_production_scale_bbox_or_time(self):
        for key,bad in (("longitude_latitude_bbox",[121.9,150.4,30.8,52.]),
                        ("test_window_not_production",["2024-01-01","2025-01-01"]),
                        ("max_depth_m",6000),
                        ("all_variables",["thetao"])):
            cfg=plan()
            cfg[key]=bad
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError,"unsafe GLORYS sample"):
                    validate_small_plan(cfg)

    def test_read_tiny_staged_netcdf_schema_not_authenticity(self):
        result=audit_downloaded_sample(self.sample)
        self.assertEqual(result["time_frames"],3)
        self.assertEqual(result["max_source_depth_m"],200.)
        self.assertEqual(len(result["variable_units"]),5)
        self.assertEqual(result["source_authenticity"],"SELF_REPORTED_FILE_METADATA_ONLY")
        self.assertIn("NOT_INDEPENDENTLY_VERIFIED",result["status"])
        self.assertEqual(result["actual_ES3K_or_UD1K_ROMs_integration"],"NOT_RUN")

    def test_reject_bad_geo_extent(self):
        with Dataset(self.sample,"a") as ds:
            ds["longitude"][:]=[145.,145.1,145.2,145.3]
        with self.assertRaisesRegex(ValueError,"central sea sample"):
            audit_downloaded_sample(self.sample)

    def test_reject_missing_ocean_field(self):
        with Dataset(self.sample,"a") as ds:
            ds.renameVariable("vo","broken_vo")
        with self.assertRaisesRegex(ValueError,"missing vo"):
            audit_downloaded_sample(self.sample)

    def test_reject_missing_center_ocean_data(self):
        with Dataset(self.sample,"a") as ds:
            ds["thetao"][0,:,2,2]=ds["thetao"]._FillValue
        with self.assertRaisesRegex(ValueError,"no ocean data"):
            audit_downloaded_sample(self.sample)

    def test_reject_calendar_wrong_time_window(self):
        with Dataset(self.sample,"a") as ds:
            ds["time"][:]=[12+8760.,36+8760.,60+8760.]
        with self.assertRaisesRegex(ValueError,"Jan 2018"):
            audit_downloaded_sample(self.sample)

    def test_reject_large_file_before_any_read(self):
        with self.sample.open("ab") as fd:
            fd.truncate(MAX_SAVED_FILE_BYTES+1)
        with self.assertRaisesRegex(ValueError,"5MiB"):
            audit_downloaded_sample(self.sample)

    def test_no_credentials_means_no_download_attempt(self):
        with patch.dict(os.environ,{
                "COPERNICUSMARINE_SERVICE_USERNAME":"",
                "COPERNICUSMARINE_SERVICE_PASSWORD":""}):
            with self.assertRaisesRegex(ValueError,"CDSAPI_KEY is NOT"):
                execute_single_micro_download(self.root/"real.nc")
        self.assertFalse((self.root/"real.nc").exists())

    def test_default_cli_creates_only_plan_never_real_download(self):
        destination=self.root/"REQUEST_PLAN_NO_DOWNLOAD.json"
        with patch.object(sys,"argv",["program","--plan-json",str(destination)]):
            with patch("japan_sea_glorys_micro_plan.execute_single_micro_download") as real:
                main()
                real.assert_not_called()
        r=json.loads(destination.read_text())
        self.assertEqual(r["mode"],"SMALL_REAL_MARINE_REQUEST_PLAN_NOT_EXECUTED")
        self.assertEqual(r["true_ocean_observations"],"NOT_DOWNLOADED")
        self.assertFalse((self.root/"real.nc").exists())

    def test_cli_existing_plan_is_not_overwritten(self):
        target=self.root/"existing.json"
        target.write_text("existing content")
        with patch.object(sys,"argv",["program","--plan-json",str(target)]):
            with self.assertRaisesRegex(SystemExit,"overwrite"):
                main()
        self.assertEqual(target.read_text(),"existing content")

    def test_real_execute_needs_explicit_output(self):
        with patch.object(sys,"argv",["program","--plan-json",str(self.root/"plan.json"),
                                     "--execute"]):
            with self.assertRaisesRegex(SystemExit,"--output"):
                main()


if __name__=="__main__":
    unittest.main()
