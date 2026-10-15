"""Synthetic 3-of-4 parent quad coastal repair tests."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_full_rho_coastline_repair import choose_coastline_safe_triangle
from ud1k_wet_triangle_review import _crosses_coast


class SameQuadCoastlineRepair(unittest.TestCase):
    def setUp(self):
        self.xy=np.zeros((2,2,2),dtype=float)
        self.xy[0,0]=[0,0]
        self.xy[0,1]=[1000,0]
        self.xy[1,1]=[1000,1000]
        self.xy[1,0]=[0,1000]
        self.ll=self.xy/100000+np.array([128,35])
        self.wet=np.ones((2,2),dtype=bool)
        self.nodes=[[0,0],[0,1],[1,1],[1,0]]
        self.target=np.array([100.,100.])
        self.coast=[(np.array([128.008,35.006,128.008,35.011]),
                     np.array([[128.008,35.006],[128.008,35.011]]))]

    def test_original_quad_crosses_but_subtriangle_avoids_land(self):
        full_geo=self.ll[[0,0,1,1],[0,1,1,0]]
        self.assertTrue(_crosses_coast(full_geo,self.coast))
        r=choose_coastline_safe_triangle(self.xy,self.ll,self.wet,self.nodes,
                                         self.target,self.coast)
        self.assertIsNotNone(r)
        self.assertEqual(r["method"],"COASTLINE_CLEAR_THREE_OF_FOUR_WET_PARENT_RHO_TRIANGLE")
        self.assertFalse(r["GSHHG_level1_coastline_intersection"])
        self.assertEqual(len(r["weights"]),3)
        self.assertAlmostEqual(sum(r["weights"]),1.,places=12)
        self.assertTrue(all(x>=0 for x in r["weights"]))
        donor=np.array([self.xy[j,i] for j,i in r["donor_eta_xi_zero_based"]])
        np.testing.assert_allclose(np.asarray(r["weights"])@donor,self.target,atol=1e-10)

    def test_coast_through_target_fails_all_three_wet_triangles(self):
        cross=[(np.array([128.001,35.0,128.001,35.01]),
                np.array([[128.001,35.0],[128.001,35.01]]))]
        r=choose_coastline_safe_triangle(self.xy,self.ll,self.wet,self.nodes,
                                         self.target,cross)
        self.assertIsNone(r)

    def test_dry_parent_cannot_enter_three_point_repair(self):
        self.wet[0,0]=False
        self.wet[1,0]=False
        r=choose_coastline_safe_triangle(self.xy,self.ll,self.wet,self.nodes,
                                         self.target,[])
        self.assertIsNone(r)


if __name__=="__main__":
    unittest.main()
