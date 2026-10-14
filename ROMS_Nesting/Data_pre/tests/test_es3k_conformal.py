"""ES3K conformal four-corner candidate versus bilinear transfinite baseline.

Tests numerical properties directly on WGS84 geodesics, not projection
conformality alone. A geometric PASS is not a production model approval.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from pyproj import CRS, Transformer, Geod
from shapely.geometry import Polygon

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"nesting"),str(ROOT/"core")]
from bathymetry_grid import make_geometry, build_grid
from es3k_corners import corner_grid
from es3k_conformal import conformal_corner_grid

CONFORMAL=ROOT.parent/"configs/es3k_conformal_candidate.json"
BASE=ROOT.parent/"configs/es3k_four_corner_candidate.json"
UD=ROOT.parent/"configs/ud1k_candidate.json"
GEOD=Geod(ellps="WGS84")


class ES3KConformalPilot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conf=json.loads(CONFORMAL.read_text())
        cls.base=json.loads(BASE.read_text())
        cls.conf_geometry,_,_,cls.conf_report=conformal_corner_grid(
            cls.conf,sample_scale=20)
        cls.base_geometry,_,_,cls.base_report=corner_grid(
            cls.base,sample_scale=20)

    def test_preserves_all_four_user_corner_locations(self):
        report=self.conf_report
        self.assertLess(report["corner_max_wgs84_error_m"],1e-5)
        self.assertEqual(report["corner_input_lat_lon"],
            {"W":[37.821077,121.9],"N":[52.0,141.327943],
             "E":[45.616255,150.4],"S":[30.8,131.471973]})
        vertices={"W":(0,0),"S":(0,-1),"N":(-1,0),"E":(-1,-1)}
        for k,(j,i) in vertices.items():
            self.assertAlmostEqual(
                self.conf_geometry["lat_rho"][j,i],
                report["corner_input_lat_lon"][k][0],places=9)
            self.assertAlmostEqual(
                self.conf_geometry["lon_rho"][j,i],
                report["corner_input_lat_lon"][k][1],places=9)

    def test_improves_wgs84_orthogonality_beyond_baseline(self):
        q=self.conf_report
        baseline=self.base_report
        self.assertEqual(q["orthogonality_gate"],"PRELIMINARY_PASS_ONLY")
        self.assertLess(q["orthogonality_error_max_deg"],1.0)
        self.assertLess(q["orthogonality_error_p95_deg"],.8)
        self.assertGreater(baseline["orthogonality_error_max_deg"],5.0)
        self.assertLess(q["orthogonality_error_max_deg"],
                        baseline["orthogonality_error_max_deg"]/4)
        self.assertGreater(q["polynomial_derivative_min_projected_m"],100)
        self.assertGreater(q["jacobian_min_projected_m2"],0)
        self.assertTrue(q["valid_non_self_intersecting_perimeter"])
        self.assertEqual(q["sampling_interpretation"],
                         "LOCAL_METRIC_EQUIVALENT_NOT_EXACT_ANGULAR")
        self.assertEqual(q["ROMS_integration"],"NOT_RUN")

    def test_grid_staggers_metrics_and_angle_consistent(self):
        q=self.conf_report
        v=self.conf_geometry
        ny,nx=q["actual_rho_shape"]
        self.assertEqual(v["lon_u"].shape,(ny,nx-1))
        self.assertEqual(v["lon_v"].shape,(ny-1,nx))
        self.assertEqual(v["lon_psi"].shape,(ny-1,nx-1))
        for field in ("pm","pn","dndx","dmde","angle","f"):
            self.assertEqual(v[field].shape,(ny,nx))
            self.assertTrue(np.isfinite(v[field]).all())
        self.assertGreater(v["pm"].min(),0)
        self.assertGreater(v["pn"].min(),0)
        self.assertEqual(q["nominal_angular_spacing"],"1/36 degree")

    def test_full_coverage_of_new_ud1k_under_curved_perimeter(self):
        ud=json.loads(UD.read_text())
        crs=CRS.from_proj4("+proj=aeqd +lat_0=41 +lon_0=135 +datum=WGS84 +units=m")
        tf=Transformer.from_crs("EPSG:4326",crs,always_xy=True)
        lon=self.conf_geometry["lon_rho"]
        lat=self.conf_geometry["lat_rho"]
        ring=np.concatenate((
            np.column_stack((lon[0],lat[0])),
            np.column_stack((lon[1:,-1],lat[1:,-1])),
            np.column_stack((lon[-1,-2::-1],lat[-1,-2::-1])),
            np.column_stack((lon[-2:0:-1,0],lat[-2:0:-1,0]))))
        xx,yy=tf.transform(ring[:,0],ring[:,1])
        parent=Polygon(np.column_stack((xx,yy)))
        self.assertTrue(parent.is_valid)
        corners=[(ud["lon_min"],ud["lat_min"]),
                 (ud["realized_bounds_deg"]["east"],ud["lat_min"]),
                 (ud["realized_bounds_deg"]["east"],ud["realized_bounds_deg"]["north"]),
                 (ud["lon_min"],ud["realized_bounds_deg"]["north"])]
        x,y=tf.transform(*zip(*corners))
        child=Polygon(np.column_stack((x,y)))
        self.assertTrue(parent.contains(child))
        self.assertGreater(parent.boundary.distance(child),50_000)

    def test_production_entry_and_invalid_mode(self):
        geometry,dx,dy=make_geometry(self.conf)
        self.assertEqual(geometry["lon_rho"].shape,
                         tuple(self.conf_report["full_estimated_rho_shape"]))
        self.assertLess(abs(geometry["lon_rho"][0,0]-121.9),1e-9)
        self.assertTrue(np.isfinite(geometry["angle"]).all())
        self.assertGreater(dx,0)
        self.assertGreater(dy,0)
        with self.assertRaisesRegex(ValueError,"aspect"):
            conformal_corner_grid({**self.conf,"logical_rectangle_aspect":0.1},sample_scale=20)
        altered=json.loads(json.dumps(self.conf))
        altered["user_corners_lat_lon"]["W"][1]=121
        with self.assertRaisesRegex(ValueError,"corners have changed"):
            conformal_corner_grid(altered,sample_scale=20)


if __name__=="__main__":
    unittest.main()
