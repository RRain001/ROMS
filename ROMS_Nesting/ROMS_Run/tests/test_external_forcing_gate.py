#!/usr/bin/env python3
"""Pre-run fail-closed tests for external boundary coverage.

These exercise ``validate_external_forcing_coverage``, the gate that runs before
any ROMS launch.  Synthetic NetCDF only; nothing is executed.
"""

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from netCDF4 import Dataset

CORE = Path(__file__).resolve().parents[1] / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from run_context import parse_infile_metadata, validate_external_forcing_coverage  # noqa: E402

UNITS = "days since 2018-01-01 00:00:00"
# DSTART 58120 == 2018-01-02; NTIMES*DT spans exactly 24 h
INFILE_TEMPLATE = """\
       TITLE = synthetic gate test
    MyAppCPP = JAPAN_SEA
     ININAME == ../input/ini.nc
    BRYNAME == ../input/{bry}
    TIDENAME == none
      NTIMES == {ntimes}
          DT == {dt}d0
      DSTART = {dstart}d0
     TIME_REF = 18581117.0d0
"""


class ExternalForcingGateTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.run_dir = self.root / "run"
        self.input_dir = self.root / "input"
        self.run_dir.mkdir()
        self.input_dir.mkdir()
        self.context = SimpleNamespace(
            case_root=self.root,
            paths=SimpleNamespace(run_dir=self.run_dir, input_dir=self.input_dir),
        )

    def write_bry(self, name, offsets, units=UNITS):
        path = self.input_dir / name
        with Dataset(path, "w") as ds:
            ds.createDimension("zeta_time_dim", len(offsets))
            var = ds.createVariable("zeta_time", "f8", ("zeta_time_dim",))
            if units is not None:
                var.units = units
            var[:] = np.asarray(offsets, dtype=float)
        return path

    def gate(self, bry="bry.nc", ntimes=8640, dt=10.0, dstart=58120.0, extra=""):
        infile = self.run_dir / "ocean_test.in"
        infile.write_text(
            INFILE_TEMPLATE.format(bry=bry, ntimes=ntimes, dt=dt, dstart=dstart) + extra
        )
        metadata = parse_infile_metadata(infile)
        return validate_external_forcing_coverage(
            self.context, metadata, infile.read_text(errors="ignore")
        )

    # ---- refusals -------------------------------------------------------

    def test_missing_boundary_file_is_refused(self):
        issues = self.gate(bry="absent.nc")
        self.assertTrue(issues)
        self.assertIn("cannot be resolved", issues[0])

    def test_unknown_coverage_is_refused(self):
        self.write_bry("bry.nc", [1.0, 2.0], units=None)
        issues = self.gate()
        self.assertTrue(issues)
        self.assertIn("UNKNOWN", issues[0])

    def test_insufficient_coverage_is_refused(self):
        self.write_bry("bry.nc", [1.0, 1.25])  # ends 2018-01-02T06, run needs a full day
        issues = self.gate()
        self.assertTrue(issues)
        self.assertIn("INSUFFICIENT", issues[0])
        self.assertIn("before the requested stop", issues[0])

    def test_start_not_covered_is_refused(self):
        self.write_bry("bry.nc", [1.5, 2.5])  # starts 2018-01-02T12
        issues = self.gate()
        self.assertTrue(issues)
        self.assertIn("after the requested start", issues[0])

    def test_unverified_marker_is_refused_even_with_a_good_file(self):
        self.write_bry("bry.nc", [1.0, 2.0])
        issues = self.gate(extra="! FORCING_UNVERIFIED: not runnable\n")
        self.assertTrue(issues)
        self.assertIn("FORCING_UNVERIFIED", issues[0])

    def test_infile_without_dstart_is_refused(self):
        self.write_bry("bry.nc", [1.0, 2.0])
        infile = self.run_dir / "no_dstart.in"
        infile.write_text(
            "    BRYNAME == ../input/bry.nc\n      NTIMES == 8640\n          DT == 10.0d0\n"
        )
        issues = validate_external_forcing_coverage(
            self.context, parse_infile_metadata(infile), infile.read_text()
        )
        self.assertTrue(issues)
        self.assertIn("must define DSTART, NTIMES and DT", issues[0])

    def test_smoke_with_external_forcing_is_checked_too(self):
        """The gate keys off BRYNAME, not off the mode name."""
        self.write_bry("bry.nc", [1.5])  # starts 2018-01-02T12, after the smoke start
        infile = self.run_dir / "ocean_japan_sea_smoke.in"
        infile.write_text(
            "    BRYNAME == ../input/bry.nc\n      NTIMES == 5\n          DT == 10.0d0\n"
            "      DSTART = 58120.0d0\n"
        )
        issues = validate_external_forcing_coverage(
            self.context, parse_infile_metadata(infile), infile.read_text()
        )
        self.assertTrue(issues)
        self.assertIn("after the requested start", issues[0])

    # ---- accepted -------------------------------------------------------

    def test_sufficient_synthetic_coverage_passes(self):
        self.write_bry("bry.nc", [1.0, 1.5, 2.0])
        self.assertEqual(self.gate(), [])

    def test_exact_window_equality_passes(self):
        self.write_bry("bry.nc", [1.0, 2.0])
        self.assertEqual(self.gate(), [])

    def test_bryname_none_is_not_checked(self):
        self.assertEqual(self.gate(bry="none"), [])


if __name__ == "__main__":
    unittest.main()
