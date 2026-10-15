"""Synthetic preflight tests for local 3-wet-parent-RHO triangle rule."""
import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_wet_triangle_review import (_barycentric, classify_points,
                                      _crosses_coast, _candidate_index)


class LocalWetTriangle(unittest.TestCase):
    def setUp(self):
        y,x=np.indices((4,4))
        self.xy=np.stack((x.astype(float)*1000,y.astype(float)*1000),axis=-1)
        self.lonlat=np.stack((128+x.astype(float)*.01,
                              35+y.astype(float)*.01),axis=-1)
        self.wet=np.zeros((4,4),dtype=bool)
        self.wet[0,0]=self.wet[0,1]=self.wet[1,0]=True

    def classify(self,coords,lines=None):
        p=np.asarray(coords,dtype=float)
        ll=np.stack((128+p[:,0]/100000, 35+p[:,1]/100000),axis=-1)
        return classify_points(self.xy,self.lonlat,self.wet,p,ll,lines or [])

    def test_inside_three_wet_vertices_has_positive_partition_unity(self):
        a=self.classify([[200,300]])[0]
        self.assertEqual(a["status"],"COASTLINE_CLEAR_LOCAL_TRIANGLE_STATIC_CANDIDATE")
        self.assertEqual(a["best_candidate"]["donor_eta_xi_zero_based"],
                         [[0,0],[0,1],[1,0]])
        self.assertAlmostEqual(sum(a["best_candidate"]["weights"]),1)
        self.assertGreaterEqual(min(a["best_candidate"]["weights"]),0)

    def test_dry_diagonal_not_allow_extrapolation(self):
        r=self.classify([[800,800]])[0]
        self.assertEqual(r["status"],"NO_ENCLOSING_LOCAL_THREE_WET_PARENT_RHO_TRIANGLE")

    def test_three_disconnected_wet_points_no_quad_no_interpolation(self):
        self.wet[:]=False
        self.wet[0,0]=self.wet[2,0]=self.wet[0,2]=True
        r=self.classify([[300,300]])[0]
        self.assertEqual(r["status"],"NO_ENCLOSING_LOCAL_THREE_WET_PARENT_RHO_TRIANGLE")

    def test_coastline_crossing_is_rejected_even_inside_triangle(self):
        coast=[(np.array([128.001,35.0001,128.004,35.006],float),
                np.array([[128.001,35.0001],[128.004,35.006]],float))]
        r=self.classify([[200,300]],coast)[0]
        self.assertEqual(r["status"],"ENCLS_THREE_WET_TRIANGLE_BUT_CROSSES_GSHHG_L1_COAST")

    def test_coastline_far_outside_triangle_keeps_static_candidate(self):
        coast=[(np.array([130.0,36,130.1,36.1]),
                np.array([[130,36],[130.1,36.1]]))]
        r=self.classify([[200,300]],coast)[0]
        self.assertEqual(r["status"],"COASTLINE_CLEAR_LOCAL_TRIANGLE_STATIC_CANDIDATE")

    def test_degenerate_triangle_rejected(self):
        pts=np.array([[0,0],[1,0],[2,0]],float)
        self.assertIsNone(_barycentric(pts,np.array([.5,0])))

    def test_shape_and_all_dry_rejected(self):
        self.wet[:]=False
        xyz,ij,cent,r=_candidate_index(self.xy,self.wet)
        self.assertEqual(len(xyz),0)
        self.assertEqual(len(cent),0)
        self.assertEqual(r,0)
        with self.assertRaisesRegex(ValueError,"incompatible"):
            _candidate_index(self.xy[:,:,0],self.wet)


if __name__=="__main__":
    unittest.main()
