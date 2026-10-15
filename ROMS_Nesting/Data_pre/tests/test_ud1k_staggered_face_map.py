"""Independent native U/V boundary-face coordinate, mask and vector tests."""
import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_staggered_face_map import (
    supported_rho_for_both_native_faces,wet_perimeter_ij,
    generate_face_records,rotate_parent_collocated_to_child_face)


class NativeFaceBoundaryMappings(unittest.TestCase):
    def setUp(self):
        j,i=np.indices((8,8))
        self.pxy=np.stack((i.astype(float)*1000,
                           j.astype(float)*1000),axis=-1)
        self.pll=np.stack((128+i*.009,35+j*.009),axis=-1)
        self.wet=np.ones((8,8),bool)
        self.child_xy=self.pxy[1:5,1:6].copy()
        self.child_ll=self.pll[1:5,1:6].copy()
        self.child_mask=np.ones((4,5),bool)

    def case(self,kind="u",coast=None,mask=None):
        return generate_face_records(
            self.pxy,self.pll,self.wet,self.child_xy,self.child_ll,
            self.child_mask if mask is None else mask,
            coast or [],parent_cell_m=1000.,face_kind=kind)

    def test_parent_face_supported_mask_not_only_wet_rho(self):
        self.wet[:]=False
        self.wet[2,2]=True
        support=supported_rho_for_both_native_faces(self.wet)
        self.assertFalse(support[2,2])
        self.wet[2,3]=self.wet[3,2]=True
        support=supported_rho_for_both_native_faces(self.wet)
        self.assertTrue(support[2,2])
        self.assertTrue(support[2,3])
        self.assertTrue(support[3,2])

    def test_rim_deduplicates_corners_and_excludes_dry_face(self):
        mask=np.ones((4,5),bool)
        mask[0,0]=False
        ij=wet_perimeter_ij(mask)
        self.assertEqual(len(ij),2*(4+5)-4-1)
        self.assertEqual(len(set(map(tuple,ij))),len(ij))
        self.assertFalse(any(np.array_equal(p,[0,0]) for p in ij))

    def test_u_and_v_independent_physical_face_locations(self):
        u=self.case("u")
        self.assertEqual(u["native_wet_boundary_face_count"],14)
        self.assertEqual(u["side_counts_corner_overlap"],{
            "south":5,"north":5,"west":4,"east":4})
        self.assertEqual(u["unresolved_face_receivers"],0)
        for row in u["records"]:
            self.assertTrue(row["GSHHG_L1_coastline_clear"])
            self.assertTrue(row["native_parent_U_and_V_wet_face_support"])
            self.assertAlmostEqual(sum(row["weights"]),1)
            self.assertEqual(row["method"],"FOUR_SUPPORTED_PARENT_RHO_BILINEAR")
        v=self.case("v")
        self.assertEqual(v["native_wet_boundary_face_count"],14)
        self.assertEqual(v["target_face_kind"],"v")

    def test_1_of_4_rho_dry_leaves_triangle_or_extrapolation(self):
        self.wet[1,1]=False
        d=self.case()
        self.assertEqual(d["unresolved_face_receivers"],0)
        self.assertEqual(d["native_wet_boundary_face_count"],14)
        for row in d["records"]:
            self.assertAlmostEqual(sum(row["weights"]),1)

    def test_real_shoreline_line_intersection_changes_stencil(self):
        # A north-south coast segment cuts quads straddling x=2500 m.
        coast=[(np.array([128.0225,35.0,128.0225,35.08]),
                np.array([[128.0225,35.0],[128.0225,35.08]]))]
        d=self.case(coast=coast)
        self.assertEqual(d["unresolved_face_receivers"],0)
        self.assertGreater(
            sum(v for k,v in d["counts_by_source_method"].items()
                if k!="FOUR_SUPPORTED_PARENT_RHO_BILINEAR"),0)

    def test_90deg_local_parent_and_child_face_rotation(self):
        u=self.case("u")
        z=np.ones((1,8,7))
        v=np.zeros((1,7,8))
        ap=np.full((8,8),np.pi/2)
        ac=np.zeros((4,5))
        out=rotate_parent_collocated_to_child_face(z,v,self.wet,ap,ac,u)
        np.testing.assert_allclose(out["east_at_actual_face"],0,atol=1e-13)
        np.testing.assert_allclose(out["north_at_actual_face"],1,atol=1e-13)
        np.testing.assert_allclose(out["child_axis_velocity_at_actual_face"],0,atol=1e-13)
        vv=self.case("v")
        result=rotate_parent_collocated_to_child_face(z,v,self.wet,ap,
                                                       ac,vv)
        np.testing.assert_allclose(
            result["child_axis_velocity_at_actual_face"],1,atol=1e-13)

    def test_no_faces_does_not_invent_velocity_or_fill_zero(self):
        self.wet[:]=False
        self.wet[2,2]=True
        with self.assertRaisesRegex(ValueError,"no 3-supported-vertex"):
            self.case()

    def test_wrong_face_kind_fails(self):
        with self.assertRaisesRegex(ValueError,"face_kind"):
            self.case("rho")


if __name__=="__main__":
    unittest.main()
