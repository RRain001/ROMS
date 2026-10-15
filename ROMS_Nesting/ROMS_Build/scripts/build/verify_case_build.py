#!/usr/bin/env python3
"""Audit an actual case binary, compiled CPP branches and dynamic libraries.

This never launches ROMS or constructs missing runtime forcing.
"""
from pathlib import Path
import argparse,hashlib,json,re,shlex,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'core'))
from build_context import resolve_build_context,probe_shell_command
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'ROMS_Run/core'))
from run_context import resolve_run_context,validate_tide_build_artifacts


def fingerprint(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-name',required=True)
    a=p.parse_args()
    c=resolve_build_context(case_name=a.case_name)
    run=resolve_run_context(case_name=a.case_name,mode='external_startup')
    log=c.case_root/'logs/external_test';log.mkdir(parents=True,exist_ok=True)
    issues=[];binary=c.expected_binary
    if not binary.is_file():raise SystemExit(f'case executable missing: {binary}')
    cpp_path=c.paths.build_dir/'checkdefs.f90'
    cpp=cpp_path.read_text()
    active=sorted(set(re.findall(r"Coptions[^=]*='\s*([A-Z_0-9]+),",cpp)))
    required=set(run.mode.required_cpp_defs)-{'TIDES_DATE'}
    for option in sorted(required|{'MPI','T_PASSIVE'}):
        if option not in active:issues.append(f'compiled CPP option missing: {option}')
    forbidden={'ANA_GRID','ANA_INITIAL','ANA_SMFLUX','ANA_STFLUX','NESTING'}
    for option in sorted(forbidden & set(active)):issues.append(f'forbidden compiled CPP: {option}')
    strings=(c.paths.build_dir/'mod_strings.f90').read_text()
    for expected in [f'my_fort = "{c.compiler["fort"]}"','Hfile = "japan_sea.h"']:
        if expected not in strings:issues.append('compiled identity mismatch: '+expected)
    if binary.stat().st_mtime < cpp_path.stat().st_mtime:
        issues.append('binary older than compiled CPP source')
    issues += validate_tide_build_artifacts(run,binary)
    command=('otool -L' if sys.platform=='darwin' else 'ldd')+' '+shlex.quote(str(binary))
    linked=probe_shell_command(c,command)
    (log/'binary_links.log').write_text(linked.stdout+linked.stderr)
    if linked.returncode or 'not found' in linked.stdout:issues.append('unresolved dynamic library')
    for name in ['libnetcdf','libnetcdff','libmpi']:
        if name not in linked.stdout:issues.append('dynamic dependency absent: '+name)
    if c.compiler['which_mpi']=='intel':
        if 'openmpi' in linked.stdout.lower() or 'libmpi.so.40' in linked.stdout:
            issues.append('OpenMPI unexpectedly linked into Intel application')
        for name,prefix in [('libnetcdf',c.netcdf_root),('libnetcdff',c.netcdf_root),('libmpi',c.mpi_root)]:
            if prefix and not any(name in line and str(prefix) in line for line in linked.stdout.splitlines()):
                issues.append('dependency resolved outside configured prefix: '+name)
    versions=probe_shell_command(c,f'{c.compiler["fort"]} --version\nmpirun --version\n"$NF_CONFIG" --version\n"$NC_CONFIG" --version')
    (log/'compiler_versions.log').write_text(versions.stdout+versions.stderr)
    nc=(c.paths.build_dir/'mod_netcdf.f90').read_text()
    report={'status':'CASE_BINARY_AND_CPP_LINK_PASS' if not issues else 'FAIL','issues':issues,
      'case':a.case_name,'application':c.variant.roms_application,'binary':str(binary),
      'binary_bytes':binary.stat().st_size,'binary_sha256':fingerprint(binary),
      'header_sha256':fingerprint(c.variant.header_path),'compiled_checkdefs_sha256':fingerprint(cpp_path),
      'compiled_options':active,'tide_phase_date_compiled':not validate_tide_build_artifacts(run,binary),
      'NetCDF4_output_compiled':'CMODE = nf90_netcdf4' in nc,
      'MPI_io_policy':'master rank; library parallel-I/O verified separately',
      'versions':versions.stdout+versions.stderr,'dynamic_links':linked.stdout,
      'ROMS_started':False,'physical_acceptance':'NOT_RUN'}
    if not report['NetCDF4_output_compiled']:
        report['issues'].append('NetCDF4/HDF5 output branch not compiled');report['status']='FAIL'
    (log/'build_verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['status','issues','application','binary','binary_bytes','binary_sha256','NetCDF4_output_compiled','ROMS_started']},indent=2))
    raise SystemExit(int(bool(report['issues'])))

if __name__=='__main__':main()
