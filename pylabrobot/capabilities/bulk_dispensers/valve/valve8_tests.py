"""Tests for the ValveDispensing8 per-well capability."""

import unittest
from typing import Dict, Optional

from pylabrobot.capabilities.bulk_dispensers.valve import (
  ValveDispensing8,
  ValveDispensingBackend8,
  Well,
)
from pylabrobot.capabilities.bulk_dispensers.valve.valve8 import _well_name_to_rc
from pylabrobot.capabilities.capability import BackendParams
from pylabrobot.resources.corning.plates import Cor_96_wellplate_360ul_Fb


class _CaptureBackend(ValveDispensingBackend8):
  """Records the well map the capability passes down."""

  def __init__(self):
    self.last_volumes: Optional[Dict[Well, float]] = None
    self.primed = False
    self.purged = False

  async def dispense(self, plate, volumes, backend_params=None):
    self.last_volumes = volumes

  async def prime(
    self, plate, volume=None, duration=None, backend_params: Optional[BackendParams] = None
  ):
    self.primed = True
    self.prime_duration = duration

  async def purge(
    self, plate, volume=None, duration=None, backend_params: Optional[BackendParams] = None
  ):
    self.purged = True
    self.purge_duration = duration


class WellNameTests(unittest.TestCase):
  def test_simple_names(self):
    self.assertEqual(_well_name_to_rc("A1"), (1, 1))
    self.assertEqual(_well_name_to_rc("H12"), (8, 12))
    self.assertEqual(_well_name_to_rc("B7"), (2, 7))

  def test_double_letter_rows_for_1536(self):
    self.assertEqual(_well_name_to_rc("Z1"), (26, 1))
    self.assertEqual(_well_name_to_rc("AA1"), (27, 1))
    self.assertEqual(_well_name_to_rc("AF48"), (32, 48))  # 1536-well corner

  def test_invalid(self):
    with self.assertRaises(ValueError):
      _well_name_to_rc("1A")
    with self.assertRaises(ValueError):
      _well_name_to_rc("A")


class CapabilityTests(unittest.IsolatedAsyncioTestCase):
  def _ready_capability(self):
    cap = ValveDispensing8(backend=_CaptureBackend())
    cap._setup_finished = True  # bypass device lifecycle for the test
    cap.plate = Cor_96_wellplate_360ul_Fb("p")
    return cap

  async def test_float_fills_every_well(self):
    cap = self._ready_capability()
    await cap.dispense(5.0)
    vols = cap.backend.last_volumes
    self.assertEqual(len(vols), 96)  # 12 x 8
    self.assertEqual(vols[(1, 1)], 5.0)
    self.assertEqual(vols[(8, 12)], 5.0)

  async def test_well_name_dict(self):
    cap = self._ready_capability()
    await cap.dispense({"A1": 5.0, "H12": 2.5})
    self.assertEqual(cap.backend.last_volumes, {(1, 1): 5.0, (8, 12): 2.5})

  async def test_rowcol_dict_passthrough(self):
    cap = self._ready_capability()
    await cap.dispense({(1, 1): 5.0, (2, 3): 1.0})
    self.assertEqual(cap.backend.last_volumes, {(1, 1): 5.0, (2, 3): 1.0})

  async def test_prime_and_purge(self):
    cap = self._ready_capability()
    await cap.prime(duration=10.0)
    await cap.purge(duration=5.0)
    self.assertTrue(cap.backend.primed)
    self.assertEqual(cap.backend.prime_duration, 10.0)  # duration flows to the backend
    self.assertTrue(cap.backend.purged)
    self.assertEqual(cap.backend.purge_duration, 5.0)

  async def test_requires_plate(self):
    cap = ValveDispensing8(backend=_CaptureBackend())
    cap._setup_finished = True
    with self.assertRaises(RuntimeError):
      await cap.dispense(5.0)  # no plate assigned

  async def test_requires_setup(self):
    cap = ValveDispensing8(backend=_CaptureBackend())
    cap.plate = Cor_96_wellplate_360ul_Fb("p2")
    with self.assertRaises(RuntimeError):
      await cap.dispense(5.0)  # setup_finished is False


if __name__ == "__main__":
  unittest.main()
