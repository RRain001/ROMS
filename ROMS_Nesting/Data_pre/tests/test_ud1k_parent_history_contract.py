"""End-to-end small *synthetic* ES3K ROMS history contract fixtures."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from netCDF4 import Dataset

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_parent_history_contract import validate_parent_history
from ud1k_vertical_flux_primitives import stretching4


def synthetic_parent_grid(path:Path)->None:
    with Dataset(path,"w") as d:
        for key,n in (("eta_rho",4),("xi_rho",5),("eta_u",4),
                      ("xi_u",4),("eta_v",3),("xi_v",5)):
            d.createDimension(key,n)
        wet=np.ones((4,5),dtype=np.int8)
        wet[0,0]=0
        for name,dims,array in (
            ("mask_rho",("eta_rho","xi_rho"),wet),
            ("mask_u",("eta_u","xi_u"),wet[:,:-1]&wet[:,1:]),
            ("mask_v",("eta_v","xi_v"),wet[:-1,:]&wet[1:,:])):
            v=d.createVariable(name,"i1",dims)
            v[:]=array
        jj,ii=np.indices((4,5))
        for name,values in (("h",100+jj*10+ii),("angle",ii*.05),
                            ("lon_rho",128+ii*.03),("lat_rho",35+jj*.03)):
            var=d.createVariable(name,"f8",("eta_rho","xi_rho"))
            var[:]=values


def synthetic_parent_history(path:Path,*,n:int=3)->None:
    with Dataset(path,"w") as d:
        for key,sz in (("ocean_time",None),("s_rho",n),("s_w",n+1),
                       ("eta_rho",4),("xi_rho",5),("eta_u",4),
                       ("xi_u",4),("eta_v",3),("xi_v",5)):
            d.createDimension(key,sz)
        t=d.createVariable("ocean_time","f8",("ocean_time",))
        t.units="seconds since 2025-01-01 00:00:00"
        t.calendar="gregorian"
        t[:]=[0.,3600.]
        for name,value in (("Vtransform",2),("Vstretching",4),
                           ("theta_s",5.),("theta_b",1.),
                           ("hc",50.),("Tcline",50.)):
            v=d.createVariable(name,"f8")
            v.assignValue(value)
        for location,name,curve in (
            ("rho","s_rho","s_rho"),("rho","Cs_r","Cs_r"),
            ("w","s_w","s_w"),("w","Cs_w","Cs_w")):
            s,c=stretching4(n,5.,1.,at=location)
            v=d.createVariable(name,"f8",( "s_"+location,))
            v[:]=s if curve.startswith("s_") else c
        dims={
            "zeta":("ocean_time","eta_rho","xi_rho"),
            "temp":("ocean_time","s_rho","eta_rho","xi_rho"),
            "salt":("ocean_time","s_rho","eta_rho","xi_rho"),
            "u":("ocean_time","s_rho","eta_u","xi_u"),
            "v":("ocean_time","s_rho","eta_v","xi_v"),
            "ubar":("ocean_time","eta_u","xi_u"),
            "vbar":("ocean_time","eta_v","xi_v")}
        for name,dim in dims.items():
            shape=(2,)+(n,) if "s_rho" in dim else (2,)
            shape=shape+((4,5) if dim[-2:]==("eta_rho","xi_rho") else
                         (4,4) if dim[-2:]==("eta_u","xi_u") else (3,5))
            v=d.createVariable(name,"f8",dim,fill_value=1e37)
            v[:]=np.full(shape,{"zeta":.2,"temp":18.,"salt":34.,
                                "u":.15,"v":-.05,"ubar":.15,"vbar":-.05}[name])


class StrictParentHistoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.g=Path(self.tmp.name)/"es3k_grid.nc"
        self.h=Path(self.tmp.name)/"es3k_his.nc"
        synthetic_parent_grid(self.g)
        synthetic_parent_history(self.h)

    def test_full_two_time_source_contract_pass(self):
        result=validate_parent_history(self.g,self.h)
        self.assertEqual(result["time_count"],2)
        self.assertEqual(result["n_s_rho"],3)
        self.assertTrue(result["full_wet_values_scanned"])
        self.assertEqual(set(result["wet_field_checks"]),
                         {"zeta","u","v","ubar","vbar","temp","salt"})
        self.assertEqual(result["physical_roms_bry_nc_and_hydrodynamics"],"NOT_RUN")

    def test_masked_missing_at_dry_rho_cell_is_legal(self):
        with Dataset(self.h,"a") as f:
            f["temp"][0,1,0,0]=f["temp"]._FillValue
        self.assertTrue(validate_parent_history(self.g,self.h)["full_wet_values_scanned"])

    def test_missing_wet_temperature_fails(self):
        with Dataset(self.h,"a") as f:
            f["temp"][0,1,1,1]=f["temp"]._FillValue
        with self.assertRaisesRegex(ValueError,"temp contains missing wet"):
            validate_parent_history(self.g,self.h)

    def test_nonmonotone_history_time_fails(self):
        with Dataset(self.h,"a") as f:
            f["ocean_time"][:]=[0,0]
        with self.assertRaisesRegex(ValueError,"increasing"):
            validate_parent_history(self.g,self.h)

    def test_staggered_dimension_swap_fails(self):
        with Dataset(self.h,"a") as f:
            f.createDimension("bad",4)
            f.renameVariable("u","native_u")
            wrong=f.createVariable("u","f8",("ocean_time","s_rho","eta_rho","xi_rho"))
            wrong[:]=np.ones((2,3,4,5))
        with self.assertRaisesRegex(ValueError,"history u must have exact"):
            validate_parent_history(self.g,self.h)

    def test_vertical_metadata_mismatch_fails(self):
        with Dataset(self.h,"a") as f:
            f["Vtransform"].assignValue(1)
        with self.assertRaisesRegex(ValueError,"Vtransform=2"):
            validate_parent_history(self.g,self.h)

    def test_sigma_curve_mismatch_fails(self):
        with Dataset(self.h,"a") as f:
            f["Cs_w"][-1]=-.1
        with self.assertRaisesRegex(ValueError,"Cs_w inconsistent"):
            validate_parent_history(self.g,self.h)

    def test_negative_water_column_fails(self):
        with Dataset(self.h,"a") as f:
            f["zeta"][1,1,1]=-999.
        with self.assertRaisesRegex(ValueError,"nonpositive wet water"):
            validate_parent_history(self.g,self.h)

    def test_invalid_calendar_fails(self):
        with Dataset(self.h,"a") as f:
            f["ocean_time"].calendar="not_a_calendar"
        with self.assertRaisesRegex(ValueError,"calendar"):
            validate_parent_history(self.g,self.h)

    def test_metadata_only_does_not_claim_values_scanned(self):
        r=validate_parent_history(self.g,self.h,scan_values=False)
        self.assertFalse(r["full_wet_values_scanned"])
        self.assertEqual(r["wet_field_checks"]["temp"]["wet_values"],
                         "NOT_SCANNED_METADATA_ONLY")


if __name__=="__main__":
    unittest.main()
