"""Build framework configuration guards; no compiler or MPI invocation."""
from pathlib import Path
import contextlib,io,os,sys,unittest,tempfile
from dataclasses import replace
from unittest.mock import patch
from subprocess import CompletedProcess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'core'))
from build_context import (build_environment,execute_build,resolve_build_context,
                           shell_prelude,write_build_provenance)

class BuildConfigTests(unittest.TestCase):
    #: Toolchain identity the case must share with the main FDNPP build.  The
    #: FDNPP config itself lives outside this subtree, which must stay runnable
    #: on its own (see scripts/check_isolation.py), so parity is asserted on the
    #: fields that define it rather than by reading that file.
    FDNPP_TOOLCHAIN_FAMILY={'fort':'ifort','which_mpi':'intel','use_mpi':True,
        'use_mpif90':True,'use_large':True,'static':True,'exec':True,'use_netcdf4':True}
    def test_default_uses_the_fdnpp_toolchain_family(self):
        c=resolve_build_context(case_name='JAPAN_SEA')
        for key,value in self.FDNPP_TOOLCHAIN_FAMILY.items():
            with self.subTest(field=key):
                self.assertEqual(c.compiler[key],value,f'compiler.{key} diverges from the FDNPP family')
        self.assertEqual(c.variant.roms_application,'JAPAN_SEA')
        self.assertEqual(c.variant.executable_name,'romsM_japan_sea')
        self.assertEqual(build_environment(c).get('HOME'),os.environ.get('HOME'))
    def test_debug_and_release_configs_differ_only_in_optimisation(self):
        """The dual build must not be mistakable for one another."""
        debug=resolve_build_context(case_name='JAPAN_SEA')
        release=resolve_build_context(case_name='JAPAN_SEA',config_path='roms_build_config.release.json')
        self.assertTrue(debug.compiler['use_debug'])
        self.assertFalse(release.compiler['use_debug'])
        self.assertNotEqual(debug.variant.executable_name,release.variant.executable_name,
            'debug and release must not publish to the same executable name')
        self.assertNotEqual(debug.paths.build_dir,release.paths.build_dir,
            'debug and release must not share a build directory')
        for key,value in self.FDNPP_TOOLCHAIN_FAMILY.items():
            with self.subTest(field=key):
                self.assertEqual(release.compiler[key],value)
        self.assertEqual(release.compiler['use_parallel_io'],debug.compiler['use_parallel_io'])
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

    def test_provenance_is_unique_per_build_and_measured_from_artifacts(self):
        """Each build gets its own record, so a stale file is never evidence."""
        import json
        c=resolve_build_context(case_name='JAPAN_SEA')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            paths=replace(c.paths,build_root=root/'build',build_dir=root/'build/Build_romsM',
                          bin_dir=root/'bin',logs_dir=root/'logs',output_dir=root/'output')
            c=replace(c,case_root=root,paths=paths)
            paths.build_dir.mkdir(parents=True);paths.bin_dir.mkdir()
            (paths.build_dir/'checkdefs.f90').write_text("      Coptions(is:is+6)=' HDF5,'\n      Coptions(is:is+4)=' MPI,'\n")
            (paths.build_dir/'mod_strings.f90').write_text('        character (len=512) :: my_fflags = "-O3 -ip"\n')
            c.expected_binary.write_bytes(b'PROVENANCE_UNIT_TEST');c.expected_binary.chmod(0o755)
            first=write_build_provenance(c,'make -j 4')
            second=write_build_provenance(c,'make -j 4')
            self.assertNotEqual(first,second,'provenance records must not be reused')
            data=json.loads(first.read_text())
            for key in ('generated_utc','build_kind','use_debug','use_parallel_io','io_policy',
                        'git_head','build_config_sha256','compiled_options','fflags',
                        'binary_sha256','binary_bytes','build_command'):
                self.assertIn(key,data)
            self.assertEqual(data['build_kind'],'debug')
            self.assertEqual(data['fflags'],'-O3 -ip')
            self.assertEqual(sorted(data['compiled_options']),['HDF5','MPI'])
            self.assertEqual(data['build_command'],'make -j 4')
            self.assertIsNotNone(data['binary_sha256'])

if __name__=='__main__':unittest.main()
