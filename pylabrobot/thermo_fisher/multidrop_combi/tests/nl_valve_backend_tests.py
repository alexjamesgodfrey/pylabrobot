"""Tests for the Multidrop Combi nL valve/per-well dispensing engine.

Covers the ``SAV`` run-length encoder (byte format recovered from FILLit's
``CombinLEngine.dll``) and the backend's command sequencing, using a fake driver
that captures commands instead of touching hardware.
"""

import unittest

from pylabrobot.thermo_fisher.multidrop_combi.multidrop_combi_nl_backend import (
  MAX_VOLUME_NL,
  MultidropCombiNlValveDispensingBackend8,
  _ul_to_nl,
  encode_well_volumes,
)


class _FakeDriver:
  """Captures send_command calls; never touches a wire."""

  description = "fake-nl"

  def __init__(self, rep_lines=None):
    self.commands = []
    self._rep_lines = rep_lines or []

  async def send_command(self, cmd, timeout=None):
    self.commands.append(cmd)
    return []

  async def report_parameters(self):
    return self._rep_lines


class EncoderTests(unittest.TestCase):
  def test_clear_command_is_first(self):
    cmds = encode_well_volumes({(1, 1): 100})
    self.assertEqual(cmds[0], "SAV 0 0 0 0 0")

  def test_single_well_is_col_row_col_row_vol(self):
    # Field order is column-first: SAV <col_start> <row_start> <col_end> <row_end>.
    cmds = encode_well_volumes({(3, 5): 250}, clear=False)  # row 3, col 5
    self.assertEqual(cmds, ["SAV 5 3 5 3 250"])

  def test_adjacent_equal_volumes_merge_into_row_rectangle(self):
    vols = {(1, 1): 100, (1, 2): 100, (1, 3): 100}  # row 1, cols 1-3
    cmds = encode_well_volumes(vols, clear=False)
    self.assertEqual(cmds, ["SAV 1 1 3 1 100"])  # col 1..3 at row 1

  def test_different_volumes_do_not_merge(self):
    vols = {(1, 1): 100, (1, 2): 200}
    cmds = encode_well_volumes(vols, clear=False)
    self.assertEqual(cmds, ["SAV 1 1 1 1 100", "SAV 2 1 2 1 200"])

  def test_non_adjacent_columns_do_not_merge(self):
    vols = {(1, 1): 100, (1, 3): 100}  # gap at column 2
    cmds = encode_well_volumes(vols, clear=False)
    self.assertEqual(cmds, ["SAV 1 1 1 1 100", "SAV 3 1 3 1 100"])

  def test_zero_and_missing_wells_are_skipped(self):
    vols = {(1, 1): 0, (1, 2): 100}
    cmds = encode_well_volumes(vols, clear=False)
    self.assertEqual(cmds, ["SAV 2 1 2 1 100"])

  def test_merge_can_be_disabled(self):
    vols = {(1, 1): 100, (1, 2): 100}
    cmds = encode_well_volumes(vols, clear=False, merge=False)
    self.assertEqual(cmds, ["SAV 1 1 1 1 100", "SAV 2 1 2 1 100"])

  def test_2d_block_merges_to_single_rectangle(self):
    # rows 1-2 x cols 1-2, all equal -> one column-first rectangle SAV c1 r1 c2 r2.
    vols = {(1, 1): 100, (1, 2): 100, (2, 1): 100, (2, 2): 100}
    cmds = encode_well_volumes(vols, clear=False)
    self.assertEqual(cmds, ["SAV 1 1 2 2 100"])

  def test_full_grid_collapses_to_one_command(self):
    vols = {(r, c): 50 for r in range(1, 9) for c in range(1, 13)}  # full 96
    cmds = encode_well_volumes(vols)  # with clear
    self.assertEqual(cmds, ["SAV 0 0 0 0 0", "SAV 1 1 12 8 50"])

  def test_variable_volumes_stay_separate(self):
    # A 3-step gradient across a row -> three distinct single-well blocks.
    vols = {(1, 1): 100, (1, 2): 200, (1, 3): 300}
    cmds = encode_well_volumes(vols, clear=False)
    self.assertEqual(cmds, ["SAV 1 1 1 1 100", "SAV 2 1 2 1 200", "SAV 3 1 3 1 300"])

  def test_checkerboard_stays_per_well(self):
    # No equal-volume neighbours -> merge cannot help; one SAV per well.
    vols = {(r, c): 100 for r in range(1, 4) for c in range(1, 4) if (r + c) % 2 == 0}
    cmds = encode_well_volumes(vols, clear=False)
    self.assertEqual(len(cmds), len(vols))  # 5 wells, 5 commands


class UnitTests(unittest.TestCase):
  def test_ul_to_nl(self):
    self.assertEqual(_ul_to_nl(1.0), 1000)  # 1 uL = 1000 nL
    self.assertEqual(_ul_to_nl(0.05), 50)  # 50 nL floor
    self.assertEqual(_ul_to_nl(50.0), 50_000)  # 50 uL ceiling


class BackendSequencingTests(unittest.IsolatedAsyncioTestCase):
  async def test_program_well_volumes_emits_sav_sequence(self):
    drv = _FakeDriver()
    be = MultidropCombiNlValveDispensingBackend8(drv)
    await be.program_well_volumes({(1, 1): 1.0, (1, 2): 1.0})
    self.assertEqual(drv.commands, ["SAV 0 0 0 0 0", "SAV 1 1 2 1 1000"])

  async def test_dispense_programs_then_triggers_dis_last(self):
    drv = _FakeDriver()
    be = MultidropCombiNlValveDispensingBackend8(drv)
    await be.dispense(volumes={(1, 1): 2.0})
    self.assertEqual(drv.commands[0], "SAV 0 0 0 0 0")
    self.assertEqual(drv.commands[-1], "DIS")
    self.assertIn("SAV 1 1 1 1 2000", drv.commands)

  async def test_dispense_applies_geometry_before_volumes(self):
    drv = _FakeDriver()
    be = MultidropCombiNlValveDispensingBackend8(drv)
    params = be.DispenseParams(
      dispense_height=2000, offset=(10, -10), dispensing_order=1, pressure_index=2
    )
    await be.dispense(volumes={(1, 1): 1.0}, backend_params=params)
    self.assertEqual(
      drv.commands,
      [
        "SLP 2 0 1000",
        "SDO 1",
        "SOF 10 -10",
        "SDH 2000",
        "SAV 0 0 0 0 0",
        "SAV 1 1 1 1 1000",
        "DIS",
      ],
    )

  async def test_pressure_and_abort_commands(self):
    drv = _FakeDriver()
    be = MultidropCombiNlValveDispensingBackend8(drv)
    await be.pressurize()
    await be.pressurize(level=2)
    await be.release_pressure()
    await be.abort()
    self.assertEqual(drv.commands, ["PON 1", "PON 2", "POF", "ABO"])

  async def test_volume_out_of_range_raises(self):
    drv = _FakeDriver()
    be = MultidropCombiNlValveDispensingBackend8(drv)
    with self.assertRaises(ValueError):
      await be.program_well_volumes({(1, 1): 0.01})  # 10 nL < 50 nL floor
    with self.assertRaises(ValueError):
      await be.program_well_volumes({(1, 1): 60.0})  # 60 uL > 50 uL ceiling
    self.assertEqual(drv.commands, [])  # nothing sent on validation failure

  async def test_max_volume_boundary_ok(self):
    drv = _FakeDriver()
    be = MultidropCombiNlValveDispensingBackend8(drv)
    await be.program_well_volumes({(1, 1): MAX_VOLUME_NL / 1000})
    self.assertIn("SAV 1 1 1 1 50000", drv.commands)

  async def test_dispense_empty_or_all_zero_raises_and_sends_nothing(self):
    drv = _FakeDriver()
    be = MultidropCombiNlValveDispensingBackend8(drv)
    with self.assertRaises(ValueError):
      await be.dispense(volumes={})
    with self.assertRaises(ValueError):
      await be.dispense(volumes={(1, 1): 0.0})
    self.assertEqual(drv.commands, [])  # instrument never touched (no SAV clear)

  async def test_dispense_out_of_range_volume_sends_no_geometry(self):
    # An out-of-range volume must raise BEFORE any geometry command is sent, so
    # the instrument is not left with mutated SLP/SDH settings (validate up front).
    drv = _FakeDriver()
    be = MultidropCombiNlValveDispensingBackend8(drv)
    params = be.DispenseParams(dispense_height=2000, pressure_index=2)
    with self.assertRaises(ValueError):
      await be.dispense(volumes={(1, 1): 60.0}, backend_params=params)  # 60 uL > 50 uL
    self.assertEqual(drv.commands, [])  # no SLP, no SDH, no SAV, no DIS

  async def test_nonzero_subfloor_volume_raises(self):
    drv = _FakeDriver()
    be = MultidropCombiNlValveDispensingBackend8(drv)
    with self.assertRaises(ValueError):
      await be.program_well_volumes({(1, 1): 0.0001})  # 0.1 nL rounds to 0 but was requested
    self.assertEqual(drv.commands, [])

  async def test_zero_volume_wells_are_skipped_not_error(self):
    drv = _FakeDriver()
    be = MultidropCombiNlValveDispensingBackend8(drv)
    await be.program_well_volumes({(1, 1): 0.0, (1, 2): 1.0})
    self.assertEqual(drv.commands, ["SAV 0 0 0 0 0", "SAV 2 1 2 1 1000"])

  async def test_purge_duration_loops_emp(self):
    drv = _FakeDriver()
    be = MultidropCombiNlValveDispensingBackend8(drv)
    await be.purge(duration=0.0)  # zero window -> no pulses
    self.assertEqual(drv.commands, [])
    await be.purge()  # single EMP 1 pulse
    self.assertEqual(drv.commands, ["EMP 1"])


class FactoryPlateParsingTests(unittest.IsolatedAsyncioTestCase):
  async def test_parses_rep3_rows_into_pla_ints(self):
    drv = _FakeDriver(
      rep_lines=[
        "REP 1 CombinL",  # unrelated report line, ignored
        "REP 3 96&standard 100 200 300 400 12 8 1500 360",
      ]
    )
    be = MultidropCombiNlValveDispensingBackend8(drv)
    plates = await be.get_factory_plates()
    self.assertEqual(len(plates), 1)
    p = plates[0]
    self.assertEqual(p["name"], "96&standard")
    self.assertEqual((p["columns"], p["rows"], p["height"]), (12, 8, 1500))
    self.assertEqual(p["pla"], [100, 200, 300, 400, 12, 8, 1500, 360])  # 8 ints

  async def test_malformed_row_is_skipped_not_fatal(self):
    # A truncated/garbled REP 3 row must not abort parsing of the good rows.
    drv = _FakeDriver(
      rep_lines=[
        "REP 3 bad&row 100 200 xxx 400 12 8 1500 360",  # non-numeric token
        "REP 3 384&standard 10 20 30 40 24 16 1050 30",
      ]
    )
    be = MultidropCombiNlValveDispensingBackend8(drv)
    plates = await be.get_factory_plates()
    self.assertEqual([p["name"] for p in plates], ["384&standard"])


if __name__ == "__main__":
  unittest.main()
