"""Nonconstant vertical shear, sea-level change, vector rotation, flux checks.

All data are intentionally tiny SYNTHETIC ROMS history fixtures; tests do
not infer real hydrodynamic source boundary conservation.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import unittest

import numpy as np
from netCDF4 import Dataset

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_boundary_remap_preview import physical_z,prepare_boundary_preview
from ud1k_boundary_normal_flux_preview import (
    wet_face_width_m,add_native_normal_face,new_flux_audit,finalize_flux_audit)
from test_ud1k_parent_history_contract import synthetic_parent_grid,synthetic_parent_history
from test_ud1k_bry_schema_contract import child_grid
from test_ud1k_boundary_remap_preview import maps_from_synthetic_grid


class NonconstantSourceToChildFlux(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.parent=Path(t.name)/"SYNTHETIC_ES3K_grid.nc"
        self.history=Path(t.name)/"SYNTHETIC_ES3K_history.nc"
        self.child=Path(t.name)/"SYNTHETIC_UD1K_grid.nc"
        synthetic_parent_grid(self.parent)
        synthetic_parent_history(self.history,n=3)
        child_grid(self.child)
        self.params={"hc":50.,"theta_s":5.,"theta_b":1.,
                     "Vtransform":2,"Vstretching":4}
        with Dataset(self.parent,"a") as g:
            g["h"][:]=125.
            jj,ii=np.indices((4,5))
            g["angle"][:]=.06*(ii-2)
        with Dataset(self.child,"a") as g:
            g["h"][:]=125.
            j,i=np.indices((6,7))
            g.createVariable("angle","f8",("eta_rho","xi_rho"))[:]=.12+.02*i+.03*j
            g.createVariable("pm","f8",("eta_rho","xi_rho"))[:]=1/3300.
            g.createVariable("pn","f8",("eta_rho","xi_rho"))[:]=1/3100.
        self.rho,self.faces=maps_from_synthetic_grid(self.child)
        self._write_shear_history()

    @staticmethod
    def _raw_u(z,sec):
        return .23+.002*z+1e-5*sec

    @staticmethod
    def _raw_v(z,sec):
        return -.05-.001*z+2e-5*sec

    def _write_shear_history(self):
        with Dataset(self.history,"a") as h:
            for t,(sec,surface) in enumerate(((0.,.4),(3600.,1.6))):
                h["zeta"][t,:,:]=surface
                z=physical_z(125.,surface,3,self.params)
                zw=physical_z(125.,surface,3,self.params,at="w")
                Hz=np.diff(zw)
                h["temp"][t,:,:,:]=(16+.013*z+1e-4*sec)[:,None,None]
                h["salt"][t,:,:,:]=(34-.003*z+3e-5*sec)[:,None,None]
                hu=self._raw_u(z,sec)
                hv=self._raw_v(z,sec)
                h["u"][t,:,:,:]=hu[:,None,None]
                h["v"][t,:,:,:]=hv[:,None,None]
                h["ubar"][t,:,:]=float(np.dot(hu,Hz)/(125+surface))
                h["vbar"][t,:,:]=float(np.dot(hv,Hz)/(125+surface))

    def preview(self):
        return prepare_boundary_preview(self.parent,self.history,self.child,
                                        self.rho,self.faces,
                                        np.array([0.,1800.,3600.]),child_n=4,
                                        child_params=self.params)

    def test_time_varying_eta_shear_temperature_and_salinity_from_analytic_z(self):
        fields,report=self.preview()
        # At same depths, source sigma profiles are affine in both z and time.
        # Therefore interpolation of the source midpoint in sigma space
        # must reproduce the affine depth profile, except at endpoints
        # where the source's physical profile explicitly clamps.
        for tidx,(seconds,surface) in enumerate(((0.,.4),(1800.,1.0),(3600.,1.6))):
            z_parent=physical_z(125.,surface,3,self.params)
            z_child=physical_z(125.,surface,4,self.params)
            clipped=np.clip(z_child,z_parent[0],z_parent[-1])
            index=3
            np.testing.assert_allclose(
                fields["south"]["temp"][tidx,:,index],
                16+.013*clipped+1e-4*seconds,atol=2e-12)
            np.testing.assert_allclose(
                fields["south"]["salt"][tidx,:,index],
                34-.003*clipped+3e-5*seconds,atol=2e-12)
            np.testing.assert_allclose(fields["south"]["zeta"][tidx,index],
                                       surface,atol=1e-12)
        self.assertGreater(np.ptp(fields["south"]["temp"][1,:,3]),.2)
        self.assertGreater(np.ptp(fields["south"]["u"][1,:,3]),.03)
        self.assertGreater(report["physical_z_profile_endpoint_clamps"]["clamped_below"],0)
        self.assertGreater(report["physical_z_profile_endpoint_clamps"]["clamped_above"],0)

    def test_spatial_parent_angle_weighting_and_child_uv_rotation_independent_oracle(self):
        fields,_=self.preview()
        j,i=0,3
        with Dataset(self.parent) as pg,Dataset(self.child) as cg:
            angles=[float(pg["angle"][1,2]),float(pg["angle"][1,3])]
            child_u_angle=.5*(cg["angle"][j,i]+cg["angle"][j,i+1])
            child_v_angle=.5*(cg["angle"][j,i]+cg["angle"][j+1,i])
        sec,surface=1800.,1.0
        z_p=physical_z(125.,surface,3,self.params)
        z_c=physical_z(125.,surface,4,self.params)
        z=np.clip(z_c,z_p[0],z_p[-1])
        u=self._raw_u(z,sec);v=self._raw_v(z,sec)
        east=sum(.5*(u*np.cos(a)-v*np.sin(a)) for a in angles)
        north=sum(.5*(u*np.sin(a)+v*np.cos(a)) for a in angles)
        expected_u=east*np.cos(child_u_angle)+north*np.sin(child_u_angle)
        expected_v=-east*np.sin(child_v_angle)+north*np.cos(child_v_angle)
        np.testing.assert_allclose(fields["south"]["u"][1,:,i],
                                   expected_u,rtol=0,atol=2e-12)
        np.testing.assert_allclose(fields["south"]["v"][1,:,i],
                                   expected_v,rtol=0,atol=2e-12)
        zw=physical_z(125.,surface,4,self.params,at="w")
        hz=np.diff(zw)
        self.assertAlmostEqual(fields["south"]["ubar"][1,i],
                               float(np.dot(expected_u,hz)/(125+surface)),places=12)
        self.assertAlmostEqual(fields["south"]["vbar"][1,i],
                               float(np.dot(expected_v,hz)/(125+surface)),places=12)

    def test_each_native_normal_section_has_3d_and_2d_flux_agreement(self):
        fields,report=self.preview()
        audit=report["native_normal_section_flux_diagnostic"]
        self.assertEqual(audit["normal_face_2d_vs_3d_integration_check"],"PASS")
        self.assertEqual(audit["parent_to_child_mass_conservation"],"NOT_RUN")
        self.assertEqual(audit["free_surface_storage_and_tidal_budget"],"NOT_RUN")
        self.assertLessEqual(audit["max_section_2d_vs_3d_relative_mismatch"],1e-10)
        sections=audit["normal_sections"]
        for side in ("south","north","east"):
            self.assertEqual([x["wet_native_normal_face_count"] for x in sections[side]],
                             [6,6,6])
            self.assertTrue(all(np.isfinite(x["outward_volume_flux_3d_m3s"])
                                for x in sections[side]))
        self.assertEqual([x["wet_native_normal_face_count"] for x in sections["west"]],
                         [0,0,0])
        self.assertEqual(audit["total_wet_normal_face_samples"],54)
        self.assertGreater(abs(sections["south"][1]["outward_volume_flux_3d_m3s"]),100)
        self.assertGreater(abs(sections["north"][1]["outward_volume_flux_3d_m3s"]),100)
        # Recompute each boundary section with its OWN signed native
        # barotropic field. Different local rotations can make the two
        # oriented physical velocities have different signs; never assume
        # opposite section totals solely from outward sign convention.
        for side,sign in (("south",-1),("north",1)):
            wet_v=fields[side]["vbar"][1,1:7]
            independently_integrated=sign*3300.*126.*float(np.sum(wet_v))
            self.assertAlmostEqual(
                sections[side][1]["outward_volume_flux_2d_m3s"],
                independently_integrated,delta=1e-8*max(1.,abs(independently_integrated)))

    def test_grid_metrics_missing_or_nonpositive_are_rejected(self):
        with Dataset(self.child,"a") as g:
            g["pm"][2,3]=0.
        with self.assertRaisesRegex(ValueError,"pm/pn metrics invalid"):
            self.preview()

    def test_no_grid_metrics_is_explicitly_unverified(self):
        with Dataset(self.child,"a") as g:
            g.renameVariable("pm","unused_pm")
            g.renameVariable("pn","unused_pn")
        _,report=self.preview()
        self.assertEqual(
            report["native_normal_section_flux_diagnostic"]["status"],
            "NOT_RUN_MISSING_CHILD_PM_PN_GRID_METRICS")

    def test_detects_source_native_ubar_inconsistency_not_flux_conservation(self):
        with Dataset(self.history,"a") as h:
            h["ubar"][:]=10.
        _,report=self.preview()
        self.assertGreater(
            report["parent_native_2d_vs_3d_barotropic_mismatch_max_mps"],9.)
        self.assertEqual(report["parent_native_barotropic_mismatch_acceptance"],
                         "DIAGNOSTIC_ONLY")
        self.assertEqual(report["native_normal_section_flux_diagnostic"]
                         ["normal_face_2d_vs_3d_integration_check"],"PASS")

    def test_normal_section_rejects_tangential_component(self):
        audit=new_flux_audit(1)
        pm=np.full((4,5),1/3300.)
        pn=np.full((4,5),1/3100.)
        with self.assertRaisesRegex(ValueError,"tangential/stagger-incompatible"):
            add_native_normal_face(audit,"south",0,"u",0,2,pm,pn,
                                   np.array([-1.,0.]),np.array([.2]),.2,1.)

    def test_per_face_flux_mismatch_cannot_cancel_between_opposite_faces(self):
        audit=new_flux_audit(1)
        pm=np.full((4,5),1/3300.)
        pn=np.full((4,5),1/3100.)
        z_w=np.array([-100.,-50.,0.])
        vel=np.array([.4,.2])
        physical_bar=float(np.dot(vel,np.diff(z_w))/100)
        # Two opposite equal-area faces: summed per-section errors could
        # cancel if only totals were checked. Here each must be rejected.
        add_native_normal_face(audit,"south",0,"v",0,1,pm,pn,
                               z_w,vel,physical_bar+.1,100.)
        add_native_normal_face(audit,"south",0,"v",0,2,pm,pn,
                               z_w,vel,physical_bar-.1,100.)
        self.assertAlmostEqual(
            audit["normal_sections"]["south"][0]["outward_volume_flux_3d_m3s"],
            audit["normal_sections"]["south"][0]["outward_volume_flux_2d_m3s"])
        with self.assertRaisesRegex(ValueError,"individual face"):
            finalize_flux_audit(audit)

    def test_nonconstant_fields_save_and_reopen_28_var_synthetic_bry(self):
        from ud1k_bry_schema_contract import write_synthetic_schema_fixture
        fields,report=self.preview()
        target=self.child.parent/"SYNTHETIC_nonconstant_UD1K_bry.nc"
        expected_times=np.array([0.,1800.,3600.])
        schema=write_synthetic_schema_fixture(
            self.child,target,fields,expected_times,n=4,
            time_units="seconds since 2025-01-01 00:00:00")
        self.assertEqual(schema["status"],"SYNTHETIC_SCHEMA_TEST_ONLY")
        self.assertEqual(schema["complete_field_variables"],28)
        self.assertEqual(report["real_roms_bry_nc"],"NOT_RUN")
        with Dataset(target) as f:
            self.assertEqual(f["temp_south"].shape,(3,4,7))
            self.assertEqual(f["u_south"].shape,(3,4,6))
            self.assertEqual(f["v_south"].shape,(3,4,7))
            self.assertEqual(f["vbar_north"].shape,(3,7))
            self.assertEqual(f.getncattr("workflow_status"),
                             "SYNTHETIC_SCHEMA_TEST_ONLY_NOT_ROMS_PHYSICS")
            np.testing.assert_allclose(f["bry_time"][:],expected_times,atol=0)
            for side in ("south","north","west","east"):
                for name in ("zeta","temp","salt","u","v","ubar","vbar"):
                    np.testing.assert_allclose(f[name+"_"+side][:],
                                               fields[side][name],atol=3e-7,rtol=1e-6)
            self.assertGreater(abs(f["zeta_south"][2,3]-f["zeta_south"][0,3]),1.0)
            self.assertGreater(float(np.ptp(f["u_south"][1,:,3])),.03)

    def test_independent_face_geometry_metrics_correct(self):
        pm=np.full((4,5),1/3300.)
        pn=np.full((4,5),1/3100.)
        self.assertAlmostEqual(wet_face_width_m("u",1,2,pm,pn),3100.)
        self.assertAlmostEqual(wet_face_width_m("v",1,2,pm,pn),3300.)


if __name__=="__main__":
    unittest.main()
