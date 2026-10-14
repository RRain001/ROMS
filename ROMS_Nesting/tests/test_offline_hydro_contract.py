from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"offline_tracer"))
from validate_hydro_inputs import inspect_hydrodynamics


def make_file(path:Path,*,aks:bool=True,ordered:bool=True,stagger_valid:bool=True)->None:
    with Dataset(path,"w") as ds:
        for key,size in (
            ("ocean_time",3),("xi_rho",6),("eta_rho",5),
            ("xi_u",5 if stagger_valid else 6),("eta_u",5),
            ("xi_v",6),("eta_v",4),("s_rho",2),("s_w",3)):
            ds.createDimension(key,size)
        t=ds.createVariable("ocean_time","f8",("ocean_time",))
        t.units="seconds since 2022-01-01 00:00:00"
        t[:]=[0,60,120 if ordered else 59]
        dims={
            "zeta":("ocean_time","eta_rho","xi_rho"),
            "ubar":("ocean_time","eta_u","xi_u"),
            "vbar":("ocean_time","eta_v","xi_v"),
            "u":("ocean_time","s_rho","eta_u","xi_u"),
            "v":("ocean_time","s_rho","eta_v","xi_v"),
        }
        if aks:
            dims["AKs"]=("ocean_time","s_w","eta_rho","xi_rho")
        for k,dd in dims.items():
            var=ds.createVariable(k,"f8",dd)
            var[:]=0.0001 if k=="AKs" else 0.5


class HydroContract(unittest.TestCase):
    def file(self,**kwargs):
        tmp=tempfile.TemporaryDirectory()
        p=Path(tmp.name)/"synthetic_roms_history.nc"
        make_file(p,**kwargs)
        self.addCleanup(tmp.cleanup)
        return p

    def test_valid_three_snapshots_with_aks(self):
        result=inspect_hydrodynamics(self.file())
        self.assertEqual(result["status"],"SCHEMA_PASS_OFFLINE_PHYSICS_NOT_RUN")
        self.assertTrue(result["AKs_present"])
        self.assertEqual(result["fields"]["u"]["shape"],[3,2,5,5])

    def test_absent_aks_blocks_by_default(self):
        p=self.file(aks=False)
        with self.assertRaisesRegex(ValueError,"missing AKs"):
            inspect_hydrodynamics(p)
        self.assertFalse(inspect_hydrodynamics(p,require_aks=False)["AKs_present"])

    def test_nonmonotonic_time(self):
        with self.assertRaisesRegex(ValueError,"non-monotonic"):
            inspect_hydrodynamics(self.file(ordered=False))

    def test_invalid_stagger(self):
        with self.assertRaisesRegex(ValueError,"invalid u C-grid"):
            inspect_hydrodynamics(self.file(stagger_valid=False))

    def test_negative_aks(self):
        p=self.file()
        with Dataset(p,"a") as ds:
            ds.variables["AKs"][0,0,0,0]=-0.2
        with self.assertRaisesRegex(ValueError,"AKs must be nonnegative"):
            inspect_hydrodynamics(p)

    def test_missing_u(self):
        p=self.file()
        with Dataset(p,"a") as ds:
            # NetCDF does not permit delete; rename to simulate missing u.
            ds.renameVariable("u","u_incorrect_name")
        with self.assertRaisesRegex(ValueError,"missing required ROMS field: u"):
            inspect_hydrodynamics(p)


if __name__=="__main__":
    unittest.main()
