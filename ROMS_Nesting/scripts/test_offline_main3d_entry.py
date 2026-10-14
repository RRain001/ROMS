#!/usr/bin/env python3
"""I8 source-level native driver fail-closed contract (not transport PASS).

Build the actual ROMS_Nesting main3d_offline.F with minimal Fortran
module stubs and assert that selecting OFFLINE_TPASSIVE never invokes
the normal main3d hydro solver by mistake.
"""
from __future__ import annotations
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"roms_src/roms/ROMS"
DRIVER=BASE/"Nonlinear/main3d_offline.F"
ROUTER=BASE/"Drivers/nl_roms.h"
CMAKE=BASE/"Nonlinear/CMakeLists.txt"

def main() -> None:
    content=ROUTER.read_text()
    assert "CALL main3d_offline (MyRunInterval)" in content
    assert "CALL main3d (MyRunInterval)" in content
    assert content.index("# if defined OFFLINE && defined OFFLINE_TPASSIVE") < content.index("CALL main3d_offline (MyRunInterval)")
    assert content.index("CALL main3d_offline (MyRunInterval)") < content.index("CALL main3d (MyRunInterval)")
    for name in ("main3d_offline.F","offline_tracer_stage.F"):
        assert "ROMS/Nonlinear/"+name in CMAKE.read_text()
    compiler=shutil.which("gfortran")
    if not compiler:
        raise RuntimeError("missing gfortran; do not skip native test")
    with tempfile.TemporaryDirectory() as tmp:
        d=Path(tmp)
        (d/"cppdefs.h").write_text("#define NONLINEAR\n#define SOLVE3D\n")
        (d/"stub.f90").write_text("module mod_param\n integer, parameter :: dp=kind(1d0)\nend module mod_param\n")
        (d/"runner.f90").write_text("program runner\n call main3d_offline(3600d0)\n stop 0\nend program runner\n")
        argv=[compiler,"-cpp","-ffree-form","-ffree-line-length-none","-I",str(d),"-J",str(d),
              "-DOFFLINE","-DOFFLINE_TPASSIVE",str(d/"stub.f90"),
              str(DRIVER),str(d/"runner.f90"),"-o",str(d/"test_driver")]
        rr=subprocess.run(argv,text=True,capture_output=True)
        if rr.returncode:
            raise RuntimeError("native offline main3d scaffold compile failed: "+rr.stdout+rr.stderr)
        ran=subprocess.run([str(d/"test_driver")],text=True,capture_output=True)
        combined=ran.stdout+"\n"+ran.stderr
        if ran.returncode==0 or "ROMS_NESTING_I8_BLOCKED_PORT_REQUIRED" not in combined:
            raise AssertionError("unimplemented offline model must fail-closed, not silently integrate: "+combined)
        print("I8_NATIVE_OFFLINE_MAIN3D_FAIL_CLOSED_PASS")
        # A normal ROMS build should not emit this entry: no file-level
        # stubs or broken visible symbols when OFFLINE is disabled.
        argv2=[compiler,"-cpp","-ffree-form","-ffree-line-length-none","-I",str(d),"-J",str(d),
               "-c",str(DRIVER),"-o",str(d/"driver_normal.o")]
        rr2=subprocess.run(argv2,text=True,capture_output=True)
        if rr2.returncode:
            raise RuntimeError("ordinary build must compile: "+rr2.stdout+rr2.stderr)
        print("I8_NATIVE_MAIN3D_DEFAULT_BUILD_PASS")
    print("FULL_OFFLINE_TRANSPORT_NOT_RUN")

if __name__=="__main__":
    main()
