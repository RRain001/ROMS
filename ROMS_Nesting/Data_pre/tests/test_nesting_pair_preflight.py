"""I3/I5 synthetic ES3K→UD1K containment gate, not dynamic nesting PASS."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from netCDF4 import Dataset
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"nesting"))
from validate_nesting_geometries import check_pair
from bathymetry_grid import build_grid
from test_bathymetry_grid import ES,make_fixture


CHILD={
    "grid_id":"UD1K","geometry_status":"CANDIDATE_APPROXIMATE",
    "geometry_type":"axis_aligned_lonlat",
    "lon_min":131.25,"lon_max":131.34,
    "lat_min":37.59,"lat_max":37.66,
    "resolution_m":1000,
}
OUTSIDE={
    **CHILD, "lon_min":131.70, "lon_max":131.79,
    "lat_min":37.59,"lat_max":37.66
}


class ParentChildTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="roms_pair_")
        self.addCleanup(temp.cleanup)
        self.tmp=Path(temp.name)
        source=self.tmp/"bathy.nc"
        make_fixture(source)
        self.parent=self.tmp/"parent.nc"
        self.child=self.tmp/"child.nc"
        self.outside=self.tmp/"outside.nc"
        for path,config in ((self.parent,ES),(self.child,CHILD),(self.outside,OUTSIDE)):
            build_grid(config,source,path,
                       allow_gebco_only_mask=True,synthetic_fixture=True)

    def test_containment_with_internal_parent_margin(self):
        report=check_pair(self.parent,self.child,margin_parent_rho_cells=2)
        self.assertEqual(report["status"],"PASS_PRELIMINARY_ONLY")
        self.assertGreater(report["buffered_parent_boundary_gap_min_m"],1000)
        self.assertGreater(report["wet_boundary_points_checked"],0)
        self.assertLess(report["farthest_nearest_parent_wet_m"],
                        report["wet_parent_search_cells"]*report["parent_nominal_cell_m"])
        self.assertEqual(report["physics_validation"],"NOT_RUN")
        self.assertEqual(report["vertical_remapping"],"NOT_RUN")
        self.assertEqual(report["conservative_boundary_fluxes"],"NOT_RUN")
        self.assertEqual(report["parent_synthetic"],"TRUE")

    def test_bbox_overlap_not_enough_for_rotated_grid(self):
        fail=check_pair(self.parent,self.outside,margin_parent_rho_cells=2)
        self.assertEqual(fail["status"],"FAIL")
        self.assertIn("buffered ES3K footprint",fail["reason"])

    def test_missing_parent_wet_near_child_rejected(self):
        with Dataset(self.parent,"a") as ds:
            mask=ds["mask_rho"][:]
            mask[:]=0
            mask[0,0]=1
            ds["mask_rho"][:]=mask
        fail=check_pair(self.parent,self.child,margin_parent_rho_cells=2)
        self.assertEqual(fail["status"],"FAIL")
        self.assertIn("lacks nearby parent wet",fail["reason"])

    def test_wrong_role_and_too_large_margin_rejected(self):
        with self.assertRaisesRegex(ValueError,"expected ES3K"):
            check_pair(self.child,self.parent)
        with self.assertRaisesRegex(ValueError,"too small"):
            check_pair(self.parent,self.child,margin_parent_rho_cells=6)

    def test_cli_generates_unambiguous_report(self):
        script=ROOT/"scripts/nesting/validate_nesting_geometries.py"
        output=self.tmp/"pair.json"
        args=[sys.executable,str(script),"--parent-grid",str(self.parent),
              "--child-grid",str(self.child),"--output-json",str(output)]
        process=subprocess.run(args,text=True,capture_output=True)
        self.assertEqual(process.returncode,0,process.stderr)
        report=json.loads(output.read_text())
        self.assertEqual(report["status"],"PASS_PRELIMINARY_ONLY")
        bad=subprocess.run([sys.executable,str(script),
                            "--parent-grid",str(self.parent),
                            "--child-grid",str(self.outside)],
                           text=True,capture_output=True)
        self.assertEqual(bad.returncode,2)

if __name__=="__main__":
    unittest.main()
