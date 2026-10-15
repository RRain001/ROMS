"""Bounded pure analytical inputs to real-geometry dynamic flux smoke."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_optionb_synthetic_dynamic_section import (
    synthetic_geographic_velocity,dynamic_optionb_sections,
    FRAME_SECONDS,ZETA_METERS)


class DynamicGeometrySignal(unittest.TestCase):
    def test_affine_geographic_flow_varies_with_depth_and_time(self):
        z=np.array([-120.,-60.,0.])
        east0,north0=synthetic_geographic_velocity(z,0.)
        east1,north1=synthetic_geographic_velocity(z,3600.)
        np.testing.assert_allclose(east0,[.176,.188,.2],rtol=0,atol=1e-14)
        np.testing.assert_allclose(north0,[-.112,-.106,-.1],rtol=0,atol=1e-14)
        np.testing.assert_allclose(east1-east0,.036,atol=1e-14)
        np.testing.assert_allclose(north1-north0,.072,atol=1e-14)

    def test_no_nonfinite_time_or_depth_is_accepted(self):
        with self.assertRaisesRegex(ValueError,"invalid"):
            synthetic_geographic_velocity(np.array([0.,np.nan]),1800.)
        with self.assertRaisesRegex(ValueError,"invalid"):
            synthetic_geographic_velocity(np.array([0.,-30.]),np.inf)

    def test_41_layer_three_frame_contract_is_fixed_and_bounded(self):
        self.assertEqual(FRAME_SECONDS,(0.,1800.,3600.))
        self.assertEqual(ZETA_METERS,(.4,1.0,1.6))
        self.assertEqual(len(FRAME_SECONDS),len(ZETA_METERS))
        with self.assertRaisesRegex(ValueError,"bounded"):
            dynamic_optionb_sections(Path("/should/not_be_read"),n=500)

    def test_geographic_signal_is_not_a_parent_roms_history(self):
        east,north=synthetic_geographic_velocity(np.array([-100.,0.]),1800.)
        self.assertTrue(np.isfinite(east).all() and np.isfinite(north).all())
        self.assertGreater(float(np.ptp(east)),0.)
        self.assertGreater(float(np.ptp(north)),0.)


if __name__=="__main__":
    unittest.main()
