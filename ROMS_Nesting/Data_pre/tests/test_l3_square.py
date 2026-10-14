"""I6 user-anchored L3 offshore square, angular sampling and parent preflight.

All generated hydro/bathymetry here is synthetic. Passing tests cannot
establish real Korean coastline, coastal discharge location, or ROMS
hydrodynamics.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from netCDF4 import Dataset
from pyproj import Geod

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"nesting"))
from l3_square import square_corners,square_grid_geometry
from bathymetry_grid import build_grid,make_geometry
from validate_nesting_geometries import check_pair

USER_CONFIG=ROOT.parent/"configs/l3_coastal_square_candidate.json"
UD_CONFIG=ROOT.parent/"configs/ud1k_candidate.json"
WGS84=Geod(ellps="WGS84")


def synthetic_sea(path:Path)->None:
    """All-water synthetic raster deliberately CANNOT certify true shoreline."""
    lon=np.linspace(129.0,130.5,90)
    lat=np.linspace(35.25,36.3,95)
    lo,la=np.meshgrid(lon,lat)
    elev=-80-100*(lo-lon.min())-35*(la-lat.min())
    with Dataset(path,"w",format="NETCDF4") as ds:
        ds.createDimension("lon",len(lon))
        ds.createDimension("lat",len(lat))
        ds.createVariable("lon","f8",("lon",))[:]=lon
        ds.createVariable("lat","f8",("lat",))[:]=lat
        ds.createVariable("elevation","f8",("lat","lon"))[:]=elev


class AnchoredL3Tests(unittest.TestCase):
    def setUp(self):
        self.spec=json.loads(USER_CONFIG.read_text())
        self.parent_spec=json.loads(UD_CONFIG.read_text())

    def test_four_corners_exact_anchors_offshore(self):
        info=square_corners(self.spec)
        corners=info["corners_lat_lon"]
        self.assertEqual(corners["A"],[35.545437,129.407703])
        self.assertEqual(corners["B"],[35.974688,129.522766])
        self.assertAlmostEqual(corners["C"][0],35.87949888065,places=7)
        self.assertAlmostEqual(corners["C"][1],130.0501311499,places=7)
        self.assertAlmostEqual(corners["D"][0],35.45075404285,places=7)
        self.assertAlmostEqual(corners["D"][1],129.93238835474,places=7)
        self.assertAlmostEqual(info["side_m"],48750.8486,delta=.2)
        self.assertAlmostEqual(info["azimuth_A_to_B_deg_cw_from_north"],12.29098,places=3)
        self.assertGreater(corners["D"][1],corners["A"][1])
        self.assertGreater(corners["C"][1],corners["B"][1])
        self.assertLess(info["bounds_deg"]["south"],35.5)
        self.assertAlmostEqual(info["area_local_planar_km2"],2376.645,delta=.1)

    def test_all_four_edges_physically_square(self):
        c=square_corners(self.spec)["corners_lat_lon"]
        def length(p,q):
            return WGS84.inv(p[1],p[0],q[1],q[0])[2]
        edges=[length(c[p],c[q]) for p,q in
               (("A","B"),("B","C"),("C","D"),("D","A"))]
        self.assertLess(max(edges)-min(edges),1.0)

    def test_l3_mesh_anchor_rho_corners_and_nominal_conversion(self):
        data,dx,dy,report=square_grid_geometry(self.spec)
        self.assertEqual(data["lon_rho"].shape,(143,176))
        self.assertEqual(report["edge_intervals"],{"xi":175,"eta":142})
        self.assertEqual(report["nominal_angular_resolution_fraction"],"1/324 deg")
        self.assertIn("NOT_CONSTANT_DDEG",report["nominal_vs_actual"])
        for row,col,key in [(0,0,"A"),(-1,0,"B"),(-1,-1,"C"),(0,-1,"D")]:
            lat,lon=report["corners_lat_lon"][key]
            self.assertAlmostEqual(data["lon_rho"][row,col],lon,places=9)
            self.assertAlmostEqual(data["lat_rho"][row,col],lat,places=9)
        self.assertLess(abs(report["relative_spacing_deviation"]["xi"]),.01)
        self.assertLess(abs(report["relative_spacing_deviation"]["eta"]),.01)
        self.assertLess(np.max(np.abs(data["angle"]+np.deg2rad(12.29))),.015)
        self.assertTrue(np.isfinite(data["pm"]).all())
        self.assertTrue(np.isfinite(data["pn"]).all())
        self.assertEqual(data["lon_u"].shape,(143,175))
        self.assertEqual(data["lon_v"].shape,(142,176))
        self.assertEqual(data["lon_psi"].shape,(142,175))

    def test_parent_exact_one_over_108_with_rounded_dms_bounds(self):
        data,dx,dy=make_geometry(self.parent_spec)
        west=128+21/60+55.9/3600
        south=34+57/60+55.7/3600
        requested_east=132+24/60+42.6/3600
        requested_north=37+38/60+29.0/3600
        step=1/108
        self.assertEqual(data["lon_rho"].shape,(290,438))
        self.assertEqual(float(data["angle"].max()),0)
        np.testing.assert_allclose(np.diff(data["lon_rho"][0]),step,atol=1e-12)
        np.testing.assert_allclose(np.diff(data["lat_rho"][:,0]),step,atol=1e-12)
        self.assertAlmostEqual(float(data["lon_rho"][0,0]),west,places=12)
        self.assertAlmostEqual(float(data["lat_rho"][0,0]),south,places=12)
        self.assertAlmostEqual(float(data["lon_rho"][0,-1]),west+437*step,places=12)
        self.assertAlmostEqual(float(data["lat_rho"][-1,0]),south+289*step,places=12)
        self.assertLess(abs((float(data["lon_rho"][0,-1])-requested_east)*3600),0.05)
        self.assertLess(abs((float(data["lat_rho"][-1,0])-requested_north)*3600),0.05)

    def test_latest_ud1k_approval_and_l3_parent_geometry_locked(self):
        family=json.loads((ROOT.parent/"configs/grid_family.json").read_text())
        parent=next(x for x in family["grids"] if x["id"]=="UD1K")
        self.assertEqual(parent["geometry_approval"],
                         "USER_UPDATED_NORTH_EAST_ROUNDED_DMS_2026_10_14")
        self.assertEqual(parent["proposed_modification"]["status"],
                         "SUPERSEDED_BY_NEW_USER_DMS_FOUR_BOUNDARIES")
        self.assertEqual(parent["proposed_modification"]["physical_approval"],
                         "PENDING_GEBCO_GSHHG_PARENT_BOUNDARY")
        self.assertEqual(self.parent_spec["angular_boundary_policy"],
                         "ANCHOR_WEST_SOUTH_EXACT_1_OVER_108_ROUNDED_DMS")
        self.assertEqual(self.parent_spec["expected_rho_shape_eta_xi"],[290,438])

    def test_opposite_inland_side_is_explicitly_rejected(self):
        bad={**self.spec,"offshore_side":"left_of_A_to_B"}
        with self.assertRaisesRegex(ValueError,"seaward"):
            square_corners(bad)
        bad={**self.spec,"nominal_resolution_deg":1/300}
        with self.assertRaisesRegex(ValueError,"1/324"):
            square_corners(bad)

    def test_small_synthetic_bathy_end_to_end_and_parent_containment(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            src=folder/"fake_all_wet.nc"
            synthetic_sea(src)
            child=folder/"L3_SYNTHETIC.nc"
            report=build_grid(self.spec,src,child,allow_gebco_only_mask=True,
                              synthetic_fixture=True)
            self.assertEqual(report["status"],"CANDIDATE_NOT_VALIDATED_FOR_ROMS")
            with Dataset(child) as ds:
                self.assertEqual(ds.grid_id,"L3_300m")
                self.assertEqual(ds.synthetic_test_only,"TRUE")
                self.assertEqual(ds.angular_spacing_claim,
                    "LOCAL_METRIC_EQUIVALENT_NOT_EXACT_ANGULAR")
                self.assertEqual(ds["lon_rho"].shape,(143,176))
                self.assertEqual(ds["mask_rho"].shape,(143,176))
                self.assertIn("A",json.loads(ds.coastal_square_corners_lat_lon))

            parent=folder/"UD1K_EXTENDED_SYNTHETIC.nc"
            # Compact *test* parent of the real candidate, same exact
            # angular spacing and with a south boundary sufficient for L3.
            study_parent={**self.parent_spec,
                          "lon_min":129.15,"lon_max":130.3,
                          "lat_min":35.35,"lat_max":36.15,
                          "angular_boundary_policy":"SNAP_TO_EXACT_ANGULAR_STEP"}
            build_grid(study_parent,src,parent,
                       allow_gebco_only_mask=True,synthetic_fixture=True)
            pair=check_pair(parent,child,margin_parent_rho_cells=2)
            self.assertEqual(pair["status"],"PASS_PRELIMINARY_ONLY")
            self.assertEqual(pair["parent_grid_id"],"UD1K")
            self.assertEqual(pair["child_grid_id"],"L3_300m")
            self.assertGreater(pair["buffered_parent_boundary_gap_min_m"],5000)
            self.assertEqual(pair["conservative_boundary_fluxes"],"NOT_RUN")
            self.assertEqual(pair["parent_synthetic"],"TRUE")

            old=folder/"UD1K_PAPER_SOUTH_SYNTHETIC.nc"
            build_grid({**study_parent,"lat_min":35.5},
                       src,old,allow_gebco_only_mask=True,
                       synthetic_fixture=True)
            fail=check_pair(old,child,margin_parent_rho_cells=2)
            self.assertEqual(fail["status"],"FAIL")
            self.assertIn("buffered UD1K",fail["reason"])

if __name__=="__main__":
    unittest.main()
