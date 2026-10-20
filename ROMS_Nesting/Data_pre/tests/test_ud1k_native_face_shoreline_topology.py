"""Synthetic explicit child RHO-neighbor wet-face coastline-crossing audit."""
import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_native_face_shoreline_topology import crossing_wet_faces


class WetFaceCoastlineSegments(unittest.TestCase):
    def setUp(self):
        j,i=np.indices((5,6))
        self.lon=128+i*.009
        self.lat=35+j*.009
        self.wet=np.ones((5,6),bool)

    def test_u_looks_east_west_along_same_j(self):
        # coastline intersects exactly U face i=0, at x=128.0045
        coast=[(np.array([128.0045,34.98,128.0045,35.06]),
                np.array([[128.0045,34.98],[128.0045,35.06]]))]
        result=crossing_wet_faces(self.lon,self.lat,self.wet,"u",coast)
        self.assertEqual(result["wet_perimeter_face_count"],2*(5+5)-4)
        self.assertGreater(result["wet_face_RHO_to_RHO_segment_crosses_GSHHG_count"],0)
        self.assertTrue(any(x["child_xi_face_zero_based"]==0 for x in result["flagged_faces"]))
        self.assertTrue(self.wet.all())

    def test_v_looks_north_south_same_i(self):
        # coast runs east/west at y=35.0045: V face j=0 crosses.
        coast=[(np.array([127.99,35.0045,128.08,35.0045]),
                np.array([[127.99,35.0045],[128.08,35.0045]]))]
        result=crossing_wet_faces(self.lon,self.lat,self.wet,"v",coast)
        self.assertEqual(result["wet_perimeter_face_count"],2*(4+6)-4)
        self.assertTrue(any(x["child_eta_face_zero_based"]==0 for x in result["flagged_faces"]))
        self.assertTrue(self.wet.all())

    def test_no_land_crossing_stays_empty(self):
        far=[(np.array([129,36,129.1,36.1]),
              np.array([[129.,36.],[129.1,36.1]]))]
        for kind in ("u","v"):
            report=crossing_wet_faces(self.lon,self.lat,self.wet,kind,far)
            self.assertEqual(report["wet_face_RHO_to_RHO_segment_crosses_GSHHG_count"],0)

    def test_nonwet_face_not_checked(self):
        self.wet[0,0]=False
        coast=[(np.array([128.0045,34.999,128.0045,35.001]),
                np.array([[128.0045,34.999],[128.0045,35.001]]))]
        r=crossing_wet_faces(self.lon,self.lat,self.wet,"u",coast)
        self.assertEqual(r["wet_face_RHO_to_RHO_segment_crosses_GSHHG_count"],0)


if __name__=="__main__":
    unittest.main()
