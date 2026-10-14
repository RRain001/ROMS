"""Unit tests for a reversible ES3K sea-only candidate, synthetic mask."""
from __future__ import annotations
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from netCDF4 import Dataset

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"nesting"))
from es3k_core_component_filter import core_component_only_candidate


def make_grid(path):
    lon,lat=np.meshgrid(np.linspace(121,151,121),np.linspace(30,53,93))
    water=np.ones(lon.shape,dtype=np.int8)
    # Intentionally separate the west-Korea sea from Japan Sea
    # across a full-height dry stripe; no existing wet-wet face.
    water[:,(lon[0]>=126.5)&(lon[0]<=127.0)]=0
    with Dataset(path,"w") as f:
        ny,nx=lon.shape
        for d,n in (("eta_rho",ny),("xi_rho",nx),("eta_u",ny),("xi_u",nx-1),
                    ("eta_v",ny-1),("xi_v",nx),("eta_psi",ny-1),("xi_psi",nx-1)):
            f.createDimension(d,n)
        f.grid_id="ES3K"
        f.geometry_status="CANDIDATE_NOT_VALIDATED_FOR_ROMS"
        f.synthetic_test_only="TRUE"
        f.shoreline_status="SYNTHETIC"
        for name,data in (
            ("lon_rho",lon),("lat_rho",lat),
            ("mask_rho",water),("h",50+np.abs(lon-130)*200),
            ("pm",np.full(lon.shape,1/3000)),
            ("pn",np.full(lon.shape,1/3000)),
            ("angle",np.zeros(lon.shape))):
            f.createVariable(name,"i1" if name=="mask_rho" else "f8",
                             ("eta_rho","xi_rho"))[:]=data
        for name,dims,mask in (
            ("mask_u",("eta_u","xi_u"),water[:,:-1]&water[:,1:]),
            ("mask_v",("eta_v","xi_v"),water[:-1,:]&water[1:,:]),
            ("mask_psi",("eta_psi","xi_psi"),
             water[:-1,:-1]&water[:-1,1:]&water[1:,:-1]&water[1:,1:])):
            f.createVariable(name,"i1",dims)[:]=mask


class CoreOnlyCandidate(unittest.TestCase):
    def test_filter_removes_only_disconnected_components_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            before=root/"source.nc"
            after=root/"core_only.nc"
            report_file=root/"filter.json"
            make_grid(before)
            digest=hashlib.sha256(before.read_bytes()).hexdigest()
            report=core_component_only_candidate(before,after,report_file)
            self.assertTrue(report_file.is_file())
            self.assertGreater(report["excluded_noncore_wet_rho_points"],0)
            self.assertEqual(report["derived_yellow_sea_proxy_wet_rho"],0)
            self.assertTrue(all(report["straits_after_filter"].values()))
            self.assertEqual(report["number_of_original_four_neighbor_components"],2)
            self.assertTrue(report["no_existing_shared_wet_face_cut"])
            self.assertEqual(hashlib.sha256(before.read_bytes()).hexdigest(),digest)
            with Dataset(before) as origin,Dataset(after) as candidate:
                for name in ("lon_rho","lat_rho","pm","pn","angle","h"):
                    np.testing.assert_array_equal(origin[name][:],candidate[name][:])
                old=np.asarray(origin["mask_rho"][:],dtype=bool)
                new=np.asarray(candidate["mask_rho"][:],dtype=bool)
                removed=np.asarray(candidate["excluded_ocean_component_rho"][:],dtype=bool)
                np.testing.assert_array_equal(new|removed,old)
                self.assertFalse(np.any(new & removed))
                self.assertEqual(int(removed.sum()),report["excluded_noncore_wet_rho_points"])
                self.assertIn("NOT_APPROVED_FOR_ROMS",candidate.mask_science_status)
            with self.assertRaisesRegex(FileExistsError,"exists"):
                core_component_only_candidate(before,after,report_file)
            with self.assertRaisesRegex(ValueError,"overwrite"):
                core_component_only_candidate(before,before,report_file)


if __name__=="__main__":
    unittest.main()
