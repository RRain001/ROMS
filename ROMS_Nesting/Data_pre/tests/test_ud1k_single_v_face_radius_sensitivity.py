"""Fixed radius sweep does not bypass coast or mutate data."""
import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_single_v_face_radius_sensitivity import test_radii


class RadiusAudit(unittest.TestCase):
    def setUp(self):
        yy,xx=np.indices((9,9))
        self.xy=np.stack((xx.astype(float)*1000,yy.astype(float)*1000),axis=-1)
        self.ll=np.stack((128+xx*.009,35+yy*.009),axis=-1)
        self.wet=np.ones((9,9),bool)

    def test_bounded_radius_detects_first_safe_source(self):
        self.wet[:]=False
        self.wet[2,6]=self.wet[2,7]=True
        target=np.array([2500.,2000.])
        geo=np.array([128.0225,35.018])
        out=test_radii(self.xy,self.ll,self.wet,target,geo,[],median_parent_cell_m=1000)
        self.assertEqual([z["radius_in_parent_cell_widths"] for z in out["radii"]],
                         [2.5,3.,3.5,4.,5.])
        self.assertEqual(out["first_water_visible_radius_parent_cells"],3.5)
        self.assertGreater(out["first_water_visible_candidate_count"],0)

    def test_land_barrier_does_not_become_safe_by_widening(self):
        self.wet[:]=False
        self.wet[2,6]=self.wet[2,7]=True
        target=np.array([2500.,2000.])
        geo=np.array([128.0225,35.018])
        coastline=[(np.array([128.04,34.99,128.04,35.09]),
                    np.array([[128.04,34.99],[128.04,35.09]]))]
        out=test_radii(self.xy,self.ll,self.wet,target,geo,
                       coastline,median_parent_cell_m=1000)
        self.assertIsNone(out["first_water_visible_radius_parent_cells"])
        self.assertEqual(out["first_water_visible_candidate_count"],0)
        self.assertTrue(out["no_cross_land_override"])


if __name__=="__main__":
    unittest.main()
