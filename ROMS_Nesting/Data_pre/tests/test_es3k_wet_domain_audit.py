"""Scientific ES3K domain review tests; all fixtures are SYNTHETIC.

None of these tests claims GEBCO 2026, GSHHG, or ROMS physical acceptance.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nesting"))
from es3k_wet_domain_audit import analyze, audit_grid, REGIONS


def sample_arrays():
    lon_axis = np.linspace(123, 144, 85)
    lat_axis = np.linspace(33, 52, 77)
    lo, la = np.meshgrid(lon_axis, lat_axis)
    wet = np.ones(lo.shape, dtype=np.int8)
    pm = np.full(lo.shape, 1/3000)
    pn = np.full(lo.shape, 1/3000)
    return lo, la, wet, pm, pn


def staggers(mask):
    wet = np.asarray(mask, dtype=bool)
    return dict(mask_u=(wet[:, :-1] & wet[:, 1:]).astype('i1'),
                mask_v=(wet[:-1, :] & wet[1:, :]).astype('i1'),
                mask_psi=(wet[:-1, :-1] & wet[:-1, 1:]
                          & wet[1:, :-1] & wet[1:, 1:]).astype('i1'))


def netcdf_fixture(path, lo, la, wet, pm, pn, *, bad_u=False):
    ny, nx = lo.shape
    with Dataset(path, 'w') as nc:
        nc.grid_id = 'ES3K'
        nc.geometry_status = 'CANDIDATE_NOT_VALIDATED_FOR_ROMS'
        nc.synthetic_test_only = 'TRUE'
        nc.bathymetry_source = 'SYNTHETIC_TEST_FIXTURE'
        nc.shoreline_status = 'GEBCO_ONLY_SHORELINE_NOT_VALIDATED'
        for name, size in (('eta_rho',ny), ('xi_rho',nx),
                           ('eta_u',ny), ('xi_u',nx-1),
                           ('eta_v',ny-1), ('xi_v',nx),
                           ('eta_psi',ny-1), ('xi_psi',nx-1)):
            nc.createDimension(name,size)
        for key, arr in (('lon_rho',lo),('lat_rho',la),
                         ('mask_rho',wet),('pm',pm),('pn',pn)):
            nc.createVariable(key,'f8' if key!='mask_rho' else 'i1',
                              ('eta_rho','xi_rho'))[:] = arr
        for name, arr in staggers(wet).items():
            if name=='mask_u' and bad_u:
                arr[0,0] = 1-arr[0,0]
            loc=name.removeprefix('mask_')
            nc.createVariable(name,'i1',('eta_'+loc,'xi_'+loc))[:] = arr


class WetDomainAudit(unittest.TestCase):
    def setUp(self):
        self.lo, self.la, self.wet, self.pm, self.pn = sample_arrays()

    def run_analyzer(self, wet=None, **kwargs):
        mask = self.wet if wet is None else wet
        return analyze(self.lo,self.la,mask,self.pm,self.pn,
                       staggered=staggers(mask),**kwargs)

    def test_west_of_korea_water_is_reported_not_reclassified_as_land(self):
        before=self.wet.copy()
        report=self.run_analyzer()
        self.assertGreater(report['region_diagnostics']['west_of_korea_yellow_sea_proxy']['wet_rho_points'],0)
        self.assertIn('UNWANTED_WEST_OF_KOREA_WET_CELLS_REVIEW_DOMAIN_GEOMETRY', report['review_flags'])
        self.assertEqual(report['result_status'],'REVIEW_REQUIRED')
        self.assertFalse(report['mask_was_modified'])
        np.testing.assert_array_equal(before,self.wet)
        self.assertEqual(report['I3_physics_acceptance'],'NOT_RUN')
        self.assertEqual(report['wet_connected_component_count_4_neighbor'],1)
        self.assertEqual(report['stagger_mask_disagreement_counts'],
                         {'mask_u':0,'mask_v':0,'mask_psi':0})

    def test_four_straits_connected_in_synthetic_ocean(self):
        report=self.run_analyzer()
        for name in ('tsushima_strait','tsugaru_strait','soya_strait','tatar_strait'):
            self.assertTrue(report['strait_window_connected_to_core'][name],name)
        self.assertGreater(len(report['outer_boundary']['west']['wet_segments_ij_inclusive']),0)
        self.assertAlmostEqual(report['wet_area_km2_metrics_approx'],self.wet.size*9.)

    def test_artificial_barrier_detects_disconnected_straits(self):
        wet=self.wet.copy()
        wet[np.abs(self.la-39.0)<0.13]=0
        report=self.run_analyzer(wet)
        self.assertGreater(report['wet_connected_component_count_4_neighbor'],1)
        self.assertFalse(report['strait_window_connected_to_core']['tsushima_strait'])
        self.assertIn('STRAIT_WINDOW_HAS_NO_CONNECTED_WET_PATH',report['review_flags'])

    def test_no_yellow_sea_region_does_not_create_hardcoded_land(self):
        wet=self.wet.copy()
        pocket=REGIONS['west_of_korea_yellow_sea_proxy'].contains(self.lo,self.la)
        wet[pocket]=0  # Deliberate synthetic fixture, not production mask policy.
        report=self.run_analyzer(wet)
        self.assertEqual(report['region_diagnostics']['west_of_korea_yellow_sea_proxy']['wet_rho_points'],0)
        self.assertFalse(report['mask_was_modified'])

    def test_bad_mask_metrics_and_core_are_rejected(self):
        mask=self.wet.copy()
        wrong=staggers(mask)
        wrong['mask_u'][0,0]=0
        with self.assertRaisesRegex(ValueError,'staggered masks disagree'):
            analyze(self.lo,self.la,mask,self.pm,self.pn,staggered=wrong)
        with self.assertRaisesRegex(ValueError,'nonpositive'):
            analyze(self.lo,self.la,mask,-self.pm,self.pn)
        missing=self.wet.copy()
        missing[REGIONS['japan_basin_core'].contains(self.lo,self.la)]=0
        with self.assertRaisesRegex(ValueError,'Japan Basin'):
            self.run_analyzer(missing)

    def test_netcdf_readonly_and_cli_report(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'candidate.nc'
            q=Path(td)/'audit.json'
            netcdf_fixture(p,self.lo,self.la,self.wet,self.pm,self.pn)
            before=p.read_bytes()
            rep=audit_grid(p)
            self.assertEqual(rep['input_provenance']['synthetic_test_only'],'TRUE')
            self.assertEqual(rep['real_inputs_review'],'SYNTHETIC_ONLY')
            self.assertFalse(rep['source_is_approved_real_GEBCO_GSHHG'])
            script=ROOT/'scripts/nesting/audit_es3k_wet_domain.py'
            cmd=[sys.executable,str(script),'--grid',str(p),'--report-json',str(q)]
            s=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(s.returncode,0,s.stderr)
            self.assertTrue(q.exists())
            self.assertEqual(p.read_bytes(),before)
            strict=subprocess.run(cmd+['--strict-no-yellow-sea-wet'],
                                  capture_output=True,text=True)
            self.assertEqual(strict.returncode,2,strict.stderr)

    def test_grid_file_stagger_is_validated(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'bad.nc'
            netcdf_fixture(path,self.lo,self.la,self.wet,self.pm,self.pn,bad_u=True)
            with self.assertRaisesRegex(ValueError,'staggered masks disagree'):
                audit_grid(path)


if __name__=='__main__':
    unittest.main()
