"""ROMS sigma-z geometry and barotropic transport synthetic invariants."""
import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_vertical_flux_primitives import (
    stretching4,vtransform2_depth,remap_profiles_in_z,
    depth_average_velocity,normal_section_flux)


class ROMSVerticalPrimitives(unittest.TestCase):
    def test_stretching4_matches_original_endpoints_and_monotonic(self):
        for theta_s,theta_b in ((0,0),(5,0),(7,2),(10,3)):
            sw,cw=stretching4(41,theta_s,theta_b,at="w")
            sr,cr=stretching4(41,theta_s,theta_b,at="rho")
            self.assertEqual(sw.shape,(42,))
            self.assertEqual(sr.shape,(41,))
            np.testing.assert_allclose([sw[0],sw[-1],cw[0],cw[-1]],[-1,0,-1,0],atol=1e-14)
            self.assertTrue(np.all(np.diff(sw)>0))
            self.assertTrue(np.all(np.diff(cw)>0))
            self.assertTrue(np.all(np.diff(sr)>0))
            self.assertTrue(np.all(np.diff(cr)>0))

    def test_depth_w_bottom_top_and_positive_monotonic_thickness(self):
        h=np.array([[5.,30.,150.],[40.,200.,500.]])
        zeta=np.array([[[0.,.2,-.2],[1.,0.,.5]],
                       [[.4,.5,-.1],[0.,-.1,.1]]])
        zw=vtransform2_depth(h,zeta,n=41,hc=50,theta_s=7,theta_b=2,at="w")
        zr=vtransform2_depth(h,zeta,n=41,hc=50,theta_s=7,theta_b=2,at="rho")
        self.assertEqual(zw.shape,(2,42,2,3))
        self.assertEqual(zr.shape,(2,41,2,3))
        np.testing.assert_allclose(zw[:,0],-h[None,:,:],atol=1e-12)
        np.testing.assert_allclose(zw[:,-1],zeta,atol=1e-12)
        self.assertTrue(np.all(np.diff(zw,axis=1)>0))
        self.assertTrue(np.all(zw[:,1:]>=zr-1e-9))
        self.assertTrue(np.all(zw[:,:-1]<=zr+1e-9))

    def test_rho_profile_constant_and_affine_z(self):
        h=np.array([20.,100.,600.])
        zeta=np.array([[0.,0.,0.]])
        parent=vtransform2_depth(h,zeta,n=41,hc=30,theta_s=5,theta_b=1,at="rho")
        child=vtransform2_depth(h,zeta,n=27,hc=30,theta_s=4,theta_b=.6,at="rho")
        c=remap_profiles_in_z(parent,np.ones_like(parent)*12.,child)
        np.testing.assert_allclose(c["values"],12,atol=1e-12)
        # Interior affine data reconstructs exact linear variation in z.
        field=parent*2+3
        out=remap_profiles_in_z(parent,field,child)
        bottom=child>=parent[:,0:1,:]
        top=child<=parent[:,-1:,:]
        inside=bottom&top
        np.testing.assert_allclose(out["values"][inside],(child*2+3)[inside],atol=1e-9)

    def test_vertical_clamp_is_explicit_counted(self):
        zp=np.array([[[ -10.,-20.],[-5.,-10.],[-1.,-1.]]])
        vals=zp*2
        zc=np.array([[[-11.,-19.],[-4.,-11.],[0.,0.]]])
        out=remap_profiles_in_z(zp,vals,zc)
        self.assertGreater(out["clamped_below_parent_bottom"],0)
        self.assertGreater(out["clamped_above_parent_top"],0)
        self.assertAlmostEqual(out["values"][0,0,0],-20)
        self.assertAlmostEqual(out["values"][0,-1,-1],-2)

    def test_depth_average_consistent_uniform_and_variable_layers(self):
        w=np.array([[[ -6.,-9.],[-5.,-6.],[-1.,-2.],[0.,0.]]])
        v=np.array([[[2.,4.],[2.,4.],[2.,4.]]])
        np.testing.assert_allclose(depth_average_velocity(v,w),[[2.,4.]],atol=1e-12)
        variable=np.array([[[1.,2.],[2.,2.],[4.,4.]]])
        got=depth_average_velocity(variable,w)
        want=np.sum(variable*np.diff(w,axis=1),axis=1)/np.sum(np.diff(w,axis=1),axis=1)
        np.testing.assert_allclose(got,want,atol=1e-12)

    def test_outward_normal_flux_sign_and_wet_mask(self):
        u=np.array([2.,-1.,100.])
        depth=np.array([10.,20.,10.])
        length=np.array([1000.,2000.,1000.])
        wet=np.array([True,True,False])
        self.assertAlmostEqual(normal_section_flux(u,depth,length,wet,sign=1),-20000)
        self.assertAlmostEqual(normal_section_flux(u,depth,length,wet,sign=-1),20000)
        with self.assertRaises(ValueError):
            normal_section_flux(u,depth,length,wet,sign=0)

    def test_monotonicity_input_checks(self):
        with self.assertRaises(ValueError):
            stretching4(0,5,2)
        with self.assertRaises(ValueError):
            vtransform2_depth(np.array([0.]),np.array([0.]),n=41,hc=50,theta_s=7,theta_b=2)
        with self.assertRaises(ValueError):
            remap_profiles_in_z(np.array([[[-2.],[-3.]]]),np.ones((1,2,1)),np.ones((1,1,1)))
        with self.assertRaises(ValueError):
            depth_average_velocity(np.ones((1,2)),np.ones((1,3)))


if __name__=="__main__":
    unittest.main()
