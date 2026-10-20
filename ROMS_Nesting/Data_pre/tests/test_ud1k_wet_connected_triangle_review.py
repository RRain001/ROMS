"""Connectivity-aware 3x3 triangle fallback tests; synthetic-only."""
import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_wet_connected_triangle_review import (
    _local_connected, _dry_node_inside_triangle, classify_connected)


class CoastalConnectedTriangles(unittest.TestCase):
    def setUp(self):
        y,x=np.indices((6,6))
        self.xy=np.stack((x*1000.,y*1000.),axis=-1)
        self.ll=np.stack((128+x*.01,35+y*.01),axis=-1)
        self.wet=np.zeros((6,6),bool)

    def test_local_connected_in_two_by_two_and_three_by_three(self):
        self.wet[0,0]=self.wet[0,1]=self.wet[1,0]=True
        self.assertTrue(_local_connected(self.wet,np.array([[0,0],[0,1],[1,0]])))
        self.wet[0,2]=True
        self.assertTrue(_local_connected(self.wet,np.array([[0,0],[0,2],[1,0]])))
        self.assertFalse(_local_connected(self.wet,np.array([[0,0],[0,2],[3,0]])))

    def test_broken_wet_graph_rejected(self):
        self.wet[0,0]=self.wet[0,2]=self.wet[2,0]=True
        self.assertFalse(_local_connected(self.wet,np.array([[0,0],[0,2],[2,0]])))

    def test_dry_rho_in_triangle_is_rejected(self):
        self.wet[0:3,0:3]=True
        self.wet[1,1]=False
        nodes=np.array([[0,0],[0,2],[2,0]])
        self.assertTrue(_dry_node_inside_triangle(self.xy,self.wet,nodes,
                                                   self.xy[nodes[:,0],nodes[:,1]]))

    def test_connected_candidate_found_without_coastline(self):
        # 3 wet donors connected inside 3x3, not a single 2x2 triple.
        self.wet[0,0]=self.wet[0,1]=self.wet[0,2]=self.wet[1,0]=True
        r=classify_connected(self.xy,self.ll,self.wet,
                             np.array([450.,100.]),[],parent_cell_m=1000.)
        self.assertEqual(r["status"],"CONNECTED_3X3_COASTLINE_CLEAR_STATIC_CANDIDATE")
        self.assertGreater(r["safe_candidate_count"],0)

    def test_no_connected_triangle_returns_no_candidate(self):
        self.wet[0,0]=self.wet[0,2]=self.wet[2,0]=True
        r=classify_connected(self.xy,self.ll,self.wet,
                             np.array([200.,200.]),[],parent_cell_m=1000.)
        self.assertEqual(r["status"],"NO_COASTLINE_CLEAR_CONNECTED_3X3_TRIANGLE")


if __name__=="__main__":
    unittest.main()
