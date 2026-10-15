#!/usr/bin/env python3
"""Compile/run a tiny MPI+NetCDF4 ABI probe; never starts ROMS."""
from pathlib import Path
import argparse,json,shlex,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'core'))
from build_context import resolve_build_context,ensure_case_layout,probe_shell_command


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-name',required=True)
    p.add_argument('--config',default=None)
    p.add_argument('--parallel-io',action='store_true',help='Probe parallel NetCDF library capability even with master-rank ROMS I/O')
    a=p.parse_args()
    c=resolve_build_context(case_name=a.case_name,config_path=a.config)
    ensure_case_layout(c)
    root=c.case_root/'logs'/'external_test'/'toolchain';root.mkdir(parents=True,exist_ok=True)
    source=root/'mpi_netcdf_probe.f90';exe=root/'mpi_netcdf_probe'
    parallel=', comm=MPI_COMM_WORLD, info=MPI_INFO_NULL' if a.parallel_io or c.compiler.get('use_parallel_io') else ''
    source.write_text('''program abi_probe
use mpi
use netcdf
implicit none
integer :: ierr,rank,nproc,ncid,dimid,varid,st,allst
real :: value(1)
call MPI_Init(ierr)
call MPI_Comm_rank(MPI_COMM_WORLD,rank,ierr)
call MPI_Comm_size(MPI_COMM_WORLD,nproc,ierr)
st=0
'''+('' if parallel else 'if(rank==0) then\n')+f'''call check(nf90_create('abi_probe.nc',ior(nf90_clobber,nf90_netcdf4),ncid{parallel}))
call check(nf90_def_dim(ncid,'x',1,dimid))
call check(nf90_def_var(ncid,'value',nf90_float,(/dimid/),varid))
call check(nf90_enddef(ncid))
if(rank==0) call check(nf90_put_var(ncid,varid,(/42.0/)))
'''+('call MPI_Barrier(MPI_COMM_WORLD,ierr)\n' if parallel else '')+'''call check(nf90_close(ncid))
'''+('' if parallel else 'endif\n')+'''call MPI_Barrier(MPI_COMM_WORLD,ierr)
if(rank==0) then
call check(nf90_open('abi_probe.nc',nf90_nowrite,ncid))
call check(nf90_inq_varid(ncid,'value',varid))
call check(nf90_get_var(ncid,varid,value))
if(value(1)/=42.0) st=1
call check(nf90_close(ncid))
endif
call MPI_Allreduce(st,allst,1,MPI_INTEGER,MPI_MAX,MPI_COMM_WORLD,ierr)
if(allst/=0) call MPI_Abort(MPI_COMM_WORLD,allst,ierr)
if(rank==0) print *, 'MPI_NETCDF4_ABI_PASS ranks=',nproc
call MPI_Finalize(ierr)
contains
subroutine check(code)
integer,intent(in) :: code
if(code/=nf90_noerr) then
print *, trim(nf90_strerror(code))
call MPI_Abort(MPI_COMM_WORLD,code,ierr)
endif
end subroutine
end program
''')
    compiler=c.build.get('make_variables',{}).get('FC','mpif90')
    commands=[f'command -v {shlex.quote(compiler)}',f'{shlex.quote(compiler)} -show',
              '"$NF_CONFIG" --all','"$NC_CONFIG" --all',
              f'{shlex.quote(compiler)} $("$NF_CONFIG" --fflags) {shlex.quote(str(source))} $("$NF_CONFIG" --flibs) -o {shlex.quote(str(exe))}',
              f'{"otool -L" if sys.platform == "darwin" else "ldd"} {shlex.quote(str(exe))}',
              f'cd {shlex.quote(str(root))}',f'mpirun -np 2 {shlex.quote(str(exe))}']
    result=probe_shell_command(c,'\n'.join(commands))
    text=result.stdout+result.stderr
    (root/'probe.log').write_text(text)
    report={'case':a.case_name,'build_config':str(c.build_config_path),'compiler':compiler,
            'parallel_netcdf4':bool(parallel),'returncode':result.returncode,
            'abi_pass':result.returncode==0 and 'MPI_NETCDF4_ABI_PASS' in text,
            'ROMS_integration':'NOT_RUN','log':str(root/'probe.log')}
    (root/'probe.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if not report['abi_pass']:print(text[-5000:]);raise SystemExit(1)

if __name__=='__main__': main()
