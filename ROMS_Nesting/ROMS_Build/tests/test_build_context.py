"""Build framework configuration guards; no compiler or MPI invocation."""
from pathlib import Path
import contextlib,io,os,sys,unittest,tempfile
from dataclasses import replace
from unittest.mock import patch
from subprocess import CompletedProcess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'core'))
from build_context import build_environment,execute_build,resolve_build_context,shell_prelude

class BuildConfigTests(unittest.TestCase):
    def test_default_matches_explicitly_selected_fdnpp_toolchain(self):
        c=resolve_build_context(case_name='JAPAN_SEA')
        self.assertEqual(c.compiler['fort'],'ifort')
        self.assertEqual(c.compiler['which_mpi'],'intel')
        self.assertEqual(c.variant.roms_application,'JAPAN_SEA')
        self.assertEqual(c.variant.executable_name,'romsM_japan_sea')
        self.assertEqual(build_environment(c).get('HOME'),os.environ.get('HOME'))
    def test_clean_and_build_keep_macros_inside_project(self):
        c=resolve_build_context(case_name='JAPAN_SEA')
        out=io.StringIO()
        with contextlib.redirect_stdout(out):execute_build(c,clean=True,dry_run=True)
        lines=[s for s in out.getvalue().splitlines() if s.startswith('make')]
        self.assertEqual(len(lines),2)
        for line in lines:
            self.assertIn('MAKE_MACROS='+str(c.paths.build_root/'make_macros.mk'),line)
        self.assertIn('FC=mpiifort',lines[-1])
    def test_debug_executable_is_published_under_case_name(self):
        c=resolve_build_context(case_name='JAPAN_SEA')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            paths=replace(c.paths,build_root=root/'build',build_dir=root/'build/Build_romsM',
                          bin_dir=root/'bin',logs_dir=root/'logs',output_dir=root/'output')
            c=replace(c,paths=paths)
            paths.bin_dir.mkdir()
            raw=paths.bin_dir/'romsG';raw.write_bytes(b'UNIT_TEST_ARTIFACT');raw.chmod(0o755)
            with patch('build_context.subprocess.run',return_value=CompletedProcess([],0)):
                self.assertEqual(execute_build(c,clean=False),0)
            self.assertEqual(c.expected_binary.read_bytes(),raw.read_bytes())
            self.assertTrue(os.access(c.expected_binary,os.X_OK))
    def test_gnu_profiles_do_not_source_intel_or_vendor_fallback(self):
        for name in ['roms_build_config.linux_gnu.json','roms_build_config.macos.json']:
            with self.subTest(profile=name):
                c=resolve_build_context(case_name='JAPAN_SEA',config_path=name)
                self.assertEqual(c.compiler['fort'],'gfortran')
                self.assertEqual(c.compiler['which_mpi'],'openmpi')
                self.assertIsNone(c.oneapi_setvars)
                text='\n'.join(shell_prelude(c))
                self.assertNotIn('my_build_paths.sh',text)
                self.assertNotIn('setvars.sh',text)
                self.assertFalse(c.compiler['use_parallel_io'])

if __name__=='__main__':unittest.main()
