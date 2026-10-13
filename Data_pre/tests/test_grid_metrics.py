"""Geodesic metrics regressions with an independent WGS84 Vincenty reference."""
import math
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[2]
for directory in ("scripts/bathymetry", "core", "impl/preprocessing"):
    sys.path.insert(0, str(ROOT / "Data_pre" / directory))
from grid_metrics import compute_grid_metrics
from create_grid_from_bathymetry import target_grid, write_grid
from check_roms_grid_quality import metric_consistency
from repair_grid_metrics import repair, sha256, verify_unchanged


def vincenty(lon1, lat1, lon2, lat2):
    """Scalar ellipsoid inverse, independent of PROJ and production code.

    Vincenty (1975), Survey Review 23(176), 88-93. Tests use local edges,
    avoiding the antipodal convergence limitation of this reference.
    """
    a, f = 6378137.0, 1 / 298.257223563
    b = a * (1 - f)
    u1, u2 = [math.atan((1 - f) * math.tan(math.radians(t))) for t in (lat1, lat2)]
    su1, cu1, su2, cu2 = math.sin(u1), math.cos(u1), math.sin(u2), math.cos(u2)
    ll = math.radians(lon2 - lon1)
    lam = ll
    for _ in range(100):
        sl, cl = math.sin(lam), math.cos(lam)
        ss = math.hypot(cu2 * sl, cu1 * su2 - su1 * cu2 * cl)
        cs = su1 * su2 + cu1 * cu2 * cl
        sigma = math.atan2(ss, cs)
        sa = cu1 * cu2 * sl / ss
        ca2 = 1 - sa * sa
        c2 = cs - 2 * su1 * su2 / ca2 if ca2 > 1e-20 else 0
        c = f / 16 * ca2 * (4 + f * (4 - 3 * ca2))
        prev = lam
        lam = ll + (1 - c) * f * sa * (sigma + c * ss * (c2 + c * cs * (-1 + 2 * c2 * c2)))
        if abs(lam - prev) < 1e-14:
            break
    else:
        raise AssertionError("reference did not converge")
    usq = ca2 * (a * a - b * b) / (b * b)
    aa = 1 + usq / 16384 * (4096 + usq * (-768 + usq * (320 - 175 * usq)))
    bb = usq / 1024 * (256 + usq * (-128 + usq * (74 - 47 * usq)))
    ds = bb * ss * (c2 + bb / 4 * (cs * (-1 + 2 * c2 * c2) - bb / 6 * c2 * (-3 + 4 * ss * ss) * (-3 + 4 * c2 * c2)))
    return b * aa * (sigma - ds)


def reference(lon, lat):
    dx, dy = np.zeros(lon.shape), np.zeros(lon.shape)
    ny, nx = lon.shape
    for j in range(ny):
        for i in range(nx):
            ix = [k for k in (i - 1, i + 1) if 0 <= k < nx]
            jy = [k for k in (j - 1, j + 1) if 0 <= k < ny]
            dx[j, i] = np.mean([vincenty(lon[j, i], lat[j, i], lon[j, k], lat[j, k]) for k in ix])
            dy[j, i] = np.mean([vincenty(lon[j, i], lat[j, i], lon[k, i], lat[k, i]) for k in jy])
    return dx, dy


class GridMetricsTests(unittest.TestCase):
    def test_latitude_domains_and_boundaries(self):
        for lo, hi in ((-0.2, 0.2), (37, 37.84), (35.5, 35.9), (49.5, 49.9), (5, 70)):
            with self.subTest(latitude=(lo, hi)):
                lon, lat = np.meshgrid(np.linspace(140.88, 142, 8), np.linspace(lo, hi, 9))
                m = compute_grid_metrics(lon, lat)
                dx, dy = reference(lon, lat)
                np.testing.assert_allclose(1 / m['pm'], dx, rtol=2e-9, atol=2e-5)
                np.testing.assert_allclose(1 / m['pn'], dy, rtol=2e-9, atol=2e-5)
                np.testing.assert_allclose(m['dndx'][:, 1:-1], (dy[:, 2:] - dy[:, :-2]) / 2, atol=2e-5)
                np.testing.assert_allclose(m['dmde'][1:-1], (dx[2:] - dx[:-2]) / 2, rtol=2e-8, atol=2e-5)
                np.testing.assert_allclose(m['dmde'][0], dx[1] - dx[0], atol=2e-5)
                np.testing.assert_allclose(m['dmde'][-1], dx[-1] - dx[-2], atol=2e-5)
                np.testing.assert_allclose(m['dndx'][:, 0], dy[:, 1] - dy[:, 0], atol=2e-5)
                np.testing.assert_allclose(m['dndx'][:, -1], dy[:, -1] - dy[:, -2], atol=2e-5)
                self.assertLess(np.max(np.abs(m['dndx'])), 1e-7)
                self.assertGreater(np.max(np.abs(m['dmde'])), 0.001)
                self.assertGreater(np.ptp(m['pm']), 0)
                self.assertGreater(np.ptp(m['pn']), 0)
                self.assertEqual(metric_consistency(m['pm'], m['pn'], lon, lat, m['dndx'], m['dmde'])['status'], 'PASS')

    def test_lm_plus_two(self):
        domain = dict(lon_min=140.88, lon_max=142, lat_min=37, lat_max=37.84)
        lon, lat, width, height, lm, mm = target_grid(domain, 10000)
        self.assertEqual(lon.shape, (mm + 2, lm + 2))
        dx, dy = reference(lon, lat)
        m = compute_grid_metrics(lon, lat)
        np.testing.assert_allclose(m['pm'], 1 / dx, rtol=2e-9)
        np.testing.assert_allclose(m['pn'], 1 / dy, rtol=2e-9)
        self.assertGreater(np.max(np.abs((1 / dx - lm / width) / (1 / dx))), 0.01)

    def test_nonuniform_edges_and_minimum_shape(self):
        lon, lat = np.meshgrid([140, 140.01, 140.03, 140.08], [35, 35.02, 35.05])
        m = compute_grid_metrics(lon, lat)
        dx, dy = reference(lon, lat)
        np.testing.assert_allclose(1 / m['pm'], dx, rtol=2e-9)
        np.testing.assert_allclose(1 / m['pn'], dy, rtol=2e-9)
        np.testing.assert_allclose(m['dmde'][0], dx[1] - dx[0], atol=2e-5)
        np.testing.assert_allclose(m['dmde'][-1], dx[-1] - dx[-2], atol=2e-5)
        tiny = compute_grid_metrics(lon[:2, :2], lat[:2, :2])
        self.assertEqual(tiny['pm'].shape, (2, 2))

    def test_nonzero_index_derivatives_at_all_edges(self):
        # Warped coordinates ensure dndx boundary assertions are not trivial zeros.
        x, y = np.meshgrid(np.arange(5), np.arange(4))
        lon = 140 + 0.01 * x + 0.001 * y * y
        lat = 37 + 0.02 * y * (1 + 0.03 * x)
        m = compute_grid_metrics(lon, lat)
        dx, dy = reference(lon, lat)
        self.assertGreater(np.max(np.abs(m['dndx'])), 1)
        np.testing.assert_allclose(m['dndx'][:, 1:-1], (dy[:, 2:] - dy[:, :-2]) / 2, atol=2e-5)
        np.testing.assert_allclose(m['dndx'][:, 0], dy[:, 1] - dy[:, 0], atol=2e-5)
        np.testing.assert_allclose(m['dndx'][:, -1], dy[:, -1] - dy[:, -2], atol=2e-5)
        np.testing.assert_allclose(m['dmde'][1:-1], (dx[2:] - dx[:-2]) / 2, atol=2e-5)
        np.testing.assert_allclose(m['dmde'][0], dx[1] - dx[0], atol=2e-5)
        np.testing.assert_allclose(m['dmde'][-1], dx[-1] - dx[-2], atol=2e-5)

    def test_invalid_and_quality_failures(self):
        lon, lat = np.meshgrid([140, 140.01, 140.02], [37, 37.01, 37.02])
        m = compute_grid_metrics(lon, lat)
        for name, bad in (('pm', np.zeros(lon.shape)), ('pn', np.full(lon.shape, np.nan)),
                          ('dmde', np.zeros(lon.shape)), ('dndx', np.ones(lon.shape))):
            trial = dict(m)
            trial[name] = bad
            self.assertEqual(metric_consistency(trial['pm'], trial['pn'], lon, lat, trial['dndx'], trial['dmde'])['status'], 'FAIL')
        rounded = {k: v.astype('f4') for k, v in m.items()}
        self.assertEqual(metric_consistency(rounded['pm'], rounded['pn'], lon, lat, rounded['dndx'], rounded['dmde'])['status'], 'PASS')
        for x, y in ((lon[:1], lat[:1]), (lon * np.nan, lat), (np.zeros_like(lon), lat)):
            with self.assertRaises(ValueError):
                compute_grid_metrics(x, y)

    def make_grid(self, path):
        lon, lat, width, height, lm, mm = target_grid(dict(lon_min=140.88, lon_max=141, lat_min=37, lat_max=37.1), 4000)
        h = np.arange(lon.size).reshape(lon.shape) + 20
        mask = np.ones(lon.shape, dtype='i1')
        mask[0, 0] = 0
        write_grid(path, lon, lat, h, mask, width, height, lm, mm, Path('synthetic'), 'z', 4000)
        return lon, lat

    def test_repair_preserves_data_and_matches_generator(self):
        with tempfile.TemporaryDirectory() as directory:
            src, dst = [Path(directory) / p for p in ('grid.nc', 'fixed.nc')]
            lon, lat = self.make_grid(src)
            with Dataset(src, 'r+') as ds:
                generated = {k: ds[k][:].copy() for k in ('pm', 'pn', 'dndx', 'dmde')}
                for k in generated:
                    ds[k][:] = 0 if k in ('dndx', 'dmde') else 0.0002
                v = ds.createVariable('packed_science', 'i2', ('eta_rho', 'xi_rho'), fill_value=-999, zlib=True)
                v.scale_factor = 0.1
                v[:] = lon
                g = ds.createGroup('extra')
                g.note = 'preserved'
                g.createVariable('scalar', 'i4').assignValue(42)
            checksum = sha256(src)
            report = repair(src, dst)
            self.assertEqual(sha256(src), checksum)
            self.assertEqual(report['output_sha256'], sha256(dst))
            self.assertIn('packed_science', report['unchanged_variables'])
            self.assertIn('extra/scalar', report['unchanged_variables'])
            with Dataset(dst) as ds:
                for k, v in generated.items():
                    np.testing.assert_array_equal(ds[k][:], v)
            verify_unchanged(src, dst)
            with Dataset(dst, 'r+') as ds:
                ds['h'][0, 0] += 1
            with self.assertRaises(ValueError):
                verify_unchanged(src, dst)
            with self.assertRaises(ValueError):
                repair(src, dst)
            with self.assertRaises(ValueError):
                repair(src, src)

    def test_float32_netcdf3_storage_and_fill_values(self):
        with tempfile.TemporaryDirectory() as directory:
            src, dst = [Path(directory) / p for p in ('classic.nc', 'fixed.nc')]
            lon, lat = np.meshgrid([140, 140.01, 140.02], [37, 37.01, 37.02])
            with Dataset(src, 'w', format='NETCDF3_64BIT_OFFSET') as ds:
                ds.createDimension('eta_rho', 3)
                ds.createDimension('xi_rho', 3)
                ds.createVariable('spherical', 'i4').assignValue(1)
                for name, values in (('lon_rho', lon), ('lat_rho', lat)):
                    ds.createVariable(name, 'f8', ('eta_rho', 'xi_rho'))[:] = values
                for name in ('pm', 'pn', 'dndx', 'dmde'):
                    v = ds.createVariable(name, 'f4', ('eta_rho', 'xi_rho'))
                    v.units = 'meter-1' if name in ('pm', 'pn') else 'meter'
                    v[:] = 0
                v = ds.createVariable('untouched', 'f4', ('eta_rho', 'xi_rho'), fill_value=-999)
                data = np.arange(9).reshape(3, 3).astype(float)
                data[0, 0] = np.nan
                v[:] = np.ma.masked_invalid(data)
            repair(src, dst)
            verify_unchanged(src, dst)
            with Dataset(dst) as ds:
                self.assertEqual(ds.data_model, 'NETCDF3_64BIT_OFFSET')
                m = {k: ds[k][:] for k in ('pm', 'pn', 'dndx', 'dmde')}
                self.assertTrue(all(v.dtype == np.dtype('f4') for v in m.values()))
                self.assertEqual(metric_consistency(m['pm'], m['pn'], lon, lat, m['dndx'], m['dmde'])['status'], 'PASS')

    def test_dry_run_and_cartesian_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            src, dst = [Path(directory) / p for p in ('grid.nc', 'fixed.nc')]
            self.make_grid(src)
            checksum = sha256(src)
            report = repair(src, dst, dry_run=True)
            self.assertFalse(dst.exists())
            self.assertIsNone(report['output_sha256'])
            self.assertEqual(sha256(src), checksum)
            with Dataset(src, 'r+') as ds:
                ds['spherical'].assignValue(0)
            with self.assertRaises(ValueError):
                repair(src, Path(directory) / 'cartesian.nc')


if __name__ == '__main__':
    unittest.main()
