"""Fast offline synthetic source fixture contract for real Option B archive job.

These tests use a *tiny* 4x5 artificial ALL-WET parent, not the real
732x464 source grid; archive-based full source + real child exercised in
a separate opt-in GitHub job.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from netCDF4 import Dataset,date2num

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
import ud1k_optionb_end_to_end_synthetic_parent as fixture
from ud1k_parent_history_contract import validate_parent_history


class ArtificialFullSourceSmoke(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.parent=self.root/"SYNTHETIC_4x5_source_grid.nc"
        self.history=self.root/"SYNTHETIC_4x5_history.nc"

    def build(self):
        with patch.object(fixture,"SOURCE_RHO_SHAPE",(4,5)):
            fixture.make_explicitly_artificial_parent(self.parent,self.history)

    def test_two_frame_full_Cgrid_parent_history_admitted_but_synthetic(self):
        self.build()
        report=validate_parent_history(self.parent,self.history,scan_values=True)
        self.assertEqual(report["time_count"],2)
        self.assertEqual(report["n_s_rho"],3)
        self.assertTrue(report["full_wet_values_scanned"])
        with Dataset(self.parent) as g,Dataset(self.history) as h:
            self.assertIn("FICTIONAL_ALL_WET",g.getncattr("source_status"))
            self.assertIn("FICTIONAL_ALL_WET",h.getncattr("source_status"))
            self.assertEqual(g["mask_rho"].shape,(4,5))
            self.assertEqual(g["mask_u"].shape,(4,4))
            self.assertEqual(g["mask_v"].shape,(3,5))
            np.testing.assert_allclose(h["ocean_time"][:],[0.,3600.],atol=0)
            np.testing.assert_allclose(h["zeta"][0],.2,rtol=0,atol=1e-7)
            np.testing.assert_allclose(h["zeta"][1],.4,rtol=0,atol=1e-7)
            np.testing.assert_allclose(h["u"][0],.15,rtol=0,atol=1e-7)
            np.testing.assert_allclose(h["v"][1],-.06,rtol=0,atol=1e-7)

    def test_refuses_to_overwrite_even_one_existing_fixture(self):
        self.parent.write_bytes(b"existing user contents")
        with patch.object(fixture,"SOURCE_RHO_SHAPE",(4,5)):
            with self.assertRaisesRegex(ValueError,"must not overwrite"):
                fixture.make_explicitly_artificial_parent(self.parent,self.history)
        self.assertEqual(self.parent.read_bytes(),b"existing user contents")
        self.assertFalse(self.history.exists())

    def test_mjd_axis_is_days_and_source_axis_is_seconds(self):
        self.assertGreater(float(fixture.TARGET_TIMES[0]),60000.)
        np.testing.assert_allclose(np.diff(fixture.TARGET_TIMES),1/24.,
                                   rtol=1e-8,atol=1e-11)
        np.testing.assert_allclose(fixture.PARENT_TIMES,[0.,3600.],atol=0)
        self.assertEqual(fixture.CHILD_N,4)
        self.assertEqual(fixture.SOURCE_RHO_SHAPE,(732,464))

    def test_real_optionb_is_not_a_real_source_grid_or_hydrodynamics(self):
        self.build()
        with Dataset(self.history) as d:
            self.assertIn("NOT_ROM",d.getncattr("source_status"))
        self.assertIn("SYNTHETIC",self.history.name)


if __name__=="__main__":
    unittest.main()
