"""Exact minimal wet-perimeter-RHO hitting-set for native GSHHG-crossing faces."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_perimeter_shoreline_consistency_candidate import minimal_boundary_wet_vertex_cover


class MinimumBoundaryMaskCut(unittest.TestCase):
    def setUp(self):
        self.mask=np.ones((290,438),bool)
        self.top={
            "reports":{
                "u":{"flagged_faces":[{"child_eta_face_zero_based":23,"child_xi_face_zero_based":436}]},
                "v":{"flagged_faces":[
                    {"child_eta_face_zero_based":0,"child_xi_face_zero_based":40},
                    {"child_eta_face_zero_based":0,"child_xi_face_zero_based":42},
                    {"child_eta_face_zero_based":23,"child_xi_face_zero_based":437}
                ]}
            }
        }

    def test_minimal_boundary_source_mask_cut_repairs_four_faces(self):
        before=self.mask.copy()
        coords,r=minimal_boundary_wet_vertex_cover(self.mask,self.top)
        self.assertEqual(coords,[[0,40],[0,42],[23,437]])
        self.assertEqual(r["minimal_removed_boundary_RHO_count"],3)
        self.assertEqual(len(r["repaired_coastline_crossing_faces"]),4)
        self.assertTrue(r["source_ocean_remains_4_connected"])
        np.testing.assert_array_equal(self.mask,before)

    def test_dry_endpoint_source_audit_refused(self):
        self.mask[0,40]=False
        with self.assertRaisesRegex(ValueError,"dry RHO endpoint"):
            minimal_boundary_wet_vertex_cover(self.mask,self.top)

    def test_incomplete_fewer_crossing_faces_refused(self):
        self.top["reports"]["v"]["flagged_faces"].pop()
        with self.assertRaisesRegex(ValueError,"four actual"):
            minimal_boundary_wet_vertex_cover(self.mask,self.top)


if __name__=="__main__":
    unittest.main()
