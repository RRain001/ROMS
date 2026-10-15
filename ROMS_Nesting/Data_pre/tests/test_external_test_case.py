"""External-forcing regression tests; only synthetic tiny grids, no model/API."""
from pathlib import Path
import os,json,re,subprocess,sys,tempfile,unittest

import numpy as np
from netCDF4 import Dataset

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'core'))
from external_test_case import audit_grid,copy_unchanged,sha256

class ExternalInfileTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'run').mkdir()
        self.grid=self.root/'SYNTHETIC_TEST_ONLY_GRID.nc'
        with Dataset(self.grid,'w') as ds:
            ds.createDimension('xi_rho',6);ds.createDimension('eta_rho',5)
            a=np.ones((5,6));a[:,0]=0
            ds.createVariable('mask_rho','i1',('eta_rho','xi_rho'))[:]=a
        self.params=BASE/'cases/JAPAN_SEA/config/project_parameters.json'
        self.before=sha256(self.params)
    def generate(self,mode,forcing='external',stop='2018-01-03T00:00:00'):
        env=os.environ.copy()
        for key in list(env):
            if key.startswith('ROMS_CASE_'):env.pop(key)
        p=subprocess.run([sys.executable,str(BASE/'scripts/run_support/create_pilot_infile.py'),
            '--case-name','JAPAN_SEA','--case-root',str(self.root),'--grid',str(self.grid),
            '--mode',mode,'--forcing-mode',forcing,'--dt-seconds','10',
            '--start-time','2018-01-02T00:00:00','--stop-time',stop],env=env,text=True,capture_output=True)
        self.assertEqual(sha256(self.params),self.before,'authoritative dates changed')
        return p
    def test_smoke_respects_explicit_external_forcing(self):
        p=self.generate('smoke');self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        text=(self.root/'run/ocean_japan_sea_smoke.in').read_text()
        self.assertRegex(text,r'LBC\(isFsur\)\s*==\s*Clo\s+Cha\s+Cha\s+Cha')
        self.assertRegex(text,r'NFFILES\s*==\s*2')
        self.assertRegex(text,r'TIME_REF\s*=\s*18581117.0d0')
        self.assertRegex(text,r'DSTART\s*=\s*58120.0000000000d0')
        self.assertRegex(text,r'LwSrc\s*==\s*F')
        self.assertRegex(text,r'SSFNAME\s*==\s*none')
        self.assertRegex(text,r'NUDNAME\s*==\s*none')
        self.assertNotIn('UNRESOLVED',text)
    def test_independent_external_durations_and_mpi_tiles(self):
        for mode,steps in [('external_startup',5),('external_1h',360),('external_6h',2160),('external_24h',8640)]:
            with self.subTest(mode=mode):
                p=self.generate(mode);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                text=(self.root/f'run/ocean_japan_sea_{mode}.in').read_text()
                self.assertEqual(re.search(r'^\s*NTIMES\s*=+\s*(\d+)',text,re.M)[1],str(steps))
                self.assertRegex(text,r'MyAppCPP\s*=\s*JAPAN_SEA\s')
                tiles=[int(re.search(rf'^\s*{k}\s*==\s*(\d+)',text,re.M)[1]) for k in ['NtileI','NtileJ']]
                self.assertEqual(tiles[0]*tiles[1],4)
    def test_external_mode_refuses_analytical_fallback(self):
        p=self.generate('external_1h','analytical');self.assertNotEqual(p.returncode,0)
        self.assertIn('require external forcing',p.stderr)
    def test_refuses_to_shorten_24h_request(self):
        p=self.generate('external_24h',stop='2018-01-02T06:00:00');self.assertNotEqual(p.returncode,0)
        self.assertIn('refusing to shorten',p.stderr)
    def test_registration_never_overwrites_different_existing_file(self):
        a=self.root/'original';b=self.root/'active'
        a.write_bytes(b'original');b.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):copy_unchanged(a,b)
        self.assertEqual(b.read_bytes(),b'existing');self.assertEqual(a.read_bytes(),b'original')
    def test_wrong_archive_checksum_is_rejected_before_registration(self):
        with self.assertRaisesRegex(ValueError,'SHA256'):
            audit_grid(self.grid,{}, {'source_sha256':'0'*64})
    def test_same_source_target_is_rejected(self):
        with self.assertRaises(ValueError):copy_unchanged(self.grid,self.grid)

if __name__=='__main__':unittest.main()
