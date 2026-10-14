"""Synthetic double-sided Bq ledger tests, NOT physical ROMS I10 PASS."""
from __future__ import annotations
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tracer_coupling"))
from budget import BudgetWindow, InterfaceWindow, ReleaseEvent, decay_exact, evaluate_budget


class BudgetTests(unittest.TestCase):
    def audit(self, beginning, ending, **kwargs):
        return evaluate_budget(BudgetWindow(beginning, ending, **kwargs), reference_bq=100, tolerance=1e-8)

    def test_parent_to_child_then_reverse(self):
        first = self.audit({"ES3K_only": 100, "UD1K_only": 0, "L3_300m": 0},
                           {"ES3K_only": 92, "UD1K_only": 8, "L3_300m": 0},
                           interfaces=(InterfaceWindow("ES3K_UD1K", 8, -8),))
        self.assertTrue(first["pass"])
        second = self.audit({"ES3K_only": 92, "UD1K_only": 8, "L3_300m": 0},
                            {"ES3K_only": 95, "UD1K_only": 5, "L3_300m": 0},
                            interfaces=(InterfaceWindow("ES3K_UD1K", -3, 3),))
        self.assertTrue(second["pass"])
        self.assertEqual(first["whole_domain_residual_bq"], 0)
        self.assertEqual(second["whole_domain_residual_bq"], 0)

    def test_two_interfaces(self):
        a = self.audit({"ES3K_only": 100, "UD1K_only": 0, "L3_300m": 0},
                       {"ES3K_only": 95, "UD1K_only": 2, "L3_300m": 3},
                       interfaces=(InterfaceWindow("ES3K_UD1K", 5, -5),
                                   InterfaceWindow("UD1K_L3", 3, -3)))
        self.assertTrue(a["pass"])
        self.assertEqual(set(a["interfaces"]), {"ES3K_UD1K", "UD1K_L3"})

    def test_balanced_global_inventory_does_not_hide_interface_error(self):
        x = self.audit({"ES3K_only": 100, "UD1K_only": 0, "L3_300m": 0},
                       {"ES3K_only": 92, "UD1K_only": 8, "L3_300m": 0},
                       interfaces=(InterfaceWindow("ES3K_UD1K", 8, -7.9),))
        self.assertEqual(x["whole_domain_residual_bq"], 0)
        self.assertFalse(x["pass"])

    def test_external_source_sink_and_decay(self):
        remaining, lost = decay_exact(100, 365.25 * 86400)
        x = self.audit({"ES3K_only": 100, "UD1K_only": 0, "L3_300m": 0},
                       {"ES3K_only": remaining, "UD1K_only": 0, "L3_300m": 0},
                       radioactive_decay_bq=lost)
        self.assertTrue(x["pass"])
        ext = self.audit({"ES3K_only": 0, "UD1K_only": 0, "L3_300m": 0},
                         {"ES3K_only": 6, "UD1K_only": 0, "L3_300m": 0},
                         outer_in_bq=4,outer_out_bq=1,
                         emissions=(ReleaseEvent("scenario:t0", "ES3K_only", 3),))
        self.assertTrue(ext["pass"])

    def test_duplicate_release_rejected(self):
        with self.assertRaises(ValueError):
            self.audit({"ES3K_only": 0, "UD1K_only": 0, "L3_300m": 0},
                       {"ES3K_only": 10, "UD1K_only": 0, "L3_300m": 0},
                       emissions=(ReleaseEvent("release123", "ES3K_only", 5),
                                  ReleaseEvent("release123", "UD1K_only", 5)))

    def test_missing_active_domain_rejected(self):
        with self.assertRaises(ValueError):
            self.audit({"ES3K_only": 100, "UD1K_only": 0},
                       {"ES3K_only": 100, "UD1K_only": 0})

    def test_invalid_negative_and_zero_reference(self):
        with self.assertRaises(ValueError):
            evaluate_budget(BudgetWindow({"ES3K_only": 1, "UD1K_only": 0, "L3_300m": 0},
                                         {"ES3K_only": 1, "UD1K_only": 0, "L3_300m": 0}),
                            reference_bq=0, tolerance=1e-8)
        with self.assertRaises(ValueError):
            self.audit({"ES3K_only": 100, "UD1K_only": 0, "L3_300m": 0},
                       {"ES3K_only": -1, "UD1K_only": 0, "L3_300m": 0})

if __name__ == "__main__":
    unittest.main()
