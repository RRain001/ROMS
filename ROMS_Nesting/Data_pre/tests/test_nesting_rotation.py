"""Geometry-only I2 tests. They DO NOT replace ROMS compiled physical tests."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from netCDF4 import Dataset

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "nesting"))
sys.path.insert(0, str(BASE / "core"))
from rotated_grid import RotatedGridSpec, create_geometry, geodesic_quality, write_synthetic_grid, east_north_to_grid, grid_to_east_north
from grid_metrics import compute_grid_metrics


class RotatedGridTests(unittest.TestCase):
    def spec(self, deg):
        return RotatedGridSpec(131.3, 37.6, 11, 9, 3000, 3000, deg)

    def test_rotations_angles_and_metric(self):
        for deg in (0, 20, -20, 45):
            with self.subTest(deg=deg):
                spec = self.spec(deg)
                arr = create_geometry(spec)
                self.assertEqual(arr["lon_rho"].shape, (9, 11))
                self.assertEqual(arr["lon_psi"].shape, (8, 10))
                self.assertEqual(arr["lon_u"].shape, (9, 10))
                self.assertEqual(arr["lon_v"].shape, (8, 11))
                self.assertTrue(np.isfinite(arr["lon_rho"]).all())
                self.assertTrue(np.all(arr["pm"] > 0))
                self.assertTrue(np.all(arr["pn"] > 0))
                # At the map center, LCC meridian convergence is zero.
                self.assertAlmostEqual(np.rad2deg(arr["angle"][4, 5]), deg, delta=0.2)
                q = geodesic_quality(arr, 3000, 3000)
                self.assertLess(q["orthogonality_error_max_deg"], 0.05)
                self.assertLess(q["dx_relerr_max"], 0.012)
                self.assertLess(q["dy_relerr_max"], 0.012)
                expected = compute_grid_metrics(arr["lon_rho"], arr["lat_rho"])
                for key in ("pm", "pn", "dndx", "dmde"):
                    np.testing.assert_allclose(arr[key], expected[key], atol=1e-10)

    def test_vectors_east_north_and_roundtrip(self):
        for deg in (-20, 0, 20, 45):
            a = create_geometry(self.spec(deg))["angle"]
            u, v = east_north_to_grid(np.ones_like(a), np.zeros_like(a), a)
            ee, nn = grid_to_east_north(u, v, a)
            np.testing.assert_allclose(ee, 1, atol=1e-14)
            np.testing.assert_allclose(nn, 0, atol=1e-14)
            u, v = east_north_to_grid(0, 1, a)
            ee, nn = grid_to_east_north(u, v, a)
            np.testing.assert_allclose(ee, 0, atol=1e-14)
            np.testing.assert_allclose(nn, 1, atol=1e-14)

    def test_synthetic_netcdf_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            outfile = Path(tmp) / "rotated.nc"
            stats = write_synthetic_grid(outfile, self.spec(20))
            self.assertLess(stats["orthogonality_error_max_deg"], 0.05)
            with Dataset(outfile) as ds:
                self.assertIn("synthetic_test_only", ds.ncattrs())
                self.assertEqual(ds.dimensions["xi_rho"].size, 11)
                self.assertEqual(ds.dimensions["xi_psi"].size, 10)
                self.assertEqual(ds["mask_u"].shape, (9, 10))
                self.assertGreater(np.max(abs(ds["angle"][:])), 0.1)
                self.assertTrue(np.all(ds["h"][:] == 100))

    def test_invalid_configs_rejected(self):
        for spec in (RotatedGridSpec(132, 37, 2, 8, 3000, 3000, 0),
                     RotatedGridSpec(132, 37, 8, 8, -100, 3000, 0),
                     RotatedGridSpec(132, 37, 8, 8, 3000, 3000, float('nan'))):
            with self.subTest(spec=spec):
                with self.assertRaises(ValueError):
                    create_geometry(spec)


if __name__ == "__main__":
    unittest.main()
