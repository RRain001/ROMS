"""I3 ES3K user-input four-corner source-of-truth tests.

Confirms geographical polygon, explicit user coordinates and nested
extent only. DOES NOT imply an accepted curvilinear 1/36-degree ROMS
grid, near-orthogonality, sea-mask or physical simulation.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import sys

from pyproj import Geod
from shapely.geometry import Polygon

ROOT=Path(__file__).resolve().parents[1]
USER_PATH=ROOT.parent/"configs/es3k_user_corners.json"
FAMILY_PATH=ROOT.parent/"configs/grid_family.json"
TOMBSTONE=ROOT.parent/"configs/es3k_figure1_outline_schematic.json"
UD=ROOT.parent/"configs/ud1k_candidate.json"
L3=ROOT.parent/"configs/l3_coastal_square_candidate.json"
G=Geod(ellps="WGS84")


class UserES3KCorners(unittest.TestCase):
    def setUp(self):
        self.cfg=json.loads(USER_PATH.read_text())
        self.grid=json.loads(FAMILY_PATH.read_text())
        self.points=self.cfg["user_corners_lat_lon"]

    def test_exact_lat_lon_and_perimeter(self):
        self.assertEqual(self.points,{
            "W":[37.821077,121.0],
            "S":[30.8,131.471973],
            "N":[52.0,141.327943],
            "E":[45.616255,150.4],
        })
        self.assertEqual(self.cfg["perimeter_order"],"W_N_E_S_W")
        self.assertEqual(self.cfg["coordinate_order"],"LATITUDE_DEG_N_LONGITUDE_DEG_E")
        es=self.grid["grids"][0]
        self.assertEqual(es["corners_deg"],self.points)
        self.assertEqual(es["source_of_corners"],"USER_SUPPLIED_2026_10_14")
        self.assertEqual(es["nominal_resolution_fraction"],"1/36 deg")
        self.assertEqual(es["angular_grid_generator_status"],"NOT_IMPLEMENTED")
        self.assertEqual(es["user_defined_envelope_deg"],[121.0,150.4,30.8,52.0])
        self.assertNotEqual(es["user_defined_envelope_deg"],es["reference_envelope_deg"])
        self.assertIsNone(es["figure1_rotation_candidate_deg_ccw_from_east"])

    def test_footprint_is_valid_non_self_intersecting(self):
        outline=Polygon([(self.points[k][1],self.points[k][0])
                         for k in ("W","N","E","S")])
        self.assertTrue(outline.is_valid)
        self.assertGreater(outline.area,0)
        self.assertEqual(outline.bounds,(121.0,30.8,150.4,52.0))
        lons,lats=zip(*[(self.points[k][1],self.points[k][0])
                        for k in ("W","N","E","S")])
        area,_=G.polygon_area_perimeter(lons,lats)
        self.assertGreater(abs(area)/1e6,2.50e6)
        self.assertLess(abs(area)/1e6,2.57e6)

    def test_edge_orientation_is_local_not_uniform_angle(self):
        a,b=self.points["W"],self.points["N"]
        az,_,km=G.inv(a[1],a[0],b[1],b[0])
        self.assertAlmostEqual(90-az,51.36,delta=.15)
        self.assertAlmostEqual(km/1000,2234.65,delta=1)
        # South-to-east long edge azimuth differs because corners are
        # on a curved ellipsoid and the shape is not an exact rectangle.
        s,e=self.points["S"],self.points["E"]
        az2,_,dist=G.inv(s[1],s[0],e[1],e[0])
        self.assertGreater(abs(az-az2),5)
        self.assertGreater(abs(dist/1000-km/1000),50)

    def test_full_ud1k_interior_and_l3_user_square(self):
        from pyproj import CRS,Transformer
        ud=json.loads(UD.read_text())
        l3=json.loads(L3.read_text())
        sys.path.insert(0,str(ROOT/"nesting"))
        from l3_square import square_corners
        crs=CRS.from_proj4("+proj=aeqd +lat_0=41 +lon_0=135 +datum=WGS84 +units=m")
        tf=Transformer.from_crs("EPSG:4326",crs,always_xy=True)
        def poly(vertices):
            return Polygon([tf.transform(lon,lat) for lon,lat in vertices])
        es=poly([(self.points[k][1],self.points[k][0])
                 for k in ("W","N","E","S")])
        south=ud["lat_max"]-round((ud["lat_max"]-ud["lat_min"])*108)/108
        parent=poly([(ud["lon_min"],south),(ud["lon_max"],south),
                     (ud["lon_max"],ud["lat_max"]),(ud["lon_min"],ud["lat_max"])])
        self.assertTrue(es.contains(parent))
        corners=square_corners(l3)["corners_lat_lon"]
        child=poly([(corners[k][1],corners[k][0])
                    for k in ("A","B","C","D")])
        self.assertTrue(parent.contains(child))
        self.assertTrue(es.contains(child))
        self.assertGreater(parent.exterior.distance(child)/1000,2)

    def test_prior_figure1_rough_corners_are_retired(self):
        tombstone=json.loads(TOMBSTONE.read_text())
        self.assertEqual(tombstone["status"],"SUPERSEDED_DO_NOT_USE")
        self.assertNotIn("points_lon_lat",tombstone)


if __name__=="__main__":
    unittest.main()
