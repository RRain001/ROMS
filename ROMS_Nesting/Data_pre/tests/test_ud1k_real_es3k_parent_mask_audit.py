"""Fail-closed test inputs for a later REAL archived ES3K mask donor audit."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from netCDF4 import Dataset

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_real_es3k_parent_mask_audit import check_real_parent_donors


class ActualMaskContractSyntheticFixture(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.path=Path(t.name)
        self.parent=self.path/"TEST_ONLY_4x5_parent.nc"
        self.rho=self.path/"RHO.json"
        self.uv=self.path/"UV.json"
        self.child=self.path/"not_needed_child_mocked_static_contract.nc"
        self.wet=np.ones((4,5),dtype=bool)
        self._write_grid()
        self._make_rows()

    def _write_grid(self):
        with Dataset(self.parent,"w") as f:
            for name,size in (("eta_rho",4),("xi_rho",5),("eta_u",4),
                              ("xi_u",4),("eta_v",3),("xi_v",5)):
                f.createDimension(name,size)
            rho=self.wet.astype("i1")
            data={"mask_rho":(rho,("eta_rho","xi_rho")),
                  "mask_u":((self.wet[:,:-1]&self.wet[:,1:]).astype("i1"),("eta_u","xi_u")),
                  "mask_v":((self.wet[:-1,:]&self.wet[1:,:]).astype("i1"),("eta_v","xi_v"))}
            for name,(v,dims) in data.items():
                f.createVariable(name,"i1",dims)[:]=v
            for name,value in (("h",120.),("angle",0.1),
                               ("lon_rho",131.),("lat_rho",36.)):
                f.createVariable(name,"f8",("eta_rho","xi_rho"))[:]=value

    def _make_rows(self):
        self.rho.write_text(json.dumps({"records":[
            {"donor_eta_xi_zero_based":[[1,2]],"weights":[1.]}
        ]}))
        self.uv.write_text(json.dumps({"reports":{
            "u":{"records":[{"donor_parent_rho_eta_xi_zero_based":[[1,2]],"weights":[1.]}]},
            "v":{"records":[{"donor_parent_rho_eta_xi_zero_based":[[1,2]],"weights":[1.]}]}
        }}))

    def run_audit(self):
        with patch("ud1k_real_es3k_parent_mask_audit.validate_real_candidate_b",
                   return_value={"option_b_status":"COMPARISON_CANDIDATE_NOT_ACTIVE",
                                 "wet_native_open_normal_section_counts":{
                                  "south":382,"north":364,"west":0,"east":266}}),patch.dict(
                   "ud1k_real_es3k_parent_mask_audit.EXPECTED_COUNTS",
                   {"rho":1,"u":1,"v":1}):
            return check_real_parent_donors(self.parent,self.child,self.rho,self.uv,
                                            expected_parent_shape=(4,5))

    def test_real_parent_mask_interface_reports_each_source_donor_and_support(self):
        r=self.run_audit()
        self.assertEqual(r["status"],"REAL_ES3K_PARENT_MASK_ALL_OPTIONB_RHO_U_V_DONORS_PASS")
        self.assertEqual(r["unique_real_parent_RHO_donor_nodes"],1)
        self.assertEqual(r["actual_RHO_and_native_UV_donor_checks"],"PASS")
        self.assertEqual(r["real_parent_ES3K_time_dependent_history"],"NOT_AVAILABLE")
        self.assertEqual(r["receivers_by_kind"],{"rho":1,"u":1,"v":1})

    def test_real_parent_rho_dry_is_rejected_despite_manifests(self):
        self.wet[1,2]=False
        self.parent.unlink();self._write_grid()
        with self.assertRaisesRegex(ValueError,"DRY RHO donor"):
            self.run_audit()

    def test_real_parent_has_no_wet_u_neighborhood(self):
        self.wet[1,1]=False
        self.wet[1,3]=False
        self.parent.unlink();self._write_grid()
        with self.assertRaisesRegex(ValueError,"lacks wet U AND V faces"):
            self.run_audit()

    def test_real_parent_has_no_wet_v_neighborhood(self):
        self.wet[0,2]=False
        self.wet[2,2]=False
        self.parent.unlink();self._write_grid()
        with self.assertRaisesRegex(ValueError,"lacks wet U AND V faces"):
            self.run_audit()

    def test_corrupted_true_native_u_mask_rejected(self):
        with Dataset(self.parent,"a") as f:
            f["mask_u"][1,2]=0.
        with self.assertRaisesRegex(ValueError,"native U mask inconsistent"):
            self.run_audit()

    def test_real_parent_depth_must_be_positive(self):
        with Dataset(self.parent,"a") as f:
            f["h"][1,2]=-1.
        with self.assertRaisesRegex(ValueError,"wet h not positive"):
            self.run_audit()

    def test_nonbinary_native_v_mask_rejected(self):
        with Dataset(self.parent,"a") as f:
            f["mask_v"][1,2]=2.
        with self.assertRaisesRegex(ValueError,"nonbinary wet flags"):
            self.run_audit()

    def test_zero_weight_listed_rho_donor_is_still_checked(self):
        data=json.loads(self.rho.read_text())
        data["records"][0]["donor_eta_xi_zero_based"]=[[1,2],[1,4]]
        data["records"][0]["weights"]=[1.,0.]
        self.rho.write_text(json.dumps(data))
        self.wet[1,4]=False
        self.parent.unlink();self._write_grid()
        with self.assertRaisesRegex(ValueError,"DRY RHO donor"):
            self.run_audit()


if __name__=="__main__":
    unittest.main()
