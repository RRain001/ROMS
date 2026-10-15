"""Synthetic C-grid parent RHO collocation / angle-rotation contract."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_boundary_cgrid_velocity import (
    face_support_report,rotate_parent_to_child_rho)


class CgridRhoVectorAudit(unittest.TestCase):
    def setUp(self):
        self.wet=np.ones((5,6),bool)
        self.ang=np.zeros((5,6))
        self.target_angle=np.zeros((3,3))
        self.u=np.full((5,5),1.)
        self.v=np.zeros((4,6))
        self.rec=[{"child_eta_rho_zero_based":1,
                   "child_xi_rho_zero_based":2,
                   "donor_eta_xi_zero_based":[[2,2],[2,3]],
                   "weights":[.25,.75]}]

    def calc(self):
        return rotate_parent_to_child_rho(self.u,self.v,self.wet,self.ang,
                                          self.target_angle,self.rec)

    def test_90deg_parent_rotation_source_u_becomes_true_north(self):
        self.ang[:]=np.pi/2
        r=self.calc()
        np.testing.assert_allclose(r["east_at_child_rho"],0,atol=1e-14)
        np.testing.assert_allclose(r["north_at_child_rho"],1,atol=1e-14)

    def test_90deg_child_rotation_turns_east_into_negative_child_v(self):
        self.target_angle[:]=np.pi/2
        r=self.calc()
        np.testing.assert_allclose(r["child_u_axis_at_rho_only"],0,atol=1e-14)
        np.testing.assert_allclose(r["child_v_axis_at_rho_only"],-1,atol=1e-14)

    def test_local_angle_differs_by_donor_not_area_mean(self):
        self.ang[2,2]=0
        self.ang[2,3]=np.pi/2
        result=self.calc()
        np.testing.assert_allclose(result["east_at_child_rho"],[.25],atol=1e-13)
        np.testing.assert_allclose(result["north_at_child_rho"],[.75],atol=1e-13)

    def test_one_wet_adjacent_face_prefer_no_dry_face(self):
        self.rec=self.rec[:1]
        self.rec[0]["donor_eta_xi_zero_based"]=[[2,2]]
        self.rec[0]["weights"]=[1.]
        self.wet[2,1]=False
        self.u[2,1]=np.nan  # disabled face, never sampled
        self.u[2,2]=2
        r=self.calc()
        np.testing.assert_allclose(r["east_at_child_rho"],[2])
        report=face_support_report(self.wet,self.rec)
        self.assertEqual(report["receiver_RHO_points_with_missing_U_or_V_donor"],0)
        self.assertEqual(report["u_one_wet_face_samples"],1)

    def test_missing_crosscomponent_face_is_not_filled_with_zero(self):
        self.wet[:]=False
        self.wet[2,2]=self.wet[2,3]=True
        r=face_support_report(self.wet,self.rec)
        self.assertEqual(r["receiver_RHO_points_with_missing_U_or_V_donor"],1)
        self.assertTrue(r["problem_points"][0]["unsupported_nonzero_donors"][0]["missing_v"])
        with self.assertRaisesRegex(ValueError,"insufficient parent C-grid wet-face support"):
            self.calc()

    def test_leading_time_and_sigma_dimensions(self):
        u=np.stack([self.u,self.u*2],axis=0)
        v=np.stack([self.v,self.v],axis=0)
        out=rotate_parent_to_child_rho(u,v,self.wet,self.ang,
                                       self.target_angle,self.rec)
        self.assertEqual(out["east_at_child_rho"].shape,(2,1))
        np.testing.assert_allclose(out["east_at_child_rho"][:,0],[1,2])

    def test_reject_wrong_u_stagger_dimensions(self):
        with self.assertRaisesRegex(ValueError,"staggered dimensions"):
            rotate_parent_to_child_rho(np.ones((5,6)),self.v,self.wet,
                                       self.ang,self.target_angle,self.rec)


if __name__=="__main__":
    unittest.main()
