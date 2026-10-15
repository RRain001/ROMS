"""Fail-closed UD1K bry_time / ES3K ocean_time epoch bridge + true source wet-face checks.

Small synthetic history tests only, no real ES3K ROMS history generated.
"""
from __future__ import annotations

from datetime import datetime,timedelta
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from netCDF4 import Dataset,date2num

ROOT=Path(__file__).resolve().parents[1]
for part in ("nesting","tests"):
    p=str(ROOT/part)
    if p not in sys.path:sys.path.insert(0,p)

from ud1k_cf_time_bridge import bridge_target_to_parent_cf_time
from ud1k_boundary_remap_preview import prepare_boundary_preview
from ud1k_bry_schema_contract import write_synthetic_schema_fixture
from test_ud1k_parent_history_contract import synthetic_parent_grid,synthetic_parent_history
from test_ud1k_bry_schema_contract import child_grid
from test_ud1k_boundary_remap_preview import maps_from_synthetic_grid

PARENT_UNITS="seconds since 2025-01-01 00:00:00"
MJD_UNITS="days since 1858-11-17 00:00:00"
HOURS_UNITS="hours since 2024-12-31 00:00:00"
BASIS=datetime(2025,1,1)


def target_mjd():
    return np.asarray(date2num([
        BASIS,BASIS+timedelta(minutes=30),
        BASIS+timedelta(hours=1)],units=MJD_UNITS,calendar="gregorian"),dtype=float)


class ExplicitCFTimeBridge(unittest.TestCase):
    def test_true_mjd_days_to_source_seconds(self):
        report=bridge_target_to_parent_cf_time(target_mjd(),np.array([0.,3600.]),
            parent_units=PARENT_UNITS,parent_calendar="standard",
            target_units=MJD_UNITS,target_calendar="gregorian")
        np.testing.assert_allclose(report["parent_time_values"],[0,1800,3600],
                                   atol=2e-6,rtol=0)
        np.testing.assert_allclose(report["bry_time_values"],target_mjd(),atol=0)
        self.assertEqual(report["time_axis_mapping_status"],
                         "TARGET_CF_EPOCH_TO_SOURCE_HISTORY_EPOCH_CONVERTED")
        self.assertEqual(report["parent_max_gap_hours"],1)
        self.assertEqual(report["bry_time_units"],MJD_UNITS)

    def test_source_hour_and_target_mjd_conversion(self):
        parent=np.array([24.,25.])
        r=bridge_target_to_parent_cf_time(target_mjd(),parent,
            parent_units=HOURS_UNITS,parent_calendar="gregorian",
            target_units=MJD_UNITS,target_calendar="standard")
        np.testing.assert_allclose(r["parent_time_values"],[24.,24.5,25.],atol=1e-8)

    def test_target_mjd_cannot_be_used_as_source_seconds(self):
        with self.assertRaisesRegex(ValueError,"outside parent"):
            bridge_target_to_parent_cf_time(target_mjd(),[0.,3600.],
                                            parent_units=PARENT_UNITS)

    def test_reject_unsupported_calendar_crossing(self):
        with self.assertRaisesRegex(ValueError,"calendars differ"):
            bridge_target_to_parent_cf_time(target_mjd(),[0.,3600.],
                parent_units=PARENT_UNITS,parent_calendar="standard",
                target_units=MJD_UNITS,target_calendar="360_day")

    def test_source_gap_over_three_hours_is_explicit_failure(self):
        with self.assertRaisesRegex(ValueError,"gap"):
            bridge_target_to_parent_cf_time([0.,7200.],[0.,14400.],
                parent_units=PARENT_UNITS,max_gap_hours=3.)

    def test_source_gap_explicit_override_allowed_with_report(self):
        r=bridge_target_to_parent_cf_time([0.,7200.],[0.,14400.],
             parent_units=PARENT_UNITS,max_gap_hours=4.)
        self.assertEqual(r["parent_max_gap_hours"],4.)
        np.testing.assert_allclose(r["parent_time_values"],[0,7200])

    def test_no_calendar_without_units(self):
        with self.assertRaisesRegex(ValueError,"without target_units"):
            bridge_target_to_parent_cf_time([0.,1800.],[0.,3600.],
                parent_units=PARENT_UNITS,target_calendar="gregorian")

    def test_missing_target_calendar_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"calendar must be explicit"):
            bridge_target_to_parent_cf_time(target_mjd(),[0.,3600.],
                parent_units=PARENT_UNITS,target_units=MJD_UNITS)

    def test_target_date_outside_history_range_rejected(self):
        out=np.asarray(date2num([BASIS+timedelta(days=2),
              BASIS+timedelta(days=3)],MJD_UNITS,calendar="gregorian"))
        with self.assertRaisesRegex(ValueError,"outside parent"):
            bridge_target_to_parent_cf_time(out,[0.,3600.],parent_units=PARENT_UNITS,
                target_units=MJD_UNITS,target_calendar="gregorian")

    def test_nonmonotone_target_times_rejected(self):
        with self.assertRaisesRegex(ValueError,"strictly increasing"):
            bridge_target_to_parent_cf_time([0.,0.],[0.,3600.],
                                            parent_units=PARENT_UNITS)


class SourcePreviewTimeAndWetFace(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root=Path(t.name)
        self.parent=root/"SYNTHETIC_es3k_grid.nc"
        self.history=root/"SYNTHETIC_es3k_his.nc"
        self.child=root/"SYNTHETIC_ud1k_grid.nc"
        synthetic_parent_grid(self.parent)
        synthetic_parent_history(self.history,n=3)
        child_grid(self.child)
        with Dataset(self.child,"a") as d:
            d.createVariable("angle","f8",("eta_rho","xi_rho"))[:]=0.
        with Dataset(self.parent,"a") as d:
            d["angle"][:]=0.
        self.rho,self.faces=maps_from_synthetic_grid(self.child)
        self.params={"hc":50.,"theta_s":5.,"theta_b":1.,
                     "Vtransform":2,"Vstretching":4}

    def preview(self,times=None,**kwargs):
        return prepare_boundary_preview(
            self.parent,self.history,self.child,self.rho,self.faces,
            target_mjd() if times is None else times,
            child_n=4,child_params=self.params,**kwargs)

    def test_actual_interpolation_with_different_source_and_bry_time_epochs(self):
        with Dataset(self.history,"a") as ds:
            ds["temp"][1]=20.
            ds["u"][1]=.25
            ds["ubar"][1]=.25
        fields,report=self.preview(
            target_time_units=MJD_UNITS,target_time_calendar="gregorian")
        self.assertAlmostEqual(fields["south"]["temp"][1,2,2],19.,places=9)
        self.assertAlmostEqual(fields["south"]["u"][1,2,2],.20,places=9)
        self.assertEqual(report["source_native_donor_support"]
                         ["actual_parent_wet_UV_face_support"],
                         "PASS_AGAINST_SUPPLIED_PARENT_MASK")
        self.assertEqual(report["source_target_CF_time_bridge"]["bry_time_units"],
                         MJD_UNITS)
        np.testing.assert_allclose(
            report["source_target_CF_time_bridge"]["parent_time_values"],
            [0.,1800.,3600.],atol=2e-6)
        # Roundtrip exactly what an actual target bry_time would express:
        # values in MJD *days*, rather than numeric parent seconds.
        out=self.child.parent/"SYNTHETIC_only_MJD_bry.nc"
        result=write_synthetic_schema_fixture(
            self.child,out,fields,target_mjd(),n=4,time_units=MJD_UNITS)
        self.assertEqual(result["complete_field_variables"],28)
        with Dataset(out) as ds:
            self.assertEqual(ds["bry_time"].units,MJD_UNITS)
            np.testing.assert_allclose(ds["bry_time"][:],target_mjd(),atol=0)
            np.testing.assert_allclose(ds["temp_south"][1,2,2],19.,atol=1e-5)

    def test_missing_native_source_v_face_fails_even_if_json_flag_claims_true(self):
        with Dataset(self.parent,"a") as ds:
            wet=np.asarray(ds["mask_rho"][:],dtype=bool)
            wet[0,2]=False
            wet[2,2]=False
            ds["mask_rho"][:]=wet
            ds["mask_u"][:]=wet[:,:-1]&wet[:,1:]
            ds["mask_v"][:]=wet[:-1,:]&wet[1:,:]
        with self.assertRaisesRegex(ValueError,"no actual wet face"):
            self.preview(target_time_units=MJD_UNITS,
                         target_time_calendar="gregorian")

    def test_unphysical_child_grid_mask_is_not_allowed_even_with_accepted_maps(self):
        with Dataset(self.child,"a") as ds:
            ds["mask_u"][0,0]=1-ds["mask_u"][0,0]
        with self.assertRaisesRegex(ValueError,"staggered wet face mask"):
            self.preview(target_time_units=MJD_UNITS,
                         target_time_calendar="gregorian")

    def test_gap_over_3h_rejected_before_interpolating_any_parent_fields(self):
        with Dataset(self.history,"a") as ds:
            ds["ocean_time"][:]=[0,4*3600.]
        with self.assertRaisesRegex(ValueError,"time gap"):
            self.preview(target_time_units=MJD_UNITS,
                         target_time_calendar="gregorian")

    def test_wrong_bry_epoch_rejected_not_treated_as_source_time(self):
        with self.assertRaisesRegex(ValueError,"outside parent"):
            self.preview(target_time_units="days since 2000-01-01 00:00:00",
                         target_time_calendar="gregorian")


if __name__=="__main__":
    unittest.main()
