"""Synthetic native ROMS C-grid sigma column depth / normal transport geometry tests."""
import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_boundary_vertical_flux_geometry_smoke import _face_section,numerical_smoke_grid


class NativeBoundarySigmaFlux(unittest.TestCase):
    def setUp(self):
        self.h=np.full((290,438),100.0)
        self.pm=np.full_like(self.h,1/950.)
        self.pn=np.full_like(self.h,1/1040.)
        self.rho=np.ones_like(self.h,dtype=bool)
        self.u=self.rho[:,:-1]&self.rho[:,1:]
        self.v=self.rho[:-1,:]&self.rho[1:,:]

    def test_side_and_metric_for_true_normal_faces(self):
        sections={s:_face_section(self.h,self.pm,self.pn,self.u,self.v,s)
                  for s in ("south","north","west","east")}
        self.assertEqual({s:(a["kind"],a["sign"]) for s,a in sections.items()},
                         {"south":("v",-1),"north":("v",1),
                          "west":("u",-1),"east":("u",1)})
        np.testing.assert_allclose(sections["south"]["width_m"],950.)
        np.testing.assert_allclose(sections["east"]["width_m"],1040.)
        self.assertEqual(sections["south"]["mask_native_normal_face"].shape,(438,))
        self.assertEqual(sections["east"]["mask_native_normal_face"].shape,(290,))

    def test_full_open_geometry_sigma_flux_matches_layer_integral(self):
        report=numerical_smoke_grid(self.h,self.pm,self.pn,self.rho,self.u,self.v)
        self.assertEqual(report["wet_normal_face_count"],2*(290+438))
        self.assertTrue(report["all_real_rho_masks_and_bathymetry_unchanged"])
        self.assertEqual(report["physical_velocity_boundary_bry_netcdf"],"NOT_RUN")
        for x in report["normal_sections"]:
            self.assertLess(x["sigma_z_max_layer_sum_error_m"],1e-10)
            self.assertLess(x["depth_mean_vs_3d_flux_absolute_error_m3_per_s"],1e-6)
            self.assertEqual(x["synthetic_constant_scalar_sigma_transfer"],"PASS")

    def test_completely_dry_west_side_has_zero_normal_faces(self):
        self.rho[:,0]=False
        self.u=self.rho[:,:-1]&self.rho[:,1:]
        self.v=self.rho[:-1,:]&self.rho[1:,:]
        report=numerical_smoke_grid(self.h,self.pm,self.pn,self.rho,self.u,self.v)
        west=next(x for x in report["normal_sections"] if x["side"]=="west")
        self.assertEqual(west["native_wet_normal_face_count"],0)
        self.assertTrue(west["static_geometry_no_open_wet_normal_faces"])

    def test_wrong_v_face_mask_is_rejected(self):
        self.v[0,0]=False
        with self.assertRaisesRegex(ValueError,"face masks inconsistent"):
            numerical_smoke_grid(self.h,self.pm,self.pn,self.rho,self.u,self.v)

    def test_bad_metrics_rejected(self):
        self.pm[0,0]=0
        with self.assertRaisesRegex(ValueError,"depth and metrics"):
            numerical_smoke_grid(self.h,self.pm,self.pn,self.rho,self.u,self.v)


if __name__=="__main__":
    unittest.main()
