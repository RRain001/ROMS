"""Synthetic math and coastline tests for full UD1K wet RHO perimeter map.

No synthetic evidence is presented as real GEBCO or ROMS physics validation.
"""
from __future__ import annotations

import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_full_rho_boundary_map import inverse_bilinear,assemble


class InverseBilinear(unittest.TestCase):
    def test_parallelogram_center_and_affine_reproduction(self):
        quad=np.array([[0.,0.],[2.,0.],[3.,2.],[1.,2.]])
        target=np.array([1.35,.7])
        w=inverse_bilinear(quad,target)
        self.assertIsNotNone(w)
        np.testing.assert_allclose(w.sum(),1.,atol=1e-12)
        np.testing.assert_allclose(w @ quad,target,atol=1e-10)
        np.testing.assert_allclose(w,np.array([.4225,.2275,.1225,.2275]),atol=.2) # geometry is skewed
        affine=np.array([1+2*x-3*y for x,y in quad])
        self.assertAlmostEqual(float(w@affine),1+2*target[0]-3*target[1],places=10)

    def test_irregular_convex_quad_and_boundaries(self):
        quad=np.array([[0.,0.],[3.,.2],[2.8,2.7],[-.4,2.4]])
        for s,t in ((0,0),(1,1),(.5,.5),(.1,.9),(.9,.1),(.999,.001)):
            w=np.array([(1-s)*(1-t),s*(1-t),s*t,(1-s)*t])
            target=w@quad
            actual=inverse_bilinear(quad,target)
            self.assertIsNotNone(actual,(s,t))
            np.testing.assert_allclose(actual,w,atol=1e-8)
        self.assertIsNone(inverse_bilinear(quad,np.array([9.,9.])))

    def test_bowtie_and_bad_values_rejected(self):
        bad=np.array([[0.,0.],[2.,2.],[0.,2.],[2.,0.]])
        self.assertIsNone(inverse_bilinear(bad,np.array([1.,1.])))
        with self.assertRaisesRegex(ValueError,"finite"):
            inverse_bilinear(np.full((4,2),np.nan),np.array([1.,1.]))
        flat=np.array([[0.,0.],[1.,0.],[2.,0.],[3.,0.]])
        self.assertIsNone(inverse_bilinear(flat,np.array([1.,0.])))


class FullBoundaryMapSynthetic(unittest.TestCase):
    def setUp(self):
        # Parent 11x11, child 290x438; synthetic child has 1017 wet RHO perimeter
        # positions. A diagonal 27-point subset is forced into child mapping.
        jj,ii=np.indices((14,14))
        self.pxy=np.stack((ii.astype(float)*1.5e3,jj.astype(float)*1.5e3),axis=-1)
        self.pll=self.pxy/100000 + np.array([128.,35.])
        self.pwet=np.ones((14,14),bool)
        ny,nx=290,438
        self.cwet=np.zeros((ny,nx),bool)
        # Exact real count 1017: 2*(290+438)-4=1452, set 435 dry.
        rim=np.zeros_like(self.cwet)
        rim[0,:]=rim[-1,:]=True
        rim[:,0]=rim[:,-1]=True
        ij=np.argwhere(rim)
        wet_idx=ij[:1017]
        self.cwet[wet_idx[:,0],wet_idx[:,1]]=True
        yy,xx=np.indices(self.cwet.shape)
        self.cxy=np.stack(((xx*3.4)%12000+3000.,(yy*3.0)%12000+3000.),axis=-1)
        self.cll=self.cxy/100000+np.array([128.,35.])
        self.fallback={"records":[]}
        for j,i in wet_idx[:27]:
            self.fallback["records"].append({
                "child_eta_rho_zero_based":int(j),"child_xi_rho_zero_based":int(i),
                "child_lon":float(self.cll[j,i,0]),"child_lat":float(self.cll[j,i,1]),
                "donor_eta_xi_zero_based":[[2,2]],"weights":[1.],
                "method":"SINGLE_DONOR_COAST_VISIBLE_EXTRAPOLATION_CANDIDATE",
                "coastline_visible":True,
            })

    def test_unduplicated_wet_perimeter_including_corner(self):
        data=assemble(self.pxy,self.pll,self.pwet,self.cxy,self.cll,
                      self.cwet,self.fallback,[])
        self.assertEqual(data["counts"]["total_wet_perimeter"],1017)
        self.assertEqual(data["counts"]["ordinary_four_wet_quad"],990)
        self.assertEqual(data["counts"]["audited_27_fallback"],27)
        self.assertEqual(data["counts"]["ordinary_quad_crosses_GSHHG_level1"],0)
        rows=data["records"]
        self.assertEqual(len(rows),1017)
        self.assertEqual(len(set((r["child_eta_rho_zero_based"],r["child_xi_rho_zero_based"])
                                 for r in rows)),1017)
        for row in rows:
            self.assertAlmostEqual(sum(row["weights"]),1.,places=11)

    def test_strict_fallback_gating(self):
        clone={"records":self.fallback["records"][:-1]}
        with self.assertRaisesRegex(ValueError,"27"):
            assemble(self.pxy,self.pll,self.pwet,self.cxy,self.cll,
                     self.cwet,clone,[])

    def test_coastline_crossing_quad_is_flagged_not_silently_approved(self):
        coast=[(np.array([128.01,35.0,128.01,35.2]),
                np.array([[128.01,35.0],[128.01,35.2]]))]
        r=assemble(self.pxy,self.pll,self.pwet,self.cxy,self.cll,
                   self.cwet,self.fallback,coast)
        self.assertGreater(r["counts"]["ordinary_quad_crosses_GSHHG_level1"],0)


if __name__=="__main__":
    unittest.main()
