"""Regression: only disconnected shallow wet pools are excluded."""
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nesting"))
from ud1k_connected_core_candidate import connected_core_masks


class ConnectedCoreCandidate(unittest.TestCase):
    def test_preserves_connected_main_and_discards_small_islands(self):
        old=np.zeros((8,12),dtype=bool)
        old[:,5:]=True          # 56-cell true connected ocean
        old[0,1]=old[1,1]=True # 2-cell isolated wet boundary puddle
        old[3,0]=True          # one wet inland puddle
        masks,report=connected_core_masks(old)
        np.testing.assert_array_equal(masks["mask_rho"],np.where(old&(
            np.indices(old.shape)[1]>=5),1,0))
        self.assertEqual(report["wet_component_count"],3)
        self.assertEqual(report["component_mask_differences"]["mask_rho"]["removed_total"],3)
        self.assertEqual(report["component_mask_differences"]["mask_rho"]["removed_wet_perimeter"],2)
        self.assertEqual(report["component_mask_differences"]["mask_v"]["removed_total"],1)
        self.assertTrue(report["source_grid_modified"] is False)
        self.assertEqual(old[0,1],1)

    def test_ambiguous_equal_basin_rejected(self):
        m=np.zeros((4,12),bool)
        m[:,0:3]=True
        m[:,9:12]=True
        with self.assertRaisesRegex(ValueError,"unambiguous"):
            connected_core_masks(m)

    def test_does_not_mistake_diagonal_contacts_for_wet_channel(self):
        mask=np.zeros((6,7),bool)
        mask[:,4:]=True
        mask[1,1]=mask[2,2]=True
        new,report=connected_core_masks(mask)
        self.assertEqual(report["wet_component_count"],3)
        self.assertEqual(new["mask_rho"][1,1],0)
        self.assertEqual(new["mask_rho"][2,2],0)

    def test_empty_input_fails(self):
        with self.assertRaises(ValueError):
            connected_core_masks(np.zeros((5,6),bool))


if __name__=="__main__":
    unittest.main()
