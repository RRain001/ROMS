"""Small synthetic ES3K history -> child C-grid RHO/U/V full preview regression."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from netCDF4 import Dataset

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_boundary_remap_preview import prepare_boundary_preview,physical_z
from test_ud1k_parent_history_contract import synthetic_parent_grid,synthetic_parent_history
from test_ud1k_bry_schema_contract import child_grid


def all_wet_rim(mask):
    rim=np.zeros_like(mask,dtype=bool)
    rim[0,:]=rim[-1,:]=True
    rim[:,0]=rim[:,-1]=True
    return np.argwhere(rim&mask)


def maps_from_synthetic_grid(path):
    # Explicit test-only certified metadata. This is NOT a GSHHG audit.
    rho=[]
    uv={"u":{"records":[]},"v":{"records":[]}}
    with Dataset(path) as f:
        for kind in ("rho","u","v"):
            for j,i in all_wet_rim(f["mask_"+kind][:]):
                j,i=int(j),int(i)
                base={"weights":[.5,.5]}
                if kind=="rho":
                    rho.append(dict(base,child_eta_rho_zero_based=j,
                                     child_xi_rho_zero_based=i,
                                     donor_eta_xi_zero_based=[[1,2],[1,3]],
                                     coastline_visible=True))
                else:
                    uv[kind]["records"].append(dict(base,child_eta_face_zero_based=j,
                        child_xi_face_zero_based=i,
                        donor_parent_rho_eta_xi_zero_based=[[1,2],[1,3]],
                        GSHHG_L1_coastline_clear=True,
                        native_parent_U_and_V_wet_face_support=True))
    return {"records":rho},{"reports":uv}


class ExperimentalSourceToChildNumerics(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.parent=Path(tmp.name)/"SYNTHETIC_es3k_grid.nc"
        self.history=Path(tmp.name)/"SYNTHETIC_es3k_his.nc"
        self.child=Path(tmp.name)/"SYNTHETIC_ud1k_grid.nc"
        synthetic_parent_grid(self.parent)
        synthetic_parent_history(self.history,n=3)
        child_grid(self.child)
        with Dataset(self.child,"a") as f:
            f.createVariable("angle","f8",("eta_rho","xi_rho"))[:]=0.
        with Dataset(self.parent,"a") as f:
            f["angle"][:]=0
        self.rho,self.faces=maps_from_synthetic_grid(self.child)
        self.params={"hc":50.,"theta_s":5.,"theta_b":1.,
                     "Vtransform":2,"Vstretching":4}

    def run_preview(self,times=(0,1800,3600)):
        return prepare_boundary_preview(
            self.parent,self.history,self.child,self.rho,self.faces,
            np.array(times,dtype=float),child_n=4,child_params=self.params)

    def test_full_four_side_constant_remap_and_barotropic_closure(self):
        arrays,report=self.run_preview()
        self.assertEqual(report["source_vertical_N"],3)
        self.assertEqual(report["target_vertical_N"],4)
        self.assertEqual(report["time_count"],3)
        self.assertEqual(report["real_roms_bry_nc"],"NOT_RUN")
        with Dataset(self.child) as child:
            for side in ("south","north","west","east"):
                for key in ("zeta","temp","salt","u","v","ubar","vbar"):
                    self.assertIn(key,arrays[side])
                    kind="rho" if key in ("zeta","temp","salt") else "u" if key in ("u","ubar") else "v"
                    mask=child["mask_"+kind][:]
                    edge=mask[0] if side=="south" else mask[-1] if side=="north" else mask[:,0] if side=="west" else mask[:,-1]
                    if edge.any():
                        expected={"zeta":.2,"temp":18.,"salt":34.,
                                  "u":.15,"v":-.05,"ubar":.15,"vbar":-.05}[key]
                        np.testing.assert_allclose(arrays[side][key][...,edge],
                                                   expected,atol=1e-12)
        self.assertEqual(set(report["wet_receivers_by_native_kind"]),
                         {"rho","u","v"})

    def test_parent_source_history_linear_time_interpolation(self):
        with Dataset(self.history,"a") as f:
            f["temp"][1]=20.
            f["u"][1]=.25
            f["v"][1]=-.15
            f["ubar"][1]=.25
            f["vbar"][1]=-.15
        prepared,_=self.run_preview()
        self.assertAlmostEqual(prepared["south"]["temp"][1,2,2],19,places=12)
        self.assertAlmostEqual(prepared["south"]["u"][1,2,2],.2,places=12)
        self.assertAlmostEqual(prepared["north"]["v"][1,2,2],-.10,places=12)
        self.assertAlmostEqual(prepared["east"]["ubar"][1,3],.2,places=12)

    def test_parent_angle_to_geographic_to_child_face(self):
        with Dataset(self.parent,"a") as f:
            f["angle"][:]=np.pi/2
        prepared,_=self.run_preview()
        # Parent U=.15 V=-.05, 90-degree grid -> East=.05 North=.15.
        self.assertAlmostEqual(prepared["south"]["u"][0,1,2],.05,places=12)
        self.assertAlmostEqual(prepared["south"]["v"][0,1,2],.15,places=12)

    def test_child_angle_rotates_velocity_into_face_axes(self):
        with Dataset(self.child,"a") as f:
            f["angle"][:]=np.pi/2
        prepared,_=self.run_preview()
        # Same geographic East=.15 North=-.05, child +90 => u=-.05,v=-.15.
        self.assertAlmostEqual(prepared["south"]["u"][0,1,2],-.05,places=12)
        self.assertAlmostEqual(prepared["south"]["v"][0,1,2],-.15,places=12)

    def test_missing_wet_boundary_receiver_fails_closed(self):
        self.faces["v"]["records"].pop()
        with self.assertRaisesRegex(ValueError,"incomplete native v wet perimeter"):
            self.run_preview()

    def test_invalid_GSHHG_status_rejected(self):
        self.rho["records"][0]["coastline_visible"]=False
        with self.assertRaisesRegex(ValueError,"uncertified GSHHG"):
            self.run_preview()

    def test_dry_parent_donor_rejected(self):
        self.rho["records"][0]["donor_eta_xi_zero_based"]=[[0,0]]
        self.rho["records"][0]["weights"]=[1]
        with self.assertRaisesRegex(ValueError,"dry/outside parent"):
            self.run_preview()

    def test_missing_native_UV_support_rejected(self):
        self.faces["u"]["records"][0]["native_parent_U_and_V_wet_face_support"]=False
        with self.assertRaisesRegex(ValueError,"lacks certified"):
            self.run_preview()

    def test_temporal_out_of_parent_range_rejected(self):
        with self.assertRaisesRegex(ValueError,"outside parent history coverage"):
            self.run_preview((-60.,0.,3600.))

    def test_nonmonotone_child_time_rejected(self):
        with self.assertRaisesRegex(ValueError,"strictly increasing"):
            self.run_preview((0.,0.))

    def test_requires_explicit_child_vertical_metadata(self):
        self.params.pop("Vstretching")
        with self.assertRaisesRegex(ValueError,"explicit child ROMS"):
            self.run_preview()

    def test_physical_z_rejects_dry_column(self):
        with self.assertRaisesRegex(ValueError,"nonpositive wet"):
            physical_z(100.,-200.,3,self.params)


if __name__=="__main__":
    unittest.main()
