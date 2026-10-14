"""GEBCO_2026 official-schema staging regression, without the 7 GB download.

The generated file uses official CEDA field names and signed integer
raster. This is synthetic interface validation, NOT real bathymetry.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from zipfile import ZipFile

import numpy as np
from netCDF4 import Dataset

ROOT=Path(__file__).resolve().parents[1]
for rel in ("core","nesting","impl/preprocessing"):
    folder=str(ROOT/rel)
    if folder not in sys.path:
        sys.path.insert(0,folder)

from bathymetry_grid import build_grid,_read_bathy_window
from stage_and_subset_bathymetry import stage_global_file,subset
from test_bathymetry_grid import ES,make_geometry


def official_schema(path:Path) -> None:
    lon=np.linspace(130.5,132.1,150)
    lat=np.linspace(36.9,38.5,135)
    lon2,lat2=np.meshgrid(lon,lat)
    # Negative bathymetry, positive local island.
    z=-120-(lat2-37)*60-(lon2-131)*7
    z[(lon2>131.55)&(lat2>37.9)]=45
    with Dataset(path,"w",format="NETCDF4") as f:
        f.createDimension("longitude",lon.size)
        f.createDimension("latitude",lat.size)
        f.createVariable("longitude","f8",("longitude",))[:]=lon
        f.createVariable("latitude","f8",("latitude",))[:]=lat
        field=f.createVariable("height_above_mean_sea_level","i2",
                               ("latitude","longitude"),
                               fill_value=-32768)
        field[:]=np.rint(z).astype(np.int16)
        field.units="m"
        f.title="SYNTHETIC official GEBCO_2026 naming, not survey"


class OfficialSchemaTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.src=self.root/"GEBCO_2026_like_SYNTHETIC.nc"
        official_schema(self.src)

    def test_direct_candidate_accepts_official_elevation_name(self):
        grid=self.root/"candidate.nc"
        summary=build_grid(ES,self.src,grid,allow_gebco_only_mask=True,
                           synthetic_fixture=True)
        self.assertEqual(summary["source_window"]["data_variable"],
                         "height_above_mean_sea_level")
        with Dataset(grid) as nc:
            self.assertEqual(nc.bathymetry_variable,"height_above_mean_sea_level")
            self.assertEqual(nc.synthetic_test_only,"TRUE")
            self.assertTrue(np.isfinite(nc["h"][:]).all())

    def test_staged_bbox_can_feed_candidate(self):
        intermediate=self.root/"japan_sea_gebco_subset.nc"
        coords,_,_=make_geometry(ES)
        lon,lat=coords["lon_rho"],coords["lat_rho"]
        west,east=float(lon.min()),float(lon.max())
        south,north=float(lat.min()),float(lat.max())
        subset(self.src,intermediate,west,east,south,north,0.035,
               max_source_cells=100_000)
        with Dataset(intermediate) as nc:
            self.assertEqual(nc.original_elevation_name,
                             "height_above_mean_sea_level")
            self.assertEqual(nc["elevation"].dimensions,("lat","lon"))
            origin=json.loads(nc.source_window)
            self.assertEqual(origin["reader"],"NETCDF_BOUNDED_WINDOW_V1")
            self.assertLess(origin["window_cells"],135*150)
        result=build_grid(ES,intermediate,self.root/"from_staged.nc",
                          allow_gebco_only_mask=True,synthetic_fixture=True)
        self.assertGreater(result["wet_fraction"],0)
        self.assertEqual(result["status"],"CANDIDATE_NOT_VALIDATED_FOR_ROMS")

    def test_zip_extraction_streamed_and_verified(self):
        archive=self.root/"GEBCO_2026.zip"
        with ZipFile(archive,"w") as zipout:
            zipout.write(self.src,arcname="GEBCO_2026.nc")
        output=self.root/"extracted"/"GEBCO_2026.nc"
        got=stage_global_file(output,archive,"GEBCO_2026.nc")
        self.assertEqual(got,output)
        self.assertEqual(hashlib.sha256(got.read_bytes()).digest(),
                         hashlib.sha256(self.src.read_bytes()).digest())
        self.assertFalse(output.with_name(output.name+".part").exists())

    def test_memory_guard_applies_to_staging(self):
        coords,_,_=make_geometry(ES)
        lon,lat=coords["lon_rho"],coords["lat_rho"]
        with self.assertRaisesRegex(ValueError,"max_source_cells"):
            subset(self.src,self.root/"nope.nc",float(lon.min()),float(lon.max()),
                   float(lat.min()),float(lat.max()),0.035,
                   max_source_cells=5)
        self.assertFalse((self.root/"nope.nc").exists())

if __name__=="__main__":
    unittest.main()
