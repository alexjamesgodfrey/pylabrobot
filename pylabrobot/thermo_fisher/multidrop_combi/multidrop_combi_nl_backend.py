"""Valve-based per-well dispensing engine for the Thermo Scientific Multidrop Combi nL.

Unlike the standard Multidrop Combi (peristaltic pump, whole-column dispensing at
1/10 uL), the Combi nL is a **pressurized reservoir + 8 solenoid microvalves**: volume
is metered by valve-open time at a set pressure, and every well is individually
addressable. This backend therefore does NOT reuse the column-based
``PeristalticDispensing8`` model; it drives the nL's native per-well command set.

The command grammar was recovered from Thermo's FILLit ``CombinLEngine.dll``
(``SkanIt.CombinLEngine.Steps.Dispense``) and confirmed on a live nL (fw 1.00.41)
over RS232 across 96-, 384-, and 1536-well plates. A typical dispense is::

    PLA <8 geometry values>   plate definition (see define_plate / get_factory_plates)
    SDO <order>               dispensing order / traversal (optional)
    SOF <x> <y>               X/Y offset (optional)
    SDH <height>              dispense height (optional)
    SAV 0 0 0 0 0             clear the per-well volume map
    SAV c1 r1 c2 r2 vol       per-well volumes: column-first, 1-indexed rectangles,
                              run-length encoded (variable volume per well is fine)
    DIS                       execute

Confirmed on hardware:

* Volumes on the wire are **nanoliters** (integer) -- ``SAV .. 2000`` dispenses 2 uL.
* ``SAV`` fields are **column-first**: ``SAV 1 2 1 3`` -> column 1, rows 2-3 (B1, C1).
* Pressurize with ``PON 1`` (a bare ``PON`` is rejected); prime/empty are hold-to-run
  (``PRI 3000`` / ``EMP 1`` looped). The nL has no RFID, so plate geometry must be set
  explicitly (``PLA``) when changing format.

The public API takes microliters (float), as elsewhere in PyLabRobot.

.. warning::
   ``pressurize``/``release_pressure``/``dispense``/``prime``/``purge`` move fluid or
   pressurize the instrument. Nothing in this module runs them implicitly.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from pylabrobot.capabilities.bulk_dispensers.valve import ValveDispensingBackend8, Well
from pylabrobot.capabilities.capability import BackendParams
from pylabrobot.resources import Plate
from pylabrobot.thermo_fisher.multidrop_combi.driver import MultidropCombiDriver

logger = logging.getLogger(__name__)

# nL usable spec: 50 nL .. 50 uL. Firmware calibration table extends higher.
MIN_VOLUME_NL = 50
MAX_VOLUME_NL = 50_000


def _ul_to_nl(volume_ul: float) -> int:
  """Convert microliters (public unit) to the nL integer wire unit."""
  return round(volume_ul * 1000)


def encode_well_volumes(
  volumes: Dict[Well, int],
  *,
  clear: bool = True,
  merge: bool = True,
) -> List[str]:
  """Encode a per-well volume map into ``SAV`` commands, FILLit-style.

  Clears the instrument's volume map, then covers equal-volume wells with
  rectangular ``SAV`` blocks to reduce command count. Wells with different volumes
  each get their own block(s), so **variable volumes per well** are fully supported
  (e.g. gradients / dilution series). Wells with volume ``0`` (or absent) are not
  programmed.

  The instrument's ``SAV`` field order is **column-first** --
  ``SAV <col_start> <row_start> <col_end> <row_end> <volume>`` (1-indexed),
  confirmed on hardware: ``SAV 1 2 1 3`` dispenses into column 1, rows 2-3 (B1, C1).

  With ``merge`` (default), a greedy 2D pass grows each block right then down over
  equal-volume wells, so a uniform full plate collapses to a single ``SAV`` and a
  uniform column/row to one block; a checkerboard (no equal-volume neighbours) stays
  one ``SAV`` per well. The cover is exact -- every requested well gets its volume.

  Args:
    volumes: ``{(row, col): volume_nL}``, 1-indexed, only wells to dispense.
    clear: Prepend ``SAV 0 0 0 0 0`` to reset the instrument's volume map.
    merge: Merge equal-volume wells into maximal rectangles (else one per well).

  Returns:
    Ordered list of ``SAV`` command strings (no ``\\r\\n`` — the driver frames).
  """
  cmds: List[str] = []
  if clear:
    cmds.append("SAV 0 0 0 0 0")

  live = {w: v for w, v in volumes.items() if v}
  if not merge:
    for row, col in sorted(live):
      cmds.append(f"SAV {col} {row} {col} {row} {live[(row, col)]}")
    return cmds

  covered: set = set()
  for row, col in sorted(live):  # row-major
    if (row, col) in covered:
      continue
    vol = live[(row, col)]

    # grow right: extend columns while same volume, present, uncovered
    col_end = col
    while (
      (row, col_end + 1) in live
      and live[(row, col_end + 1)] == vol
      and (row, col_end + 1) not in covered
    ):
      col_end += 1

    # grow down: extend rows while the whole [col..col_end] span matches
    row_end = row
    while all(
      (row_end + 1, c) in live and live[(row_end + 1, c)] == vol and (row_end + 1, c) not in covered
      for c in range(col, col_end + 1)
    ):
      row_end += 1

    for r in range(row, row_end + 1):
      for c in range(col, col_end + 1):
        covered.add((r, c))
    cmds.append(f"SAV {col} {row} {col_end} {row_end} {vol}")
  return cmds


class MultidropCombiNlValveDispensingBackend8(ValveDispensingBackend8):
  """Native valve/per-well dispensing engine for the Multidrop Combi nL.

  Implements the :class:`ValveDispensingBackend8` capability backend. Reuses the
  shared :class:`MultidropCombiDriver` (RS232 serial) unchanged -- the driver is the
  wire; this backend owns the nL protocol. All physical operations are explicit
  methods; none run on construction or setup.

  Args:
    driver: A connected (or connectable) Multidrop driver for the nL.
  """

  def __init__(self, driver: MultidropCombiDriver):
    super().__init__()
    self._driver = driver

  async def _on_setup(self, backend_params: Optional[BackendParams] = None) -> None:
    """Clear any latched instrument error after the driver connects."""
    try:
      await self._driver.acknowledge_error()
    except Exception as e:  # noqa: BLE001 -- best-effort; a fresh instrument has no error to clear
      logger.debug("acknowledge_error on setup failed (ignored): %s", e)

  async def _on_stop(self) -> None:
    """Release reservoir pressure on teardown, so a stopped unit is left un-pressurized."""
    try:
      await self.release_pressure()
    except Exception as e:  # noqa: BLE001 -- best-effort; never block teardown on a POF failure
      logger.debug("release_pressure on stop failed (ignored): %s", e)

  # --- pressure (physical) ---

  async def pressurize(self, level: int = 1) -> None:
    """Pressurize the reagent reservoir (``PON <level>``). PHYSICAL.

    FILLit issues ``PON 1``; a bare ``PON`` is rejected by the firmware
    (status 3). Select a pressure profile with :meth:`select_pressure_profile`
    first if the instrument requires it.

    Args:
      level: Pressure level argument (default 1, as FILLit sends).
    """
    cmd = f"PON {level}"
    logger.info("[Combi nL %s] pressurize (%s)", self._driver.description, cmd)
    await self._driver.send_command(cmd, timeout=30.0)

  async def release_pressure(self) -> None:
    """Release reservoir pressure (``POF``). PHYSICAL."""
    logger.info("[Combi nL %s] release pressure", self._driver.description)
    await self._driver.send_command("POF", timeout=30.0)

  # --- configuration (non-motion) ---

  async def select_pressure_profile(self, pressure_index: int) -> None:
    """Select the valve/pressure profile (``SLP <idx> 0 1000``).

    ``pressure_index`` corresponds to a calibration speed/pressure level (see the
    instrument's ``REP 9``/``REP 10`` tables).
    """
    await self._driver.send_command(f"SLP {pressure_index} 0 1000", timeout=5.0)

  async def set_dispense_height(self, height_hundredths_mm: int) -> None:
    """Set dispense height (``SDH``), in 1/100 mm."""
    await self._driver.send_command(f"SDH {height_hundredths_mm}", timeout=5.0)

  async def set_dispense_offset(self, x: int, y: int) -> None:
    """Set X/Y dispense offset (``SOF``), in 1/100 mm."""
    await self._driver.send_command(f"SOF {x} {y}", timeout=5.0)

  async def set_dispensing_order(self, order: int) -> None:
    """Set dispensing order / traversal (``SDO``)."""
    await self._driver.send_command(f"SDO {order}", timeout=5.0)

  async def get_factory_plates(self) -> List[dict]:
    """Read the instrument's factory plate table (``REP`` line 3).

    The nL has no RFID auto-detect, so the active plate geometry must be set
    explicitly. Each ``REP 3`` row is a factory plate definition whose 8 numeric
    fields are exactly the :meth:`define_plate` / ``PLA`` arguments (positions in
    1/100 mm, grid, height, well volume).

    Returns:
      List of ``{"name", "columns", "rows", "height", "pla"}`` dicts. ``name`` has
      ``&`` where the instrument encodes spaces; ``pla`` is the 8-value arg list.
    """
    plates: List[dict] = []
    for line in await self._driver.report_parameters():
      parts = line.split()
      if len(parts) < 11 or parts[0] != "REP" or parts[1] != "3":
        continue
      try:
        pla = [int(v) for v in parts[3:11]]
      except ValueError:
        logger.debug("Skipping unparseable REP 3 row: %r", line)
        continue  # tolerate a malformed/truncated row without losing the rest
      plates.append(
        {
          "name": parts[2],
          "columns": pla[4],
          "rows": pla[5],
          "height": pla[6],
          "pla": pla,
        }
      )
    return plates

  async def define_plate(self, pla_args: List[int]) -> None:
    """Define the active plate geometry (``PLA``). Non-motion.

    Args:
      pla_args: The 8 ``PLA`` values -- typically a factory plate's ``pla`` field
        from :meth:`get_factory_plates`: ``[firstColX, lastColX, firstRowY,
        lastRowY, columns, rows, height_1/100mm, wellVolume]`` (positions 1/100 mm).
    """
    if len(pla_args) != 8:
      raise ValueError(f"PLA needs 8 args, got {len(pla_args)}: {pla_args}")
    await self._driver.send_command("PLA " + " ".join(str(v) for v in pla_args), timeout=5.0)

  @staticmethod
  def _to_validated_nl_map(volumes: Dict[Well, float]) -> Dict[Well, int]:
    """Convert a uL well map to validated integer nL, raising before any wire I/O.

    Wells with volume ``0`` (or negative) are dropped ("skip this well"). Any
    positive volume outside the nL range (50 nL .. 50 uL) raises ``ValueError``,
    so callers can validate the whole request up front and never half-program the
    instrument.
    """
    nl_map: Dict[Well, int] = {}
    for well, vol_ul in volumes.items():
      if vol_ul <= 0:
        continue  # 0 (or negative) means do not program this well
      vol_nl = _ul_to_nl(vol_ul)
      if not (MIN_VOLUME_NL <= vol_nl <= MAX_VOLUME_NL):
        raise ValueError(
          f"Well {well}: volume {vol_ul} uL ({vol_nl} nL) outside nL range "
          f"{MIN_VOLUME_NL}-{MAX_VOLUME_NL} nL (0.05-50 uL)."
        )
      nl_map[well] = vol_nl
    return nl_map

  async def program_well_volumes(self, volumes: Dict[Well, float]) -> None:
    """Program the per-well volume map (``SAV`` sequence). Non-motion.

    Args:
      volumes: ``{(row, col): volume_uL}``, 1-indexed. Volumes convert to nL.

    Raises:
      ValueError: If any requested (non-zero) volume is outside the nL range
        (50 nL .. 50 uL). Volumes of ``0`` mean "skip this well".
    """
    for cmd in encode_well_volumes(self._to_validated_nl_map(volumes)):
      await self._driver.send_command(cmd, timeout=5.0)

  # --- dispense (physical) ---

  @dataclass
  class DispenseParams(BackendParams):
    """Optional geometry applied before a per-well ``DIS``.

    Args:
      dispense_height: ``SDH`` drop height in 1/100 mm (e.g. 2000 = 20 mm). This is
        the tip-to-plate dispense height, separate from the plate's physical Z.
      offset: ``SOF`` (x, y) offset in 1/100 mm.
      dispensing_order: ``SDO`` traversal order.
      pressure_index: ``SLP`` pressure/valve profile index (from calibration).
    """

    dispense_height: Optional[int] = None
    offset: Optional[Tuple[int, int]] = None
    dispensing_order: Optional[int] = None
    pressure_index: Optional[int] = None

  async def dispense(
    self,
    plate: Optional[Plate] = None,
    volumes: Optional[Dict[Well, float]] = None,
    backend_params: Optional[BackendParams] = None,
  ) -> None:
    """Program per-well volumes and execute a dispense (``SAV`` … then ``DIS``). PHYSICAL.

    The reservoir must already be pressurized (:meth:`pressurize`). Optional geometry
    is applied first, then the well-volume map, then ``DIS``.

    Args:
      plate: Target plate (accepted for the capability interface; the ``SAV`` map is
        addressed directly by ``(row, col)`` so the plate is not otherwise required).
      volumes: ``{(row, col): volume_uL}``, 1-indexed.
      backend_params: Optional :class:`DispenseParams` (height/offset/order/pressure).
    """
    # Validate the whole request (including per-well volume ranges) up front so a
    # bad value raises before we send ANY command -- no geometry mutated, no SAV,
    # no DIS.
    live = {w: v for w, v in (volumes or {}).items() if v and v > 0}
    self._to_validated_nl_map(live)  # raises on any out-of-range volume
    if not live:
      raise ValueError("volumes must contain at least one well with a positive volume.")

    if backend_params is not None and isinstance(backend_params, self.DispenseParams):
      if backend_params.pressure_index is not None:
        await self.select_pressure_profile(backend_params.pressure_index)
      if backend_params.dispensing_order is not None:
        await self.set_dispensing_order(backend_params.dispensing_order)
      if backend_params.offset is not None:
        await self.set_dispense_offset(*backend_params.offset)
      if backend_params.dispense_height is not None:
        await self.set_dispense_height(backend_params.dispense_height)

    await self.program_well_volumes(volumes)
    logger.info(
      "[Combi nL %s] dispense: %d wells, %.3f-%.3f uL",
      self._driver.description,
      len(live),
      min(live.values()),
      max(live.values()),
    )
    await self._driver.send_command("DIS", timeout=180.0)

  # --- maintenance (physical) ---

  # FILLit's prime/empty buttons are hold-to-run: they loop a fixed ``PRI 3000`` /
  # ``EMP 1`` pulse while the button is held (decompiled ``CombinLPrimeForm.DoIt`` ->
  # ``CCombinLEngine.PRI(3000, -1)`` / ``EMP(1, -1)``; the ``-1`` second arg is omitted).
  PRIME_PULSE = 3000
  EMPTY_PULSE = 1

  async def prime(
    self,
    plate: Optional[Plate] = None,
    volume: Optional[float] = None,
    duration: Optional[float] = None,
    backend_params: Optional[BackendParams] = None,
  ) -> None:
    """Prime the tubing (``PRI``). PHYSICAL. Requires pressurization.

    On the nL a single ``PRI`` is a brief descend/retract pulse; FILLit's prime
    button is *hold-to-run*, looping the pulse while held. From dry, the tubing
    needs several seconds of pulses to fill. Pass ``duration`` to emulate holding.

    Args:
      plate: Accepted for the capability interface; unused on the wire.
      volume: Single-pulse argument. If given, sends one ``PRI <int(volume)>``.
      duration: Seconds to hold-prime, looping ``PRI 3000`` pulses. Takes
        precedence over ``volume``. If both are None, sends one ``PRI 3000`` pulse.
    """
    if duration is not None:
      start = time.monotonic()
      pulses = 0
      while time.monotonic() - start < duration:
        await self._driver.send_command(f"PRI {self.PRIME_PULSE}", timeout=120.0)
        pulses += 1
      logger.info(
        "[Combi nL %s] hold-prime %.1fs (%d x PRI %d)",
        self._driver.description,
        duration,
        pulses,
        self.PRIME_PULSE,
      )
      return
    arg = self.PRIME_PULSE if volume is None else int(volume)
    logger.info("[Combi nL %s] prime (PRI %d)", self._driver.description, arg)
    await self._driver.send_command(f"PRI {arg}", timeout=120.0)

  async def purge(
    self,
    plate: Optional[Plate] = None,
    volume: Optional[float] = None,
    duration: Optional[float] = None,
    backend_params: Optional[BackendParams] = None,
  ) -> None:
    """Purge/empty the tubing (``EMP``). PHYSICAL.

    Like priming, emptying is *hold-to-run*: a single ``EMP`` is one pulse; pass
    ``duration`` to loop ``EMP 1`` and clear a wet line.

    Args:
      plate: Accepted for the capability interface; unused on the wire.
      volume: Single-pulse argument. If given, sends one ``EMP <int(volume)>``.
      duration: Seconds to hold-empty, looping ``EMP 1`` pulses. Takes precedence
        over ``volume``. If both are None, sends one ``EMP 1`` pulse.
    """
    if duration is not None:
      start = time.monotonic()
      pulses = 0
      while time.monotonic() - start < duration:
        await self._driver.send_command(f"EMP {self.EMPTY_PULSE}", timeout=120.0)
        pulses += 1
      logger.info(
        "[Combi nL %s] hold-empty %.1fs (%d x EMP %d)",
        self._driver.description,
        duration,
        pulses,
        self.EMPTY_PULSE,
      )
      return
    arg = self.EMPTY_PULSE if volume is None else int(volume)
    logger.info("[Combi nL %s] purge (EMP %d)", self._driver.description, arg)
    await self._driver.send_command(f"EMP {arg}", timeout=120.0)

  async def abort(self) -> None:
    """Abort the current operation (``ABO`` — the command FILLit uses).

    For an immediate hard stop, use ``driver.send_abort_signal()`` (raw ESC).
    """
    logger.info("[Combi nL %s] abort (ABO)", self._driver.description)
    await self._driver.send_command("ABO", timeout=10.0)
