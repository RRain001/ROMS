"""Coast-safe wet-donor fallback: synthetic regression contracts only."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_coastal_waterpath_fallback import (
    _connected_subset,_segment_crosses_coast,classify_visible_wet_donors)


class WaterVisibleCoastalFallback(unittest.TestCase):
    def setUp(self):
        j,i=np.indices((10,10))
        self.xy=np.stack((i*1000.,j*1000.),axis=-1)
        self.ll=np.stack((128+i*.01,35+j*.01),axis=-1)
        self.wet=np.ones((10,10),bool)
        self.target=np.array([5200.,5200.])
        self.geopoint=np.array([128.052,35.052])

    def calc(self,coast=None,*,radius=2.5):
        return classify_visible_wet_donors(
            self.xy,self.ll,self.wet,self.target,self.geopoint,
            coast or [],median_cell_m=1000,max_cell_radius=radius)

    def test_two_or_more_wet_sources_and_weights(self):
        d=self.calc()
        self.assertEqual(d["status"],"MULTI_DONOR_COAST_VISIBLE_IDW_EXTRAPOLATION_CANDIDATE")
        self.assertGreaterEqual(len(d["selected_donors"]),2)
        self.assertAlmostEqual(sum(r["weight"] for r in d["selected_donors"]),1.)
        self.assertTrue(all(r["weight"]>=0 for r in d["selected_donors"]))
        self.assertLessEqual(d["max_selected_distance_m"],2500+1e-6)
        self.assertTrue(d["extrapolation_not_enclosing_interpolation"])

    def test_coastline_separates_target_and_parent(self):
        # Every segment from target to wet donors passes the vertical barrier.
        self.wet[:,:6]=False
        self.target=np.array([5300.,5000.])
        self.geopoint=np.array([128.053,35.050])
        coast=[(np.array([128.054,34.99,128.054,35.09]),
                np.array([[128.054,34.99],[128.054,35.09]]))]
        a=self.calc(coast)
        self.assertEqual(a["status"],"NO_VISIBLE_PARENT_WET_DONOR_WITHIN_RADIUS")
        self.assertGreater(a["rejected_GSHHG_L1_coastline"],0)

    def test_no_neighbors_in_bounded_search(self):
        self.wet[:]=False
        self.wet[0,0]=True
        a=self.calc()
        self.assertEqual(a["status"],"NO_VISIBLE_PARENT_WET_DONOR_WITHIN_RADIUS")

    def test_graph_disconnect_excludes_second_basin_donor(self):
        m=np.zeros((10,10),bool)
        m[4,4]=m[4,5]=m[5,4]=True
        m[6,6]=m[6,7]=True
        subset=_connected_subset(m,(4,4),[(4,4),(4,5),(6,6)],max_hops=8)
        self.assertEqual(subset,{(4,4),(4,5)})

    def test_single_wet_candidate_uses_weight_one(self):
        self.wet[:]=False
        self.wet[5,5]=True
        a=self.calc()
        self.assertEqual(a["status"],"SINGLE_DONOR_COAST_VISIBLE_EXTRAPOLATION_CANDIDATE")
        self.assertEqual(a["selected_donors"][0]["weight"],1.)

    def test_intersecting_shoreline_segment_rejected(self):
        near=np.array([128.055,35.049])
        p=np.array([128.051,35.051])
        coast=[(np.array([128.053,35.04,128.053,35.06]),
                np.array([[128.053,35.04],[128.053,35.06]]))]
        self.assertTrue(_segment_crosses_coast(near,p,coast))
        self.assertFalse(_segment_crosses_coast(np.array([128.052,35.049]),p,coast))


if __name__=="__main__":
    unittest.main()
