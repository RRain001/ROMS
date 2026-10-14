#!/usr/bin/env python3
"""Regression tests for TPXO complex parsing and ROMS tide reconstruction."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT / "Data_pre" / "core", ROOT / "Data_pre" / "impl" / "preprocessing"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from create_tides_from_tpxo import current_ellipse, parse_zero_phase_date  # noqa: E402
from stage_tpxo_elevation_atlas import (  # noqa: E402
    otps_elevation_phase,
    read_constituent_subset,
    read_transport_subset,
)


class TpxoTideRegressionTests(unittest.TestCase):
    def _write_record(self, values: np.ndarray) -> Path:
        handle = tempfile.NamedTemporaryFile(suffix=".tpxo", delete=False)
        path = Path(handle.name)
        with handle:
            handle.write(b"\x00" * 44)
            handle.write(np.asarray(values, dtype=">f4").tobytes())
        return path

    def test_interleaved_elevation_complex_layout(self) -> None:
        raw = np.array(
            [
                [[1.0, 2.0], [3.0, 4.0]],
                [[5.0, 6.0], [7.0, 8.0]],
            ],
            dtype=np.float32,
        )
        path = self._write_record(raw)
        try:
            result = read_constituent_subset(path, slice(None), slice(None), (2, 2))
        finally:
            path.unlink()
        np.testing.assert_allclose(result, raw[..., 0] + 1j * raw[..., 1])

    def test_interleaved_transport_complex_layout(self) -> None:
        raw = np.array(
            [
                [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]],
                [[9.0, 10.0, 11.0, 12.0], [13.0, 14.0, 15.0, 16.0]],
            ],
            dtype=np.float32,
        )
        path = self._write_record(raw)
        try:
            u, v = read_transport_subset(path, slice(None), slice(None), (2, 2))
        finally:
            path.unlink()
        np.testing.assert_allclose(u, raw[..., 0] + 1j * raw[..., 1])
        np.testing.assert_allclose(v, raw[..., 2] + 1j * raw[..., 3])

    def test_otps_ephase_sign(self) -> None:
        values = np.array([1.0 + 1.0j, 1.0 - 1.0j, -1.0 + 0.0j])
        np.testing.assert_allclose(otps_elevation_phase(values), [315.0, 45.0, 180.0])

    def test_roms_current_ellipse_formula(self) -> None:
        cmax, cmin, cangle, cphase = current_ellipse(np.array([1.0 + 0.0j]), np.array([0.0 + 0.0j]))
        np.testing.assert_allclose(cmax, [1.0])
        np.testing.assert_allclose(cmin, [0.0])
        np.testing.assert_allclose(cangle, [0.0])
        np.testing.assert_allclose(cphase, [0.0])

    def test_zero_phase_date_is_configured_not_simulation_start(self) -> None:
        self.assertEqual(parse_zero_phase_date(None), 20241001.0)
        self.assertEqual(parse_zero_phase_date("2025-01-01T00:00:00"), 20250101.0)


if __name__ == "__main__":
    unittest.main()
