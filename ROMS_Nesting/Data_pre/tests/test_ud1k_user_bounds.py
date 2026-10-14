"""UD1K four user DMS limits are immutable; nominal 1/108° is exact at grid-node precision; DMS east/north are rounded.

Real GEBCO/GSHHG and ROMS physics acceptance gates remain NOT RUN.
"""
from __future__ import annotations
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
from netCDF4 import Dataset
from pyproj import CRS, Transformer
from shapely.geometry import Polygon

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"nesting"),str(ROOT/"core")]
from bathymetry_grid import make_geometry, build_grid
from l3_square import square_corners
from validate_nesting_geometries import check_pair

UD_PATH=ROOT.parent/"configs/ud1k_candidate.json"
ES_PATH=ROOT.parent/"configs/es3k_user_corners.json"
L3_PATH=ROOT.parent/"configs/l3_coastal_square_candidate.json"


def dms(deg:int,minute:int,second:float) -> float:
    return deg+minute/60+second/3600


class NewUD1KBounds(unittest.TestCase):
    def setUp(self):
        self.ud=json.loads(UD_PATH.read_text())
        self.es=json.loads(ES_PATH.read_text())
        self.l3=json.loads(L3_PATH.read_text())

    def test_dms_four_exact_bounds_and_policy(self):
        expected={
            "south":dms(34,57,55.7),
            "west":dms(128,21,55.9),
            "north":dms(37,38,29.0),
            "east":dms(132,24,42.6),
        }
        actual={n:self.ud[k] for n,k in (
            ("south","lat_min"),("north","lat_max"),
            ("west","lon_min"),("east","lon_max"))}
        for key,value in expected.items():
            self.assertAlmostEqual(actual[key],value,places=12)
        self.assertEqual(set(self.ud["requested_bounds_dms"]),set(expected))
        self.assertEqual(self.ud["angular_boundary_policy"],
                         "ANCHOR_WEST_SOUTH_EXACT_1_OVER_108_ROUNDED_DMS")
        self.assertEqual(self.ud["geometry_approval"],"USER_UPDATED_NORTH_EAST_ROUNDED_DMS_2026_10_14")

    def test_generated_exact_extent_and_nominal_resolution(self):
        out,dx,dy=make_geometry(self.ud)
        lo,la=out["lon_rho"],out["lat_rho"]
        self.assertEqual(lo.shape,(290,438))
        self.assertTrue(np.all(out["angle"]==0))
        self.assertAlmostEqual(float(lo[0,0]),self.ud["lon_min"],places=12)
        self.assertAlmostEqual(float(la[0,0]),self.ud["lat_min"],places=12)
        # E/N are only given with 0.1" DMS precision and must be
        # rounded versions of the exact-1/108° grid endpoint.
        self.assertLess(abs((float(lo[0,-1])-self.ud["lon_max"])*3600),0.05)
        self.assertLess(abs((float(la[-1,0])-self.ud["lat_max"])*3600),0.05)
        self.assertAlmostEqual(float(lo[0,-1]),self.ud["realized_bounds_deg"]["east"],places=12)
        self.assertAlmostEqual(float(la[-1,0]),self.ud["realized_bounds_deg"]["north"],places=12)
        actual_lon=1/108
        actual_lat=1/108
        np.testing.assert_allclose(np.diff(lo[0]),actual_lon,atol=1e-12,rtol=0)
        np.testing.assert_allclose(np.diff(la[:,0]),actual_lat,atol=1e-12,rtol=0)
        self.assertAlmostEqual(actual_lon,self.ud["actual_lon_step_deg"],places=13)
        self.assertAlmostEqual(actual_lat,self.ud["actual_lat_step_deg"],places=13)
        self.assertLess(max(abs(actual_lon/(1/108)-1),abs(actual_lat/(1/108)-1)),.002)
        self.assertTrue(np.isfinite(out["pm"]).all())
        self.assertTrue(np.isfinite(out["pn"]).all())
        self.assertEqual(out["lon_u"].shape,(290,437))
        self.assertEqual(out["lon_v"].shape,(289,438))
        self.assertEqual(out["lon_psi"].shape,(289,437))

    def test_reject_spatial_changes_outside_tolerance(self):
        # Move the rounded E or N boundary outside half a tenth of
        # an arcsecond: the exact-spacing policy MUST reject it.
        for changed_key in ("lon_max","lat_max"):
            invalid={**self.ud,changed_key:self.ud[changed_key]+0.1/3600}
            with self.assertRaisesRegex(ValueError,"cannot match E/N"):
                make_geometry(invalid)
        invalid={**self.ud,"rounded_dms_half_precision_arcsec":0.051}
        with self.assertRaisesRegex(ValueError,"half-precision"):
            make_geometry(invalid)
        bad={**self.ud,"angular_boundary_policy":"SILENT_CORNER_SNAPPING"}
        with self.assertRaisesRegex(ValueError,"unknown UD1K"):
            make_geometry(bad)

    def test_es3k_contains_ud1k_contains_l3(self):
        corners=square_corners(self.l3)["corners_lat_lon"]
        crs=CRS.from_proj4("+proj=aeqd +lat_0=40 +lon_0=135 +datum=WGS84 +units=m")
        transform=Transformer.from_crs("EPSG:4326",crs,always_xy=True)
        def poly(vertices):
            return Polygon([transform.transform(lon,lat) for lat,lon in vertices])
        es=poly([self.es["user_corners_lat_lon"][name]
                 for name in ("W","N","E","S")])
        ud=poly([
            (self.ud["lat_min"],self.ud["lon_min"]),
            (self.ud["lat_min"],self.ud["lon_max"]),
            (self.ud["lat_max"],self.ud["lon_max"]),
            (self.ud["lat_max"],self.ud["lon_min"])])
        l3=poly([corners[name] for name in ("A","B","C","D")])
        self.assertTrue(es.is_valid)
        self.assertTrue(es.contains(ud))
        self.assertTrue(ud.contains(l3))
        self.assertGreater(ud.boundary.distance(l3),40000)

    def test_actual_size_parent_and_child_with_synthetic_wet_bathy(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            src=root/"SYNTHETIC_OCEAN_NOT_GEBCO.nc"
            lon=np.linspace(128,133,110)
            lat=np.linspace(34.5,38.0,100)
            with Dataset(src,"w") as ds:
                ds.createDimension("lon",len(lon))
                ds.createDimension("lat",len(lat))
                ds.createVariable("lon","f8",("lon",))[:]=lon
                ds.createVariable("lat","f8",("lat",))[:]=lat
                ds.createVariable("elevation","f4",("lat","lon"))[:]=-125
            parent=root/"UD1K_EXACT_DMS_SYNTHETIC.nc"
            child=root/"L3_SYNTHETIC.nc"
            build_grid(self.ud,src,parent,allow_gebco_only_mask=True,synthetic_fixture=True)
            build_grid(self.l3,src,child,allow_gebco_only_mask=True,synthetic_fixture=True)
            with Dataset(parent) as ds:
                self.assertEqual(ds["lon_rho"].shape,(290,438))
                self.assertEqual(ds.angular_spacing_claim,
                   "GEOGRAPHIC_EXACT_1_OVER_108_WEST_SOUTH_FIXED_DMS_ROUNDED")
                self.assertEqual(ds.ud1k_boundary_policy,
                   "ANCHOR_WEST_SOUTH_EXACT_1_OVER_108_ROUNDED_DMS")
                self.assertAlmostEqual(ds.ud1k_actual_lon_step_deg,
                                       self.ud["actual_lon_step_deg"],places=12)
                self.assertAlmostEqual(ds.ud1k_actual_lat_step_deg,
                                       self.ud["actual_lat_step_deg"],places=12)
                self.assertLess(abs(ds.ud1k_east_dms_rounding_offset_arcsec),0.05)
                self.assertLess(abs(ds.ud1k_north_dms_rounding_offset_arcsec),0.05)
                self.assertAlmostEqual(ds.ud1k_actual_lon_step_deg,1/108,places=12)
                self.assertAlmostEqual(ds.ud1k_actual_lat_step_deg,1/108,places=12)
                self.assertEqual(ds.synthetic_test_only,"TRUE")
            result=check_pair(parent,child,margin_parent_rho_cells=2)
            self.assertEqual(result["status"],"PASS_PRELIMINARY_ONLY")
            self.assertEqual(result["parent_grid_id"],"UD1K")
            self.assertEqual(result["child_grid_id"],"L3_300m")
            self.assertGreater(result["buffered_parent_boundary_gap_min_m"],40000)
            self.assertEqual(result["conservative_boundary_fluxes"],"NOT_RUN")


if __name__=="__main__":
    unittest.main()
