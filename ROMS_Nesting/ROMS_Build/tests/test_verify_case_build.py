#!/usr/bin/env python3
"""Fault-injection tests for the build verifier.

The verifier must go red when tide build evidence is broken, and it must not
claim a mode PASS unless the audited build actually produced that mode's
executable.  Everything below runs against a synthetic case root; no compiler,
MPI runtime or linked binary is involved.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess

BUILD_CORE = Path(__file__).resolve().parents[1] / "core"
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "build"
for candidate in (str(BUILD_CORE), str(SCRIPTS)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from build_context import resolve_build_context  # noqa: E402
from verify_case_build import NOT_CHECKED, fingerprint, verify_build  # noqa: E402

MODES = {
    "smoke": "romsM_japan_sea",
    "external_startup": "romsM_japan_sea",
    "external_1h": "romsM_japan_sea_release",
    "external_6h": "romsM_japan_sea_release",
    "external_24h": "romsM_japan_sea_release",
}

INFILE = """\
    MyAppCPP = JAPAN_SEA
      NtileI == 2
      NtileJ == 2
"""

#: Every needle validate_tide_build_artifacts looks for, split by file.
SET_TIDES = """
Etide(:,:)=0.0_r8
SSH_Tamp
Utide(:,:)=0.0_r8
UV_Tmajor
Vtide(:,:)=0.0_r8
ramp=TANH((tdays(ng)-dstart)/1.0_r8)
"""
TIDES_DATE = "zero_phase_date\nnetcdf_get_fvar\n"


def _fake_probe(netcdf_root: str, mpi_root: str):
    def probe(_context, command: str) -> CompletedProcess:
        if command.startswith(("ldd", "otool")):
            stdout = (
                f"\tlibnetcdf.so.19 => {netcdf_root}/lib/libnetcdf.so.19\n"
                f"\tlibnetcdff.so.7 => {netcdf_root}/lib/libnetcdff.so.7\n"
                f"\tlibmpi.so.12 => {mpi_root}/lib/release/libmpi.so.12\n"
            )
        else:
            stdout = "ifort (IFORT) 2021.9.0\nIntel(R) MPI Library 2021.9\nnetCDF-Fortran 4.5.3\n"
        return CompletedProcess([], 0, stdout=stdout, stderr="")

    return probe


class VerifyCaseBuildFaultInjection(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for sub in ("run", "input", "bin"):
            (self.root / sub).mkdir()
        for build_dir in ("build/Build_romsM", "build/Build_romsM_release"):
            path = self.root / build_dir
            path.mkdir(parents=True)
            (path / "checkdefs.f90").write_text(
                "      Coptions(is:is+6)=' HDF5,'\n"
                "      Coptions(is:is+4)=' MPI,'\n"
                "      Coptions(is:is+9)=' MASKING,'\n"
                "      Coptions(is:is+10)=' CURVGRID,'\n"
                "      Coptions(is:is+9)=' SOLVE3D,'\n"
                "      Coptions(is:is+9)=' SALINITY,'\n"
                "      Coptions(is:is+12)=' MY25_MIXING,'\n"
                "      Coptions(is:is+15)=' UV_SMAGORINSKY,'\n"
                "      Coptions(is:is+15)=' TS_SMAGORINSKY,'\n"
                "      Coptions(is:is+12)=' BULK_FLUXES,'\n"
                "      Coptions(is:is+9)=' SSH_TIDES,'\n"
                "      Coptions(is:is+8)=' UV_TIDES,'\n"
                "      Coptions(is:is+10)=' RAMP_TIDES,'\n"
                "      Coptions(is:is+11)=' T_PASSIVE,'\n"
            )
            (path / "mod_strings.f90").write_text(
                '        character (len=80)  :: my_fort = "ifort"\n'
                '        character (len=512) :: my_fflags = "-O3 -ip"\n'
                '        character (len=256) :: Hfile = "japan_sea.h"\n'
            )
            (path / "mod_netcdf.f90").write_text("      CMODE = nf90_netcdf4\n")
            (path / "set_tides.f90").write_text(SET_TIDES)
            (path / "tides_date.f90").write_text(TIDES_DATE)
            (path / "tides_date.o").write_bytes(b"OBJ")
        (self.root / "run" / "japan_sea.h").write_text("#define TIDES_DATE\n")
        for mode, binary in MODES.items():
            (self.root / "run" / f"ocean_japan_sea_{mode}.in").write_text(INFILE)
            target = self.root / "bin" / binary
            if not target.exists():
                target.write_bytes(f"ARTIFACT {binary}".encode())
                target.chmod(0o755)
        # Provenance records tie each artifact to its build; without them the
        # audit must refuse to call anything PASS.
        provenance = self.root / "logs" / "build_provenance"
        provenance.mkdir(parents=True)
        for stamp, config in (("20261015T000000000000Z", "roms_build_config"),
                              ("20261015T000001000000Z", "roms_build_config.release")):
            binary_name = "romsM_japan_sea" if config == "roms_build_config" else "romsM_japan_sea_release"
            (provenance / f"{stamp}_{config}_default.json").write_text(
                json.dumps({"generated_utc": stamp, "binary_sha256": fingerprint(self.root / "bin" / binary_name)})
            )
        self.provenance_dir = provenance
        self.debug = self._context(None)
        self.release = self._context("roms_build_config.release.json")
        self.probe = _fake_probe(str(self.debug.netcdf_root), str(self.debug.mpi_root))

    def _context(self, config_path):
        return resolve_build_context(
            case_name="JAPAN_SEA", case_root=self.root, config_path=config_path
        )

    def _run(self, context, probe=None):
        return verify_build(context, probe=probe or self.probe)

    # ---- P0-REV-1: tide build issues must reach the verdict ---------------

    def test_healthy_tree_passes(self):
        report = self._run(self.debug)
        self.assertEqual(report["status"], "CASE_BINARY_AND_CPP_LINK_PASS", report["issues"])
        self.assertEqual(report["tide_build_issues"], [])

    def test_broken_tide_signature_fails_the_build(self):
        """Fault injection: drop a required signature from set_tides.f90."""
        (self.debug.paths.build_dir / "set_tides.f90").write_text(
            SET_TIDES.replace("UV_Tmajor", "")
        )
        report = self._run(self.debug)
        self.assertNotEqual(report["status"], "CASE_BINARY_AND_CPP_LINK_PASS")
        self.assertTrue(report["tide_build_issues"], "tide issue was not collected")
        self.assertTrue(
            any("UV_TIDES" in item for item in report["issues"]),
            f"tide issue did not reach the top-level verdict: {report['issues']}",
        )

    def test_missing_tide_source_fails_the_build(self):
        (self.debug.paths.build_dir / "set_tides.f90").unlink()
        report = self._run(self.debug)
        self.assertNotEqual(report["status"], "CASE_BINARY_AND_CPP_LINK_PASS")
        self.assertTrue(report["tide_build_issues"])

    def test_missing_tides_date_object_fails_the_build(self):
        (self.debug.paths.build_dir / "tides_date.o").unlink()
        report = self._run(self.debug)
        self.assertNotEqual(report["status"], "CASE_BINARY_AND_CPP_LINK_PASS")

    # ---- P0-REV-2: a build only claims the modes it produced --------------

    def test_debug_build_does_not_claim_the_release_modes(self):
        report = self._run(self.debug)
        by_mode = {entry["mode"]: entry for entry in report["mode_verdicts"]}
        self.assertEqual(by_mode["smoke"]["status"], "PASS")
        self.assertEqual(by_mode["external_startup"]["status"], "PASS")
        for mode in ("external_1h", "external_6h", "external_24h"):
            self.assertEqual(by_mode[mode]["status"], NOT_CHECKED, mode)
            self.assertFalse(by_mode[mode]["checked_by_this_build"], mode)
        self.assertFalse(report["all_modes_covered_by_this_run"])
        self.assertEqual(
            sorted(report["modes_not_checked_in_this_build"]),
            ["external_1h", "external_24h", "external_6h"],
        )

    def test_release_build_does_not_claim_the_debug_modes(self):
        report = self._run(self.release)
        by_mode = {entry["mode"]: entry for entry in report["mode_verdicts"]}
        for mode in ("smoke", "external_startup"):
            self.assertEqual(by_mode[mode]["status"], NOT_CHECKED, mode)
        self.assertEqual(by_mode["external_24h"]["status"], "PASS")
        self.assertEqual(
            sorted(report["modes_not_checked_in_this_build"]), ["external_startup", "smoke"]
        )

    def test_removing_the_release_binary_is_not_waved_through(self):
        """The debug audit must stop claiming anything about the release modes."""
        (self.root / "bin" / "romsM_japan_sea_release").unlink()
        report = self._run(self.debug)
        self.assertNotEqual(report["status"], "CASE_BINARY_AND_CPP_LINK_PASS")
        self.assertTrue(any("external_24h" in item for item in report["issues"]), report["issues"])

    def test_swapped_binaries_are_not_waved_through(self):
        """Swapping the two executables must not inherit either build's PASS.

        Each audit compares the file its modes run against the SHA its own build
        recorded, so a swapped or hand-edited artifact is caught rather than
        re-blessed by being fingerprinted again.
        """
        debug_bin = self.root / "bin" / "romsM_japan_sea"
        release_bin = self.root / "bin" / "romsM_japan_sea_release"
        release_bin.write_bytes(debug_bin.read_bytes())  # release slot now holds debug bytes

        report = self._run(self.release)
        by_mode = {entry["mode"]: entry for entry in report["mode_verdicts"]}
        self.assertEqual(by_mode["external_24h"]["status"], "FAIL")
        self.assertNotEqual(report["status"], "CASE_BINARY_AND_CPP_LINK_PASS")
        self.assertFalse(report["artifact_matches_provenance"])
        self.assertTrue(any("provenance" in item for item in report["issues"]), report["issues"])

    def test_tampered_artifact_is_detected(self):
        (self.root / "bin" / "romsM_japan_sea").write_bytes(b"HAND EDITED")
        report = self._run(self.debug)
        self.assertNotEqual(report["status"], "CASE_BINARY_AND_CPP_LINK_PASS")
        self.assertFalse(report["artifact_matches_provenance"])
        by_mode = {entry["mode"]: entry for entry in report["mode_verdicts"]}
        self.assertEqual(by_mode["smoke"]["status"], "FAIL")

    def test_missing_provenance_is_not_waved_through(self):
        for path in self.provenance_dir.glob("*.json"):
            path.unlink()
        report = self._run(self.debug)
        self.assertNotEqual(report["status"], "CASE_BINARY_AND_CPP_LINK_PASS")
        self.assertIsNone(report["provenance_record"])
        self.assertTrue(any("no build provenance" in item for item in report["issues"]))

    def test_forbidden_cpp_fails(self):
        checkdefs = self.debug.paths.build_dir / "checkdefs.f90"
        checkdefs.write_text(checkdefs.read_text() + "      Coptions(is:is+9)=' NESTING,'\n")
        report = self._run(self.debug)
        self.assertNotEqual(report["status"], "CASE_BINARY_AND_CPP_LINK_PASS")
        self.assertIn("NESTING", report["forbidden_options_present"])

    def test_missing_required_cpp_fails(self):
        checkdefs = self.debug.paths.build_dir / "checkdefs.f90"
        checkdefs.write_text(checkdefs.read_text().replace("' MASKING,'", "' MASKINGX,'"))
        report = self._run(self.debug)
        self.assertNotEqual(report["status"], "CASE_BINARY_AND_CPP_LINK_PASS")
        self.assertTrue(any("MASKING" in item for item in report["issues"]))

    # ---- evidence separation ---------------------------------------------

    def test_evidence_files_are_distinct_per_build(self):
        debug_report = self._run(self.debug)
        release_report = self._run(self.release)
        self.assertNotEqual(
            debug_report["evidence_files"]["verification"],
            release_report["evidence_files"]["verification"],
        )
        log_dir = self.root / "logs" / "external_test"
        names = {path.name for path in log_dir.iterdir()}
        for report in (debug_report, release_report):
            self.assertIn(report["evidence_files"]["verification"], names)
            self.assertIn(report["evidence_files"]["dynamic_links"], names)
            self.assertIn(report["evidence_files"]["compiler_versions"], names)

    def test_workflow_and_roms_source_heads_are_reported_separately(self):
        report = self._run(self.debug)
        self.assertIn("workflow_repo", report)
        self.assertIn("roms_source_repo", report)
        for key in ("workflow_repo", "roms_source_repo"):
            self.assertIn("path", report[key])
            self.assertIn("head", report[key])
            self.assertIn("dirty", report[key])


if __name__ == "__main__":
    unittest.main()
