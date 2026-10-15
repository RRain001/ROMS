#!/usr/bin/env python3
"""Fail-closed boundary-coverage tests; synthetic NetCDF only, no model/API.

Every case here is a *negative* test except the two explicitly named
``..._passes`` ones: the point of the module is that a run may only start when
coverage is provably OK, so anything undecidable must be refused rather than
silently replaced by the configured stop time.
"""

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "core"))

from external_forcing_coverage import (  # noqa: E402
    INSUFFICIENT,
    OK,
    UNKNOWN,
    boundary_time_variables,
    check_boundary_coverage,
    datetime_to_mjd,
    mjd_to_datetime,
)

START = datetime(2018, 1, 2, 0, 0, 0)
STOP = datetime(2018, 1, 3, 0, 0, 0)
UNITS = "days since 2018-01-01 00:00:00"


def _write_bry(path, axes, extra_var=True):
    """axes: {name: (raw_values | None, units | None)}; None values -> skip var."""
    with Dataset(path, "w") as ds:
        ds.createDimension("eta_rho", 2)
        for name, (values, units) in axes.items():
            dim = f"{name}_dim"
            ds.createDimension(dim, len(values) if values is not None else 1)
            var = ds.createVariable(name, "f8", (dim,))
            if units is not None:
                var.units = units
            if values is not None:
                var[:] = np.asarray(values, dtype=float)
        if extra_var:
            ds.createDimension("xi_rho", 3)
            ds.createVariable("zeta_west", "f8", ("eta_rho", "xi_rho"))[:] = 0.0
    return path


def _days(*offsets):
    """Raw axis values in days since 2018-01-01 00:00 for the given offsets."""
    return [float(offset) for offset in offsets]


class CoverageModuleTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def check(self, path, start=START, stop=STOP):
        return check_boundary_coverage(path, start, stop)

    # ---- UNKNOWN: coverage cannot be established -------------------------

    def test_missing_file_is_unknown(self):
        report = self.check(self.root / "absent.nc")
        self.assertEqual(report.status, UNKNOWN)
        self.assertIn("not found", report.reasons[0])

    def test_no_time_axis_is_unknown(self):
        path = _write_bry(self.root / "no_time.nc", {})
        report = self.check(path)
        self.assertEqual(report.status, UNKNOWN)
        self.assertIn("no boundary time axis", report.reasons[0])

    def test_missing_units_is_unknown(self):
        path = _write_bry(self.root / "no_units.nc", {"zeta_time": (_days(1, 2, 3), None)})
        report = self.check(path)
        self.assertEqual(report.status, UNKNOWN)
        self.assertIn("no units", report.reasons[0])

    def test_empty_axis_is_unknown(self):
        path = _write_bry(self.root / "empty.nc", {"zeta_time": ([], UNITS)})
        report = self.check(path)
        self.assertEqual(report.status, UNKNOWN)
        self.assertIn("empty", report.reasons[0])

    def test_undecodable_units_is_unknown(self):
        path = _write_bry(self.root / "bad_units.nc", {"zeta_time": (_days(1, 2, 3), "fortnights since tea")})
        report = self.check(path)
        self.assertEqual(report.status, UNKNOWN)
        self.assertIn("cannot be decoded", report.reasons[0])

    def test_unreadable_file_is_unknown(self):
        path = self.root / "not_netcdf.nc"
        path.write_bytes(b"this is not a NetCDF file")
        report = self.check(path)
        self.assertEqual(report.status, UNKNOWN)
        self.assertIn("cannot be opened", report.reasons[0])

    # ---- INSUFFICIENT: coverage established but too short ---------------

    def test_reversed_time_axis_is_insufficient(self):
        path = _write_bry(self.root / "reversed.nc", {"zeta_time": (_days(3, 2, 1), UNITS)})
        report = self.check(path)
        self.assertEqual(report.status, INSUFFICIENT)
        self.assertIn("not strictly increasing", " ".join(report.reasons))

    def test_duplicate_timestamps_are_insufficient(self):
        path = _write_bry(self.root / "dupes.nc", {"zeta_time": (_days(1, 1, 2), UNITS)})
        report = self.check(path)
        self.assertEqual(report.status, INSUFFICIENT)
        self.assertIn("not strictly increasing", " ".join(report.reasons))

    def test_insufficient_tail_is_insufficient(self):
        # covers 2018-01-02T00 -> 2018-01-02T12, one day short of the stop
        path = _write_bry(self.root / "short_tail.nc", {"zeta_time": (_days(1, 1.5), UNITS)})
        report = self.check(path)
        self.assertEqual(report.status, INSUFFICIENT)
        self.assertIn("before the requested stop", " ".join(report.reasons))

    def test_start_not_covered_is_insufficient(self):
        # starts 2018-01-02T12, after the requested start
        path = _write_bry(self.root / "late_start.nc", {"zeta_time": (_days(1.5, 2.5), UNITS)})
        report = self.check(path)
        self.assertEqual(report.status, INSUFFICIENT)
        self.assertIn("after the requested start", " ".join(report.reasons))

    def test_one_short_axis_among_several_is_insufficient(self):
        """Checking only zeta_time, as an earlier revision did, would pass this."""
        path = _write_bry(
            self.root / "one_short.nc",
            {
                "zeta_time": (_days(1, 2, 3), UNITS),
                "temp_time": (_days(1, 1.25), UNITS),
            },
        )
        report = self.check(path)
        self.assertEqual(report.status, INSUFFICIENT)
        self.assertIn("temp_time", " ".join(report.reasons))
        self.assertEqual({axis.variable for axis in report.axes}, {"zeta_time", "temp_time"})

    def test_inverted_requested_window_is_insufficient(self):
        path = _write_bry(self.root / "fine.nc", {"zeta_time": (_days(1, 2, 3), UNITS)})
        report = self.check(path, start=STOP, stop=START)
        self.assertEqual(report.status, INSUFFICIENT)
        self.assertIn("inverted", report.reasons[0])

    # ---- OK: synthetic but genuinely sufficient -------------------------

    def test_sufficient_synthetic_axis_passes(self):
        path = _write_bry(self.root / "ok.nc", {"zeta_time": (_days(1, 1.5, 2), UNITS)})
        report = self.check(path)
        self.assertEqual(report.status, OK)
        self.assertTrue(report.ok)
        self.assertEqual(report.axes[0].count, 3)
        self.assertEqual(report.axes[0].start, START)
        self.assertEqual(report.axes[0].stop, STOP)

    def test_exact_boundary_equality_passes(self):
        path = _write_bry(self.root / "exact.nc", {"zeta_time": (_days(1, 2), UNITS)})
        self.assertEqual(self.check(path).status, OK)

    def test_multi_axis_all_sufficient_passes(self):
        path = _write_bry(
            self.root / "multi_ok.nc",
            {
                "zeta_time": (_days(1, 2), UNITS),
                "v3d_time": (_days(1, 1.5, 2), UNITS),
                "temp_time": (_days(1, 2), UNITS),
            },
        )
        report = self.check(path)
        self.assertEqual(report.status, OK)
        self.assertEqual(len(report.axes), 3)

    # ---- helpers --------------------------------------------------------

    def test_boundary_time_variables_lists_every_axis(self):
        path = _write_bry(
            self.root / "axes.nc",
            {"zeta_time": (_days(1, 2), UNITS), "salt_time": (_days(1, 2), UNITS)},
        )
        with Dataset(path) as ds:
            self.assertEqual(boundary_time_variables(ds), ["salt_time", "zeta_time"])

    def test_mjd_round_trip_matches_roms_time_ref(self):
        self.assertAlmostEqual(datetime_to_mjd(datetime(1858, 11, 17)), 0.0, places=9)
        # 2018-01-02 is the DSTART the external test .in files carry
        self.assertAlmostEqual(datetime_to_mjd(datetime(2018, 1, 2)), 58120.0, places=6)
        self.assertEqual(mjd_to_datetime(58120.0), datetime(2018, 1, 2))


if __name__ == "__main__":
    unittest.main()
