"""I3 candidate grid real-bathymetry integration; not an official ES3K grid."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from netCDF4 import Dataset
import shapefile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"nesting"))
from bathymetry_grid import build_grid, make_geometry, NESTING_ONLY


def make_fixture(path: Path) -> None:
    """Rectilinear synthetic GEBCO: sloping water plus a positive-elevation island."""
    lon=np.linspace(130.65,131.95,90)
    lat=np.linspace(37.05,38.2,75)
    lo,la=np.meshgrid(lon,lat)
    elev=-(30+150*(la-lat.min())+10*(lo-lon.min()))
    elev[(lo>131.36) & (la>37.55)]=-12+65*(lo[(lo>131.36) & (la>37.55)]-131.36)+50
    with Dataset(path,"w") as ds:
        ds.createDimension("lon",len(lon))
        ds.createDimension("lat",len(lat))
        ds.createVariable("lon","f8",("lon",))[:]=lon
        ds.createVariable("lat","f8",("lat",))[:]=lat
        ds.createVariable("elevation","f8",("lat","lon"))[:]=elev


ES={
    "grid_id":"ES3K","geometry_status":"CANDIDATE_APPROXIMATE",
    "geometry_type":"rotated_lcc","center_lon":131.32,"center_lat":37.63,
    "width_points":15,"height_points":13,"dx_m":3000,"dy_m":3000,"angle_deg":20
}
UD={
    "grid_id":"UD1K","geometry_status":"CANDIDATE_APPROXIMATE",
    "geometry_type":"axis_aligned_lonlat",
    "lon_min":131.10,"lon_max":131.42,"lat_min":37.46,"lat_max":37.73,
    "resolution_m":1600
}


class BathyGridTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        self.source=self.folder/"synthetic_bathy.nc"
        make_fixture(self.source)

    def build(self,spec,name,**kwargs):
        output=self.folder/name
        result=build_grid(spec,self.source,output,allow_gebco_only_mask=True,
                          synthetic_fixture=True,**kwargs)
        return output,result

    def test_rotated_actual_bathymetry_not_flat(self):
        path,rep=self.build(ES,"rotated.nc")
        self.assertEqual(rep["status"],NESTING_ONLY)
        self.assertEqual(rep["rho_shape"],[13,15])
        self.assertGreater(rep["wet_fraction"],0)
        self.assertLess(rep["wet_fraction"],1)
        self.assertLess(rep["quality"]["orthogonality_error_max_deg"],0.08)
        with Dataset(path) as ds:
            self.assertEqual(ds.geometry_status,NESTING_ONLY)
            self.assertEqual(ds.shoreline_status,"GEBCO_ONLY_SHORELINE_NOT_VALIDATED")
            self.assertEqual(ds.synthetic_test_only,"TRUE")
            self.assertEqual(ds["lon_u"].shape,(13,14))
            self.assertEqual(ds["lon_v"].shape,(12,15))
            self.assertEqual(ds["lon_psi"].shape,(12,14))
            self.assertEqual(ds["pm"].shape,(13,15))
            self.assertGreater(float(np.ptp(ds["h"][:])),20)
            self.assertAlmostEqual(np.rad2deg(ds["angle"][6,7]),20,delta=.25)
            mask=np.asarray(ds["mask_rho"][:])
            np.testing.assert_array_equal(ds["mask_u"][:],mask[:,:-1]*mask[:,1:])
            np.testing.assert_array_equal(ds["mask_v"][:],mask[:-1,:]*mask[1:,:])
            self.assertGreater(np.abs(ds["lon_u"][4,4]-
                        (ds["lon_rho"][4,4]+ds["lon_rho"][4,5])/2),0) # sanity that C-grid has true coordinates

    def test_unrotated_ud1k_stays_axis_aligned(self):
        path,rep=self.build(UD,"ud.nc")
        self.assertLess(rep["quality"]["orthogonality_error_max_deg"],0.06)
        with Dataset(path) as ds:
            np.testing.assert_allclose(ds["angle"][:],0,atol=1e-14)
            a=np.asarray(ds["lon_rho"][:])
            b=np.asarray(ds["lat_rho"][:])
            np.testing.assert_allclose(a,np.broadcast_to(a[0:1,:],a.shape),atol=1e-13)
            np.testing.assert_allclose(b,np.broadcast_to(b[:,0:1],b.shape),atol=1e-13)
            self.assertAlmostEqual(float(a.min()),UD["lon_min"],places=10)
            self.assertAlmostEqual(float(a.max()),UD["lon_max"],places=10)

    def test_gshhg_masks_intersect_bathymetry_water(self):
        candidate,_,_=make_geometry(ES)
        forced=np.zeros(candidate["lon_rho"].shape,dtype=bool)
        forced[0,0]=True
        with patch("bathymetry_grid._read_gshhg_land",return_value=(forced,"synthetic-gshhg.shp")):
            path,rep= self.build(ES,"mask.nc",gshhg_base=self.folder)
        self.assertEqual(rep["shoreline_status"],"GSHHG_L1_INTERSECTED_WITH_GEBCO")
        with Dataset(path) as ds:
            self.assertEqual(ds["mask_rho"][0,0],0)
            self.assertEqual(ds.shoreline_source,"synthetic-gshhg.shp")

    def test_real_gshhg_shapefile_parser_masks_wet_grid(self):
        # This exercises the actual independent GSHHG shapefile loader,
        # unlike the above mocked test. Synthetic polygon, not Japan Sea.
        coords, _, _ = make_geometry(ES)
        lo = float(coords["lon_rho"][6, 5])
        la = float(coords["lat_rho"][6, 5])
        base=self.folder/"gshhg-shp-2"/"GSHHS_shp"
        folder=base/"h"
        folder.mkdir(parents=True)
        shp_path=folder/"GSHHS_h_L1.shp"
        with shapefile.Writer(str(shp_path),shapeType=shapefile.POLYGON) as sh:
            sh.field("ID","N")
            sh.poly([[[lo-.018,la-.018],[lo+.018,la-.018],
                      [lo+.018,la+.018],[lo-.018,la+.018],
                      [lo-.018,la-.018]]])
            sh.record(1)
        unmasked,_=self.build(ES,"unmasked.nc")
        masked=self.folder/"gshhg_masked.nc"
        report=build_grid(ES,self.source,masked,gshhg_base=base,
                          gshhg_resolution="h",synthetic_fixture=True)
        self.assertEqual(report["shoreline_status"],"GSHHG_L1_INTERSECTED_WITH_GEBCO")
        with Dataset(unmasked) as old,Dataset(masked) as updated:
            self.assertEqual(old["mask_rho"][6,5],1)
            self.assertEqual(updated["mask_rho"][6,5],0)
            self.assertEqual(updated["mask_u"][6,5],0)
            self.assertIn("GSHHS_h_L1.shp",updated.shoreline_source)

    def test_integer_gebco_elevation(self):
        # GEBCO elevation is often stored as signed integer NetCDF.
        integer_path=self.folder/"gebco_int16.nc"
        with Dataset(self.source) as original,Dataset(integer_path,"w") as target:
            for name in ("lon","lat"):
                target.createDimension(name,len(original.dimensions[name]))
                var=target.createVariable(name,"f8",(name,))
                var[:]=original[name][:]
            elev=target.createVariable("elevation","i2",("lat","lon"),fill_value=-32768)
            elev[:]=np.rint(original["elevation"][:]).astype("i2")
        output=self.folder/"int16_grid.nc"
        report=build_grid(ES,integer_path,output,
                          allow_gebco_only_mask=True,synthetic_fixture=True)
        self.assertEqual(report["status"],NESTING_ONLY)
        with Dataset(output) as grid:
            self.assertTrue(np.isfinite(grid["h"][:]).all())
            self.assertGreater(float(np.ptp(grid["h"][:])),20)

    def test_mask_required_unless_explicit_test_policy(self):
        with self.assertRaisesRegex(ValueError,"--gshhg-base"):
            build_grid(ES,self.source,self.folder/"bad.nc")

    def test_reject_missing_geometry_and_wrong_science_status(self):
        broken={**ES,"angle_deg":None}
        with self.assertRaisesRegex(ValueError,"explicitly"):
            self.build(broken,"invalid.nc")
        with self.assertRaisesRegex(ValueError,"CANDIDATE_APPROXIMATE"):
            self.build({**ES,"geometry_status":"VERIFIED"}, "unapproved.nc")

    def test_reject_out_of_range_source_bathymetry(self):
        with self.assertRaisesRegex(ValueError,"increase geographic margin"):
            self.build({**ES,"center_lon":135},"uncovered.nc")

    def test_cli_end_to_end(self):
        spec=self.folder/"candidate.json"
        spec.write_text(json.dumps(ES))
        path=self.folder/"cli_grid.nc"
        script=ROOT/"scripts/nesting/create_bathymetry_grid.py"
        cmd=[sys.executable,str(script),
             "--geometry-json",str(spec),"--bathymetry",str(self.source),
             "--output",str(path),"--allow-gebco-only-mask","--synthetic-test-only"]
        proc=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"],NESTING_ONLY)
        self.assertTrue(path.exists())


if __name__=="__main__":
    unittest.main()
