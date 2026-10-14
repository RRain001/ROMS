"""I3 regression: GEBCO window-only reads for multi-GB global NetCDF inputs.

These tests use generated grids, not real GEBCO 2026 or Japan Sea science.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"nesting"))
from bathymetry_grid import _read_bathy_window, build_grid
from test_bathymetry_grid import ES,make_fixture, NESTING_ONLY,make_geometry


class BoundedBathymetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="i3_gebco_window_")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.source=self.root/"small.nc"
        make_fixture(self.source)
        self.coord,_,_=make_geometry(ES)

    def window(self, source=None, limit=50_000_000):
        return _read_bathy_window(source or self.source,
                                  self.coord["lon_rho"],
                                  self.coord["lat_rho"],
                                  max_source_cells=limit)

    def test_cropped_and_interpolation_halo(self):
        lon,lat,z,name,metadata=self.window()
        with Dataset(self.source) as ds:
            self.assertLess(z.size,ds["elevation"].size)
            self.assertLessEqual(z.shape[0],ds.dimensions["lat"].size)
            self.assertLessEqual(z.shape[1],ds.dimensions["lon"].size)
        self.assertEqual(name,"elevation")
        self.assertEqual(metadata["reader"],"NETCDF_BOUNDED_WINDOW_V1")
        self.assertEqual(metadata["window_cells"],z.size)
        self.assertLessEqual(lon[0],np.min(self.coord["lon_rho"]))
        self.assertGreaterEqual(lon[-1],np.max(self.coord["lon_rho"]))
        self.assertLessEqual(lat[0],np.min(self.coord["lat_rho"]))
        self.assertGreaterEqual(lat[-1],np.max(self.coord["lat_rho"]))
        self.assertTrue(np.isfinite(z).all())

    def test_source_flipped_both_axes_and_transposed_elevation(self):
        inverted=self.root/"inverted.nc"
        with Dataset(self.source) as orig, Dataset(inverted,"w") as nc:
            nc.createDimension("lon",len(orig.dimensions["lon"]))
            nc.createDimension("lat",len(orig.dimensions["lat"]))
            nc.createVariable("lon","f8",("lon",))[:]=orig["lon"][::-1]
            nc.createVariable("lat","f8",("lat",))[:]=orig["lat"][::-1]
            # Opposite source variable storage order and descending axes.
            nc.createVariable("elevation","f8",("lon","lat"))[:]=orig["elevation"][::-1,::-1].T
        expected=self.window()
        actual=self.window(inverted)
        for old,new in zip(expected[:3],actual[:3]):
            np.testing.assert_allclose(old,new,rtol=0,atol=0)
        self.assertTrue(actual[4]["source_longitude_descending"])
        self.assertTrue(actual[4]["source_latitude_descending"])
        out=self.root/"test_opposite.nc"
        result=build_grid(ES,inverted,out,allow_gebco_only_mask=True,synthetic_fixture=True)
        self.assertEqual(result["status"],NESTING_ONLY)
        with Dataset(out) as ds:
            self.assertIn("NETCDF_BOUNDED_WINDOW_V1",ds.bathymetry_source_window)

    def test_crop_memory_ceiling_hard_error(self):
        with self.assertRaisesRegex(ValueError,"max_source_cells"):
            self.window(limit=4)
        with self.assertRaisesRegex(ValueError,"max_source_cells"):
            build_grid(ES,self.source,self.root/"bad.nc",allow_gebco_only_mask=True,
                       max_source_cells=4,synthetic_fixture=True)
        self.assertFalse((self.root/"bad.nc").exists())

    def test_reject_insufficient_geographic_coverage(self):
        with self.assertRaisesRegex(ValueError,"increase geographic margin"):
            _read_bathy_window(self.source,self.coord["lon_rho"]+3,
                               self.coord["lat_rho"])
        self.assertFalse((self.root/"bad.nc").exists())

    def test_large_source_read_window_not_global_raster(self):
        # A 2,000x2,000 source exists on disk (~8 MB int16). A small
        # rotated ES3K candidate reads only its geographic window.
        full=self.root/"gebco_global_like.nc"
        nx=2000;ny=2000
        lon=np.linspace(129.0,133.5,nx)
        lat=np.linspace(35.5,40.0,ny)
        with Dataset(full,"w",format="NETCDF4") as nc:
            nc.createDimension("lon",nx)
            nc.createDimension("lat",ny)
            nc.createVariable("lon","f8",("lon",))[:]=lon
            nc.createVariable("lat","f8",("lat",))[:]=lat
            z=nc.createVariable("elevation","i2",("lat","lon"),zlib=True,
                                complevel=1)
            # Integer sea depths vary with latitude; source need not be
            # 4 million cells resident in the generator during reads.
            vals=-100-np.arange(ny,dtype=np.int16)[:,None]*np.ones((1,nx),dtype=np.int16)
            z[:]=vals
        ll,la,z,_,p=self.window(full,limit=300_000)
        self.assertLess(z.size,300_000)
        self.assertLess(z.size,nx*ny//10)
        self.assertTrue(np.isfinite(z).all())
        self.assertEqual(p["original_source_shape"],[ny,nx])
        self.assertGreater(z.max()-z.min(),0)
        outfile=self.root/"large_input_to_small_es3k.nc"
        report=build_grid(ES,full,outfile,allow_gebco_only_mask=True,
                          synthetic_fixture=True,max_source_cells=300_000)
        self.assertEqual(report["source_window"]["window_shape"],list(z.shape))
        self.assertTrue(outfile.is_file())

    def test_missing_elevation_values_rejected(self):
        masked=self.root/"missing.nc"
        with Dataset(self.source) as orig, Dataset(masked,"w") as nc:
            nc.createDimension("lon",len(orig.dimensions["lon"]))
            nc.createDimension("lat",len(orig.dimensions["lat"]))
            nc.createVariable("lon","f8",("lon",))[:]=orig["lon"][:]
            nc.createVariable("lat","f8",("lat",))[:]=orig["lat"][:]
            z=nc.createVariable("elevation","i2",("lat","lon"),fill_value=-32768)
            z[:]=np.rint(orig["elevation"][:]).astype(np.int16)
            z[35:45,40:51]=-32768
        with self.assertRaisesRegex(ValueError,"missing/nonfinite bathymetry"):
            build_grid(ES,masked,self.root/"bad.nc",allow_gebco_only_mask=True,
                       synthetic_fixture=True)


if __name__=="__main__":
    unittest.main()
