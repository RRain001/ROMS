"""Synthetic locality / mask / I3 slope safety checks (not real science)."""
from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
import numpy as np
from netCDF4 import Dataset
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"nesting"),str(ROOT/"tests")]
from test_es3k_core_bathymetry_smoothing import make_fixture,VERTICAL
from es3k_local_slope_projection import local_log_depth_projection,local_slope_candidate
from es3k_core_bathymetry_smoothing import adjacent_rx0

class LocalDepthTest(unittest.TestCase):
    def test_repair_only_problematic_edges(self):
        h=np.full((21,23),100.,dtype=float)
        wet=np.ones(h.shape,bool)
        h[10,10]=2800.
        before=h.copy()
        after,n=local_log_depth_projection(h,wet,target_rx0=.35,max_sweeps=500)
        self.assertLessEqual(adjacent_rx0(after,wet),.35)
        self.assertGreater(n,0)
        np.testing.assert_array_equal(after[:2],before[:2])
        self.assertEqual(after[0,0],before[0,0])
        self.assertLess(np.count_nonzero(np.abs(after-before)>1.e-9),50)
    def test_fails_closed_when_sweeps_insufficient(self):
        h=np.ones((9,9))*100
        h[4,4]=7000
        with self.assertRaisesRegex(ValueError,"failed"):
            local_log_depth_projection(h,np.ones(h.shape,bool),
                                       target_rx0=.2,max_sweeps=1)
    def test_approved_core_file_kept_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/"src.nc";dst=root/"out.nc";report=root/"report.json"
            make_fixture(src)
            with Dataset(src,"r+") as ds:
                h=ds["h"][:]
                h[:]=150.
                ds["h"][:]=h
            before=src.read_bytes()
            result=local_slope_candidate(src,dst,report,vertical=VERTICAL,targets=(.35,))
            self.assertEqual(result["status"],"LOCAL_ES3K_CORE_SLOPE_STATIC_PASS_PHYSICS_NOT_RUN")
            self.assertEqual(src.read_bytes(),before)
            self.assertEqual(result["selected"]["sweeps"],0)
            self.assertEqual(json.loads(report.read_text())["ROMS_physics"],"NOT_RUN")
            with Dataset(src) as x,Dataset(dst) as y:
                for name in ("mask_rho","pm","pn","angle","excluded_ocean_component_rho"):
                    np.testing.assert_array_equal(x[name][:],y[name][:])
    def test_rejects_unapproved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/"src.nc"
            make_fixture(src)
            with Dataset(src,"r+") as ds:ds.grid_id="NOT_ES3K"
            with self.assertRaisesRegex(ValueError,"expected filtered"):
                local_slope_candidate(src,root/"out.nc",root/"report.json",vertical=VERTICAL)
            self.assertFalse((root/"out.nc").exists())

if __name__=="__main__":
    unittest.main()
