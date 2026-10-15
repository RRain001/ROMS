"""Tests for manifest fail-closed and generic time/vertical RHO donor samples."""
import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_boundary_rho_fallback_map import apply_scalar_stencils


class RhoBoundaryScalarStencils(unittest.TestCase):
    def setUp(self):
        self.a=np.arange(5*5,dtype=float).reshape(5,5)
        self.recs=[
            {"donor_eta_xi_zero_based":[[1,2],[2,2],[2,3]],
             "weights":[.2,.3,.5]},
            {"donor_eta_xi_zero_based":[[3,4]],
             "weights":[1.]}
        ]

    def test_3_wet_weighted_scalar_and_single(self):
        out=apply_scalar_stencils(self.a,self.recs)
        self.assertEqual(out.shape,(2,))
        self.assertAlmostEqual(out[0],.2*7+.3*12+.5*13)
        self.assertAlmostEqual(out[1],19)

    def test_leading_time_and_vertical_axes(self):
        vals=np.stack([self.a,2*self.a],axis=0)
        got=apply_scalar_stencils(vals,self.recs)
        self.assertEqual(got.shape,(2,2))
        np.testing.assert_allclose(got[1],2*got[0],rtol=0,atol=1e-12)
        more=np.stack([vals,vals+10],axis=0)
        self.assertEqual(apply_scalar_stencils(more,self.recs).shape,(2,2,2))

    def test_constant_preservation(self):
        out=apply_scalar_stencils(np.ones((3,5,5)),self.recs)
        np.testing.assert_allclose(out,1.,rtol=0,atol=1e-14)

    def test_nonfinite_source_fails_closed(self):
        bad=self.a.copy()
        bad[1,2]=np.nan
        with self.assertRaisesRegex(ValueError,"not finite"):
            apply_scalar_stencils(bad,self.recs)

    def test_non_rho_input_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"eta_rho"):
            apply_scalar_stencils(np.ones(7),self.recs)


if __name__=="__main__":
    unittest.main()
