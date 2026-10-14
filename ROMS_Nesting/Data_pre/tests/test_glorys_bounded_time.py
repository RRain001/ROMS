"""I4 GLORYS time-on-disk source reader interface regression.

Checks no full-time read even when the time dimension is the trailing
NetCDF axis. It is an interface test, not real CMEMS quality assurance.
"""
from __future__ import annotations
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"core"))
from roms_preprocessing_utils import read_dimensional_variable


class FakeNetCDFVar:
    def __init__(self, array,dimensions):
        self.data=np.ma.array(array)
        self.dimensions=tuple(dimensions)
        self.shape=self.data.shape
        self.selections=[]

    def __getitem__(self,key):
        if not isinstance(key,tuple):
            key=(key,)
        self.selections.append(key)
        time=next((k for k,name in enumerate(self.dimensions) if name=="time"),None)
        if time is not None and isinstance(key[time],slice):
            raise AssertionError("attempted full time-series read: var[:] is forbidden")
        return self.data[key]


class FakeDataset:
    def __init__(self,name,var):
        self.variables={name:var}


class ReadOneTimeRecord(unittest.TestCase):
    def test_time_first_and_3d_vertical(self):
        a=np.arange(10*3*5*4,dtype=float).reshape(10,3,5,4)
        var=FakeNetCDFVar(a,("time","depth","latitude","longitude"))
        arr=read_dimensional_variable(FakeDataset("uo",var),"uo","longitude","latitude",
                                      depth_name="depth",time_index=7)
        np.testing.assert_array_equal(arr,a[7])
        self.assertEqual(var.selections,[(7,slice(None),slice(None),slice(None))])

    def test_time_last_with_swapped_space_dimensions(self):
        a=np.arange(4*5*2*8,dtype=float).reshape(4,5,2,8)
        var=FakeNetCDFVar(a,("longitude","latitude","depth","time"))
        arr=read_dimensional_variable(FakeDataset("so",var),"so","longitude","latitude",
                                      depth_name="depth",time_index=5)
        np.testing.assert_array_equal(arr,np.transpose(a[:,:,:,5],(2,1,0)))
        self.assertEqual(var.selections,[(slice(None),slice(None),slice(None),5)])

    def test_zeta_time_first_and_no_time_2d(self):
        a=np.arange(4*5*6,dtype=float).reshape(4,5,6)
        var=FakeNetCDFVar(a,("time","latitude","longitude"))
        got=read_dimensional_variable(FakeDataset("zos",var),"zos","longitude","latitude",
                                      time_index=3)
        np.testing.assert_array_equal(got,a[3])
        b=np.arange(5*6,dtype=float).reshape(5,6)
        bare=FakeNetCDFVar(b,("latitude","longitude"))
        np.testing.assert_array_equal(
            read_dimensional_variable(FakeDataset("zos",bare),"zos","longitude","latitude"),
            b)
        self.assertEqual(bare.selections,[(slice(None),slice(None))])

    def test_masked_at_selected_record(self):
        a=np.ma.array(np.ones((5,3,2),dtype=float))
        a[3,2,1]=np.ma.masked
        var=FakeNetCDFVar(a,("time","latitude","longitude"))
        got=read_dimensional_variable(FakeDataset("zos",var),"zos","longitude","latitude",time_index=3)
        self.assertTrue(np.isnan(got[2,1]))
        self.assertTrue(np.isfinite(got[0,0]))

    def test_missing_or_invalid_time_index_fails_before_read(self):
        a=np.ones((6,3,4,5))
        var=FakeNetCDFVar(a,("time","depth","latitude","longitude"))
        with self.assertRaises(SystemExit):
            read_dimensional_variable(FakeDataset("u",var),"u","longitude","latitude",
                                      depth_name="depth",time_index=None)
        with self.assertRaises(IndexError):
            read_dimensional_variable(FakeDataset("u",var),"u","longitude","latitude",
                                      depth_name="depth",time_index=99)
        self.assertEqual(var.selections,[])


if __name__=="__main__":
    unittest.main()
