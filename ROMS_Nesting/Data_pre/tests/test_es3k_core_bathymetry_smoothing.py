"""I3 ES3K slope smoothing contract (synthetic only): no source mutation."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from netCDF4 import Dataset

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"nesting"))
from es3k_core_bathymetry_smoothing import (
    adjacent_rx0, smooth_once, smooth_core_candidate)

VERTICAL=json.loads((ROOT.parent/"configs/es3k_i3_vertical_candidate.json").read_text())


def make_fixture(path: Path) -> None:
    ny,nx=15,19
    wet=np.zeros((ny,nx),dtype='i1')
    wet[1:14,1:18]=1
    depth=np.full((ny,nx),10.,dtype='f8')
    depth[wet==1]=150.
    depth[5:10,9:14]=3500.
    depth[2:4,3:7]=800.
    with Dataset(path,"w",format="NETCDF4") as ds:
        ds.grid_id="ES3K"
        ds.geometry_status="CANDIDATE_NOT_VALIDATED_FOR_ROMS"
        ds.domain_mask_policy="ONLY_JAPAN_BASIN_CONNECTED_COMPONENT_NO_FAKE_LAND"
        ds.synthetic_test_only="TRUE"
        ds.geometry_reference_status="SYNTHETIC_ONLY"
        for name,size in (("eta_rho",ny),("xi_rho",nx),
                          ("eta_u",ny),("xi_u",nx-1),
                          ("eta_v",ny-1),("xi_v",nx),
                          ("eta_psi",ny-1),("xi_psi",nx-1)):
            ds.createDimension(name,size)
        for name,arr in (("h",depth),("mask_rho",wet),
                         ("pm",np.full((ny,nx),1/3000)),
                         ("pn",np.full((ny,nx),1/3000)),
                         ("angle",np.zeros((ny,nx))),
                         ("excluded_ocean_component_rho",np.zeros((ny,nx),dtype='i1'))):
            dtype='i1' if name.startswith("mask") or name.startswith("excluded") else 'f8'
            ds.createVariable(name,dtype,("eta_rho","xi_rho"))[:]=arr


class CoreSmoothingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.source=self.base/"raw.nc"
        self.output=self.base/"candidate.nc"
        self.report=self.base/"candidate.json"
        make_fixture(self.source)

    def test_wet_only_smoothing_preserves_land(self):
        h=np.array([[10.,100.,500.],[10.,3000.,10.],[100.,100.,10.]])
        wet=np.array([[0,1,1],[0,1,1],[0,1,0]],bool)
        result=smooth_once(h,wet,blend=.85,min_depth_m=10.)
        np.testing.assert_array_equal(result[~wet],h[~wet])
        self.assertLess(adjacent_rx0(result,wet),adjacent_rx0(h,wet))

    def test_slope_vertical_and_file_invariance(self):
        original=self.source.read_bytes()
        record=smooth_core_candidate(self.source,self.output,self.report,
                                      vertical=VERTICAL,max_iterations=120)
        self.assertEqual(record["status"],"ES3K_CORE_SLOPE_PRELIMINARY_PASS_ONLY")
        self.assertLessEqual(record["rx0_final"],.35)
        self.assertLessEqual(record["rx1_final"],8.0)
        self.assertLess(abs(record["volume_change_fraction"]),.02)
        self.assertEqual(self.source.read_bytes(),original)
        self.assertTrue(record["original_grid_unchanged"])
        with Dataset(self.source) as src,Dataset(self.output) as out:
            for name in ("mask_rho","pm","pn","angle",
                         "excluded_ocean_component_rho"):
                np.testing.assert_array_equal(src[name][:],out[name][:])
            self.assertEqual(out.bathymetry_smoothing_status,
              "ES3K_CORE_I3_SLOPE_CANDIDATE_NOT_ROMs_PHYSICS_PASS")
            self.assertEqual(record["wet_rho_points"],221)
            self.assertNotEqual(float(out["h"][7,11]),float(src["h"][7,11]))
        self.assertEqual(json.loads(self.report.read_text())["I3_scientific_acceptance"],
                         "NOT_ACCEPTED")

    def test_fail_closed_no_output_on_max_iterations(self):
        with self.assertRaisesRegex(ValueError,"NOT_MET"):
            smooth_core_candidate(self.source,self.output,self.report,
                                  vertical=VERTICAL,max_iterations=1)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())

    def test_reject_original_or_unapproved_source(self):
        with self.assertRaisesRegex(ValueError,"overwrite"):
            smooth_core_candidate(self.source,self.source,self.report,vertical=VERTICAL)
        with Dataset(self.source,"r+") as ds:
            ds.domain_mask_policy="UNFILTERED"
        with self.assertRaisesRegex(ValueError,"core-component-only"):
            smooth_core_candidate(self.source,self.output,self.report,vertical=VERTICAL)
        self.assertFalse(self.output.exists())

    def test_reject_wrong_vertical_and_volume_budget(self):
        with self.assertRaisesRegex(ValueError,"41-layer"):
            smooth_core_candidate(self.source,self.output,self.report,
                                  vertical={**VERTICAL,"N":40})
        with self.assertRaisesRegex(ValueError,"volume"):
            smooth_core_candidate(self.source,self.output,self.report,
                                  vertical=VERTICAL,max_volume_change_fraction=1e-8)
        self.assertFalse(self.output.exists())

if __name__=="__main__":
    unittest.main()
