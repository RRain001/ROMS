"""Synthetic ROMS bry_unlimit CDL-complete NetCDF boundary contract tests."""
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from netCDF4 import Dataset

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_bry_schema_contract import (
    _NAMES,_SIDES,boundary_spec,validate_prepared,write_synthetic_schema_fixture)


def child_grid(path):
    with Dataset(path,"w") as f:
        sizes={"eta_rho":6,"xi_rho":7,"eta_u":6,"xi_u":6,
               "eta_v":5,"xi_v":7}
        for k,n in sizes.items():
            f.createDimension(k,n)
        wet=np.ones((6,7),dtype=np.int8)
        wet[:,0]=0
        for name,array,dims in (
            ("mask_rho",wet,("eta_rho","xi_rho")),
            ("mask_u",wet[:,:-1]&wet[:,1:],("eta_u","xi_u")),
            ("mask_v",wet[:-1,:]&wet[1:,:],("eta_v","xi_v"))):
            f.createVariable(name,"i1",dims)[:]=array
        jj,ii=np.indices(wet.shape)
        coords=[
            ("h",100+jj*10+ii,("eta_rho","xi_rho")),
            ("lon_rho",129+ii*.01,("eta_rho","xi_rho")),
            ("lat_rho",36+jj*.01,("eta_rho","xi_rho")),
            ("lon_u",129+(ii[:,:-1]+.5)*.01,("eta_u","xi_u")),
            ("lat_u",36+jj[:,:-1]*.01,("eta_u","xi_u")),
            ("lon_v",129+ii[:-1,:]*.01,("eta_v","xi_v")),
            ("lat_v",36+(jj[:-1,:]+.5)*.01,("eta_v","xi_v"))]
        for name,data,dims in coords:
            f.createVariable(name,"f8",dims)[:]=data


def input_arrays(path:Path,*,n:int=3,nt:int=2):
    out={}
    with Dataset(path) as f:
        for side in _SIDES:
            out[side]={}
            for key in _NAMES:
                _,wet=boundary_spec(f,side,key,n,nt)
                shp=(nt,n,len(wet)) if key in ("temp","salt","u","v") else (nt,len(wet))
                value={"zeta":.12,"temp":12.5,"salt":33.5,
                       "u":.15,"v":-.06,"ubar":.15,"vbar":-.06}[key]
                out[side][key]=np.full(shp,value)
    return out


class SyntheticOnlyBoundaryOutput(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.grid=Path(self.tmp.name)/"ud1k.nc"
        self.bry=Path(self.tmp.name)/"ud1k_SYNTHETIC.nc"
        child_grid(self.grid)
        self.prepared=input_arrays(self.grid)

    def make(self):
        return write_synthetic_schema_fixture(
            self.grid,self.bry,self.prepared,np.array([0.,3600.]),n=3)

    def test_complete_four_sides_28_fields_and_exact_CDL_dims(self):
        report=self.make()
        self.assertEqual(report["complete_field_variables"],28)
        self.assertEqual(report["status"],"SYNTHETIC_SCHEMA_TEST_ONLY")
        with Dataset(self.bry) as f:
            self.assertEqual(len(f.dimensions["s_rho"]),3)
            self.assertEqual(len(f.dimensions["s_w"]),4)
            self.assertEqual(len(f.dimensions["bry_time"]),2)
            self.assertEqual(f["u_south"].dimensions,
                             ("bry_time","s_rho","xi_u"))
            self.assertEqual(f["v_south"].dimensions,
                             ("bry_time","s_rho","xi_v"))
            self.assertEqual(f["zeta_east"].dimensions,
                             ("bry_time","eta_rho"))
            self.assertEqual(f["vbar_east"].dimensions,
                             ("bry_time","eta_v"))
            self.assertEqual(f["temp_north"].dimensions,
                             ("bry_time","s_rho","xi_rho"))
            self.assertEqual(f.getncattr("workflow_status"),
                             "SYNTHETIC_SCHEMA_TEST_ONLY_NOT_ROMS_PHYSICS")
            self.assertIn("Not computed from ES3K",f.getncattr("WARNING"))
            self.assertEqual(sum((field+"_"+side in f.variables)
                                  for side in _SIDES for field in _NAMES),28)

    def test_no_input_nan_on_wet_boundary_allowed(self):
        self.prepared["north"]["u"][0,0,-1]=np.nan
        with self.assertRaisesRegex(ValueError,"NaN/Inf"):
            self.make()
        self.assertFalse(self.bry.exists())

    def test_missing_component_or_side_rejected(self):
        self.prepared["south"].pop("salt")
        with self.assertRaisesRegex(ValueError,"missing complete"):
            self.make()

    def test_wrong_staggered_face_length_rejected(self):
        self.prepared["east"]["v"]=np.zeros((2,3,6))
        with self.assertRaisesRegex(ValueError,"v_east shape"):
            self.make()

    def test_repeated_or_nonmonotone_time_rejected(self):
        with Dataset(self.grid) as f:
            with self.assertRaisesRegex(ValueError,"ascending"):
                validate_prepared(f,self.prepared,np.array([0.,0.]),n=3,
                                  units="seconds since 2000-01-01 00:00:00")

    def test_overwrite_rejected(self):
        self.make()
        with self.assertRaisesRegex(ValueError,"never overwrite"):
            self.make()

    def test_grid_source_not_mutated(self):
        with Dataset(self.grid) as f:
            mask=f["mask_rho"][:].copy()
        self.make()
        with Dataset(self.grid) as f:
            np.testing.assert_array_equal(f["mask_rho"][:],mask)


if __name__=="__main__":
    unittest.main()
