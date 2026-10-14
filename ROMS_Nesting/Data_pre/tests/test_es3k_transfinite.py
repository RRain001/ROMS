"""I2 four-corner-constrained ES3K diagnostic mesh regression.

The trial bilinear/AEQD mesh is not accepted if it fails physical
orthogonality, nominal resolution, bathymetry, or dynamics gates.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

import numpy as np
from pyproj import Geod

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"core"))
sys.path.insert(0,str(ROOT/"nesting"))
from es3k_corners import corner_grid,user_corner_inputs
from bathymetry_grid import make_geometry
from test_es3k_user_corners import USER_PATH

G=Geod(ellps="WGS84")
CONFIG=ROOT.parent/"configs/es3k_four_corner_candidate.json"


class ES3KTransfinitePilot(unittest.TestCase):
    def setUp(self):
        self.spec=json.loads(CONFIG.read_text())
        self.user=json.loads(USER_PATH.read_text())["user_corners_lat_lon"]

    def test_exact_input_121_9_and_refuse_modified_corners(self):
        self.assertEqual(self.spec["user_corners_lat_lon"],self.user)
        self.assertEqual(user_corner_inputs(self.spec)["W"],(37.821077,121.9))
        changed=json.loads(json.dumps(self.spec))
        changed["user_corners_lat_lon"]["W"][1]=121.0
        with self.assertRaisesRegex(ValueError,"user-supplied corners have changed"):
            corner_grid(changed,sample_scale=20)

    def test_coarse_pilot_cgrid_corners_angle_and_metrics(self):
        geo,nom_x,nom_y,report=corner_grid(self.spec,sample_scale=20)
        rho=geo["lon_rho"]
        self.assertEqual(rho.shape,tuple(report["actual_rho_shape"]))
        self.assertGreater(report["full_estimated_rho_shape"][0],rho.shape[0])
        self.assertGreater(report["full_estimated_rho_shape"][1],rho.shape[1])
        self.assertLess(report["corner_max_wgs84_error_m"],1e-5)
        corners={"W":(0,0),"N":(-1,0),"E":(-1,-1),"S":(0,-1)}
        for key,(j,i) in corners.items():
            self.assertAlmostEqual(geo["lat_rho"][j,i],self.user[key][0],places=9)
            self.assertAlmostEqual(geo["lon_rho"][j,i],self.user[key][1],places=9)
        for name in ("pm","pn","dndx","dmde","angle","f"):
            self.assertEqual(geo[name].shape,rho.shape)
            self.assertTrue(np.isfinite(geo[name]).all())
        self.assertTrue((geo["pm"]>0).all())
        self.assertTrue((geo["pn"]>0).all())
        self.assertEqual(geo["lon_u"].shape,(rho.shape[0],rho.shape[1]-1))
        self.assertEqual(geo["lon_v"].shape,(rho.shape[0]-1,rho.shape[1]))
        self.assertEqual(geo["lon_psi"].shape,(rho.shape[0]-1,rho.shape[1]-1))
        self.assertGreater(report["orthogonality_error_max_deg"],1.0)
        self.assertEqual(report["orthogonality_gate"],"NOT_PASS")
        self.assertGreater(report["geodesic_dx_min_m"],0)
        self.assertGreater(report["geodesic_dy_min_m"],0)
        self.assertEqual(report["nominal_angular_spacing"],"1/36 degree")
        self.assertIn("NOT_EXACT_ANGULAR",report["sampling_interpretation"])
        self.assertEqual(report["ROMS_integration"],"NOT_RUN")

    def test_rejects_failed_grid_before_loading_any_gebco(self):
        from bathymetry_grid import build_grid
        # The intentionally missing GEBCO path should never be opened.
        # A wrong implementation would raise FileNotFoundError instead.
        with self.assertRaisesRegex(ValueError,"ROT-GATE NOT PASS"):
            build_grid(self.spec,
                       Path("/nonexistent/real_GEBCO_2026.nc"),
                       Path("/tmp/ES3K_SHOULD_NOT_EXIST.nc"),
                       allow_gebco_only_mask=True,
                       synthetic_fixture=True)


    def test_fail_closed_geometry_label(self):
        self.assertEqual(self.spec["geometry_status"],"CANDIDATE_APPROXIMATE")
        self.assertEqual(self.spec["status"],"DIAGNOSTIC_TRANSFINITE_PATCH_ONLY_NO_ACCEPTED_GRID")
        self.assertEqual(self.spec["exact_angular_resolution"],
                         "NOT_IMPLEMENTED_METRIC_EQUIVALENT_ONLY")
        wrong={**self.spec,"nominal_resolution_deg":1/40}
        with self.assertRaisesRegex(ValueError,"1/36"):
            corner_grid(wrong,sample_scale=20)
        with self.assertRaises(ValueError):
            corner_grid(self.spec,sample_scale=0)

    def test_production_grid_loader_branch_matches_diagnostic(self):
        # Geometry-only branch intentionally has explicit status.
        geo,dx,dy=make_geometry(self.spec)
        self.assertAlmostEqual(geo["lat_rho"][0,0],37.821077,places=9)
        self.assertAlmostEqual(geo["lon_rho"][0,0],121.9,places=9)
        self.assertTrue(np.isfinite(geo["angle"]).all())
        self.assertGreater(dx,0)
        self.assertGreater(dy,0)


if __name__=="__main__":
    unittest.main()
