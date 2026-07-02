from abc import ABCMeta, abstractmethod
from typing import Dict, Optional, Tuple

from pylabrobot.capabilities.capability import BackendParams, CapabilityBackend
from pylabrobot.resources import Plate

# A well address as (row, column), both 1-indexed.
Well = Tuple[int, int]


class ValveDispensingBackend8(CapabilityBackend, metaclass=ABCMeta):
  """Abstract backend for valve-based, per-well bulk dispensing devices.

  Unlike peristaltic and syringe dispensers (which meter a whole column at once),
  valve dispensers address every well independently -- typically a row of solenoid
  microvalves fed from a pressurized reservoir, with volume metered by valve-open
  time. Volumes are therefore a mapping of 1-indexed ``(row, column)`` to
  microliters, not a per-column mapping.

  The Thermo Scientific Multidrop Combi nL is the reference implementation.
  """

  @abstractmethod
  async def dispense(
    self,
    plate: Plate,
    volumes: Dict[Well, float],
    backend_params: Optional[BackendParams] = None,
  ) -> None:
    """Dispense per-well volumes.

    Args:
      plate: Target plate.
      volumes: Mapping of 1-indexed ``(row, column)`` to volume in uL.
        Example: ``{(1, 1): 5.0, (1, 2): 5.0, (2, 1): 2.5}``
      backend_params: Backend-specific parameters (height, offset, pressure, ...).
    """

  @abstractmethod
  async def prime(
    self,
    plate: Plate,
    volume: Optional[float] = None,
    duration: Optional[float] = None,
    backend_params: Optional[BackendParams] = None,
  ) -> None:
    """Prime the fluid lines.

    Args:
      plate: Target plate.
      volume: Prime volume in uL (if the device meters priming by volume).
      duration: Prime duration in seconds (for hold-to-run priming, where the
        device pumps continuously for the given time).
      backend_params: Backend-specific parameters.
    """

  @abstractmethod
  async def purge(
    self,
    plate: Plate,
    volume: Optional[float] = None,
    duration: Optional[float] = None,
    backend_params: Optional[BackendParams] = None,
  ) -> None:
    """Purge (empty) the fluid lines.

    Args:
      plate: Target plate.
      volume: Purge volume in uL (if the device meters purging by volume).
      duration: Purge duration in seconds (hold-to-run emptying).
      backend_params: Backend-specific parameters.
    """
