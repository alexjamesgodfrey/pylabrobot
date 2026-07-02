from typing import Dict, Optional, Union

from pylabrobot.capabilities.capability import BackendParams, Capability, need_capability_ready
from pylabrobot.resources import Plate

from .backend8 import ValveDispensingBackend8, Well


def _well_name_to_rc(name: str) -> Well:
  """Convert a well name like ``"A1"`` or ``"AF48"`` to 1-indexed ``(row, col)``.

  Row letters use bijective base-26 (A=1, Z=26, AA=27, ...), so 384- and
  1536-well plates (rows past Z) resolve correctly.
  """
  i = 0
  while i < len(name) and name[i].isalpha():
    i += 1
  letters, digits = name[:i], name[i:]
  if not letters or not digits.isdigit():
    raise ValueError(f"Invalid well name: {name!r}")
  row = 0
  for ch in letters.upper():
    row = row * 26 + (ord(ch) - ord("A") + 1)
  return row, int(digits)


class ValveDispensing8(Capability):
  """Valve-based, per-well bulk dispensing capability.

  For devices (like the Multidrop Combi nL) that address every well individually
  via a bank of solenoid valves, rather than a whole column at a time. Volumes may
  be given as:

  * a single ``float`` -- the same volume into every well of the assigned plate;
  * a dict keyed by well name (``{"A1": 5.0, "B1": 2.5}``); or
  * a dict keyed by 1-indexed ``(row, col)`` (``{(1, 1): 5.0}``).

  See :doc:`/user_guide/capabilities/dispensing/valve` for a walkthrough.
  """

  def __init__(self, backend: ValveDispensingBackend8):
    super().__init__(backend=backend)
    self.backend: ValveDispensingBackend8 = backend
    self._plate: Optional[Plate] = None

  @property
  def plate(self) -> Plate:
    if self._plate is None:
      raise RuntimeError("No plate assigned to this capability.")
    return self._plate

  @plate.setter
  def plate(self, value: Optional[Plate]):
    if value is not None and self._plate is not None:
      raise RuntimeError(f"A plate is already assigned ({self._plate.name}). Unassign it first.")
    self._plate = value

  def _to_well_map(
    self, volumes: Union[float, Dict[str, float], Dict[Well, float]]
  ) -> Dict[Well, float]:
    """Normalize the public ``volumes`` argument to ``{(row, col): uL}``."""
    if isinstance(volumes, (int, float)):
      n_cols = self.plate.num_items_x
      n_rows = self.plate.num_items_y
      vol = float(volumes)
      return {(r, c): vol for r in range(1, n_rows + 1) for c in range(1, n_cols + 1)}

    result: Dict[Well, float] = {}
    for key, vol in volumes.items():
      if isinstance(key, str):
        result[_well_name_to_rc(key)] = float(vol)
      elif isinstance(key, tuple) and len(key) == 2:
        result[(int(key[0]), int(key[1]))] = float(vol)
      else:
        raise ValueError(f"Invalid well key: {key!r} (use a well name or (row, col)).")
    return result

  @need_capability_ready
  async def dispense(
    self,
    volumes: Union[float, Dict[str, float], Dict[Well, float]],
    backend_params: Optional[BackendParams] = None,
  ) -> None:
    """Dispense per-well volumes into the assigned plate.

    Args:
      volumes: A single volume (uL) for every well, or a mapping of well name /
        ``(row, col)`` to volume in uL.
      backend_params: Backend-specific parameters.
    """
    await self.backend.dispense(
      plate=self.plate, volumes=self._to_well_map(volumes), backend_params=backend_params
    )

  @need_capability_ready
  async def prime(
    self,
    volume: Optional[float] = None,
    duration: Optional[float] = None,
    backend_params: Optional[BackendParams] = None,
  ) -> None:
    """Prime the fluid lines.

    Args:
      volume: Prime volume in uL (if the device meters priming by volume).
      duration: Prime duration in seconds (hold-to-run priming).
      backend_params: Backend-specific parameters.
    """
    await self.backend.prime(
      plate=self.plate, volume=volume, duration=duration, backend_params=backend_params
    )

  @need_capability_ready
  async def purge(
    self,
    volume: Optional[float] = None,
    duration: Optional[float] = None,
    backend_params: Optional[BackendParams] = None,
  ) -> None:
    """Purge (empty) the fluid lines.

    Args:
      volume: Purge volume in uL (if the device meters purging by volume).
      duration: Purge duration in seconds (hold-to-run emptying).
      backend_params: Backend-specific parameters.
    """
    await self.backend.purge(
      plate=self.plate, volume=volume, duration=duration, backend_params=backend_params
    )
