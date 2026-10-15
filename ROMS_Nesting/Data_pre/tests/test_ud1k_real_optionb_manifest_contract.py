"""Offline strict static coast-safe manifest tests, tiny mocked masks only.

A separate GitHub Actions job reads the *actual* archived Option B NetCDF
and donor manifests from original native GEBCO/GSHHG I3 run; these tests
do not fabricate real shoreline certification.
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_real_optionb_manifest_contract import _admit_rows,wet_perimeter


class RejectionAndCompletenessTests(unittest.TestCase):
    def setUp(self):
        self.wet=np.ones((3,4),dtype=bool)
        self.wet[0,0]=False
        self.rows=[]
        for j,i in sorted(wet_perimeter(self.wet)):
            self.rows.append({
                "child_eta_rho_zero_based":j,
                "child_xi_rho_zero_based":i,
                "donor_eta_xi_zero_based":[[1,2],[2,2]],
                "weights":[0.25,0.75],
                "coastline_visible":True,
            })
        self.face_rows=[]
        for j,i in sorted(wet_perimeter(self.wet)):
            self.face_rows.append({
                "child_eta_face_zero_based":j,
                "child_xi_face_zero_based":i,
                "donor_parent_rho_eta_xi_zero_based":[[1,2],[2,2]],
                "weights":[0.25,0.75],
                "GSHHG_L1_coastline_clear":True,
                "native_parent_U_and_V_wet_face_support":True,
            })

    def admit(self,kind="rho",rows=None):
        with patch.dict(
            "ud1k_real_optionb_manifest_contract.EXPECTED_COUNTS",
            {kind:len(wet_perimeter(self.wet))}):
            return _admit_rows(
                self.rows if rows is None and kind=="rho" else
                self.face_rows if rows is None else rows,
                self.wet,kind,(4,5))

    def test_perimeter_matches_unique_native_wet_faces(self):
        self.assertEqual(self.admit()["verified_native_wet_receiver_count"],8)
        self.assertEqual(self.admit("v")["verified_native_wet_receiver_count"],8)

    def test_missing_wet_receiver_refused(self):
        with self.assertRaisesRegex(ValueError,"wrong donor row count"):
            self.admit(rows=self.rows[:-1])

    def test_duplicated_receiver_refused(self):
        rows=[dict(v) for v in self.rows]
        rows[-1]=dict(rows[0])
        with self.assertRaisesRegex(ValueError,"duplicate wet receiver"):
            self.admit(rows=rows)

    def test_invalid_weights_refused(self):
        rows=[dict(v) for v in self.rows]
        rows[0]["weights"]=[.2,.3]
        with self.assertRaisesRegex(ValueError,"normalized weights"):
            self.admit(rows=rows)

    def test_cross_shoreline_or_unverified_parent_wet_face_refused(self):
        rows=[dict(v) for v in self.face_rows]
        rows[0]["native_parent_U_and_V_wet_face_support"]=False
        with self.assertRaisesRegex(ValueError,"coast-visible/native-face"):
            self.admit("u",rows)
        rows[0]["native_parent_U_and_V_wet_face_support"]=True
        rows[0]["GSHHG_L1_coastline_clear"]=False
        with self.assertRaisesRegex(ValueError,"coast-visible/native-face"):
            self.admit("u",rows)

    def test_outside_actual_parent_rho_bounds_refused(self):
        rows=[dict(v) for v in self.rows]
        rows[0]["donor_eta_xi_zero_based"]=[[1,2],[4,2]]
        with self.assertRaisesRegex(ValueError,"outside parent RHO"):
            self.admit(rows=rows)

    def test_dry_receiver_refused(self):
        rows=[dict(v) for v in self.rows]
        rows[0]["child_eta_rho_zero_based"]=0
        rows[0]["child_xi_rho_zero_based"]=0
        with self.assertRaisesRegex(ValueError,"not a wet native"):
            self.admit(rows=rows)

    def test_duplicate_parent_donor_rejected(self):
        rows=[dict(v) for v in self.rows]
        rows[0]["donor_eta_xi_zero_based"]=[[1,2],[1,2]]
        with self.assertRaisesRegex(ValueError,"duplicated parent donor"):
            self.admit(rows=rows)

    def test_missing_coastline_certification_rejected(self):
        rows=[dict(v) for v in self.rows]
        rows[0]["coastline_visible"]=False
        with self.assertRaisesRegex(ValueError,"coast-visible"):
            self.admit(rows=rows)

    def test_missing_just_one_weight_rejected(self):
        rows=[dict(v) for v in self.rows]
        rows[0]["weights"]=[1.0]
        with self.assertRaisesRegex(ValueError,"normalized weights"):
            self.admit(rows=rows)

    def test_corners_are_not_double_counted(self):
        self.assertEqual(len(wet_perimeter(np.ones((3,4),dtype=bool))),10)
        self.assertEqual(len(wet_perimeter(self.wet)),9)


if __name__=="__main__":
    unittest.main()
