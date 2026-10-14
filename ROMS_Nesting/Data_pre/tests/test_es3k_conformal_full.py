"""Full-resolution ES3K conformal geometry and ES3K→UD1K test.

This is synthetic all-wet bathymetry. The gate proves source-code
compatibility and geometry only, NEVER actual Japanese Sea topology,
model stability, or an exact 1/36-degree rotated angular grid.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from netCDF4 import Dataset

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"nesting"),str(ROOT/"core")]
from es3k_conformal import conformal_corner_grid
from bathymetry_grid import build_grid
from validate_nesting_geometries import check_pair

ES3K=ROOT.parent/"configs/es3k_conformal_candidate.json"
UD1K=ROOT.parent/"configs/ud1k_candidate.json"


class FullResolutionConformal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.es=json.loads(ES3K.read_text())
        cls.ud=json.loads(UD1K.read_text())
        cls.geo,_,_,cls.report=conformal_corner_grid(cls.es,sample_scale=1)

    def test_full_resolution_geometry_metrics(self):
        q=self.report
        self.assertEqual(q["sample_scale"],1)
        self.assertEqual(q["actual_rho_shape"],q["full_estimated_rho_shape"])
        self.assertGreater(q["actual_rho_shape"][0],400)
        self.assertGreater(q["actual_rho_shape"][1],300)
        self.assertLess(q["corner_max_wgs84_error_m"],1e-5)
        self.assertLess(q["orthogonality_error_max_deg"],1.0)
        self.assertGreater(q["jacobian_min_projected_m2"],0)
        self.assertEqual(q["orthogonality_gate"],"PRELIMINARY_PASS_ONLY")
        self.assertEqual(q["sampling_interpretation"],
                         "LOCAL_METRIC_EQUIVALENT_NOT_EXACT_ANGULAR")
        self.assertEqual(q["GEBCO_GSHHG"],"NOT_RUN")
        self.assertEqual(q["ROMS_integration"],"NOT_RUN")
        for name in ("angle","pm","pn","dndx","dmde"):
            values=self.geo[name]
            self.assertTrue(np.isfinite(values).all())
            self.assertEqual(values.shape,tuple(q["actual_rho_shape"]))

    def test_full_resolution_real_cgrid_file_synthetic_parent_child(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/"synthetic_all_wet_not_real_gebco.nc"
            # Broad, small, strictly monotonically indexed source.
            lon=np.linspace(120.0,152.0,180)
            lat=np.linspace(29.0,53.0,150)
            with Dataset(source,"w",format="NETCDF4") as f:
                f.createDimension("lon",lon.size)
                f.createDimension("lat",lat.size)
                f.createVariable("lon","f8",("lon",))[:]=lon
                f.createVariable("lat","f8",("lat",))[:]=lat
                xx,yy=np.meshgrid(lon,lat)
                f.createVariable("elevation","f8",("lat","lon"))[:]=(
                    -140.0-0.3*(xx-120)-0.1*(yy-29))
            pfile=root/"ES3K_FULL_SYNTHETIC_ONLY.nc"
            cfile=root/"UD1K_USER_SYNTHETIC_ONLY.nc"
            pres=build_grid(self.es,source,pfile,
                            allow_gebco_only_mask=True,synthetic_fixture=True)
            cres=build_grid(self.ud,source,cfile,
                            allow_gebco_only_mask=True,synthetic_fixture=True)
            self.assertEqual(pres["status"],"CANDIDATE_NOT_VALIDATED_FOR_ROMS")
            self.assertEqual(cres["status"],"CANDIDATE_NOT_VALIDATED_FOR_ROMS")
            with Dataset(pfile) as parent,Dataset(cfile) as child:
                self.assertEqual(parent["lon_rho"].shape,
                                 tuple(self.report["actual_rho_shape"]))
                self.assertEqual(child["lon_rho"].shape,(290,438))
                self.assertEqual(parent.geometry_status,"CANDIDATE_NOT_VALIDATED_FOR_ROMS")
                self.assertEqual(parent.synthetic_test_only,"TRUE")
                self.assertEqual(parent.angular_spacing_claim,
                                 "LOCAL_WGS84_METRIC_EQUIVALENT_NOT_EXACT_ANGULAR")
                self.assertGreater(int(np.sum(parent["mask_rho"][:])),300000)
                self.assertLess(
                    abs(float(parent["lon_rho"][0,0])-121.9),1e-9)
                self.assertTrue(np.isfinite(parent["angle"][:]).all())
            pair=check_pair(pfile,cfile,margin_parent_rho_cells=2)
            self.assertEqual(pair["status"],"PASS_PRELIMINARY_ONLY")
            self.assertEqual(pair["parent_grid_id"],"ES3K")
            self.assertEqual(pair["child_grid_id"],"UD1K")
            self.assertGreater(pair["buffered_parent_boundary_gap_min_m"],50000)
            self.assertEqual(pair["conservative_boundary_fluxes"],"NOT_RUN")
            self.assertEqual(pair["parent_synthetic"],"TRUE")
            self.assertEqual(pair["child_synthetic"],"TRUE")


if __name__=="__main__":
    unittest.main()
