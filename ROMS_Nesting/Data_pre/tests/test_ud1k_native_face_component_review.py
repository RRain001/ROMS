"""Synthetic tests of independent native U/V source face coastal fallback."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_native_face_component_review import _native_face_source


class NativeComponentStencil(unittest.TestCase):
    def setUp(self):
        j,i=np.indices((5,6))
        self.xy=np.stack((i.astype(float)*1000,j.astype(float)*1000),axis=-1)
        self.ll=np.stack((128+i*.009,35+j*.009),axis=-1)
        self.wet=np.ones((5,6),bool)
        self.target=np.array([2400.,2400.])
        self.geo=np.array([128.0216,35.0216])

    def test_native_face_2d_stencil_constant_preservation(self):
        z=_native_face_source(self.xy,self.ll,self.wet,self.target,self.geo,[],
                              parent_cell_m=1000,face_kind="u")
        nodes=z["selected_native_component_faces"]
        self.assertGreaterEqual(len(nodes),2)
        self.assertAlmostEqual(sum(q["weight"] for q in nodes),1.,places=13)
        self.assertTrue(all(q["weight"]>=0 and q["distance_m"]<2500 for q in nodes))
        self.assertEqual(z["source_location"],"ACTUAL_NATIVE_ES3K_LON_LAT_U")

    def test_rays_blocked_by_shoreline_fail_closed(self):
        self.wet[:,:3]=False
        self.target=np.array([2300.,2000.])
        self.geo=np.array([128.0207,35.018])
        coastline=[(np.array([128.022,34.99,128.022,35.06]),
                    np.array([[128.022,34.99],[128.022,35.06]]))]
        r=_native_face_source(self.xy,self.ll,self.wet,self.target,self.geo,
                              coastline,parent_cell_m=1000,face_kind="v")
        self.assertEqual(r["coastline_visible_candidate_count"],0)
        self.assertGreater(r["rejected_shoreline_rays"],0)

    def test_all_dry_source_reports_no_candidate(self):
        self.wet[:]=False
        result=_native_face_source(self.xy,self.ll,self.wet,
                                   self.target,self.geo,[],parent_cell_m=1000,face_kind="u")
        self.assertEqual(result["coastline_visible_candidate_count"],0)


if __name__=="__main__":
    unittest.main()
