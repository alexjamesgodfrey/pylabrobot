import logging
from typing import Dict, Optional

from pylabrobot.capabilities.capability import BackendParams
from pylabrobot.resources import Plate

from .backend8 import ValveDispensingBackend8, Well

logger = logging.getLogger(__name__)


class ValveDispensingChatterboxBackend8(ValveDispensingBackend8):
  """Chatterbox backend for device-free testing."""

  async def dispense(
    self,
    plate: Plate,
    volumes: Dict[Well, float],
    backend_params: Optional[BackendParams] = None,
  ) -> None:
    logger.info("Dispensing %d wells to plate '%s': %s", len(volumes), plate.name, volumes)

  async def prime(
    self,
    plate: Plate,
    volume: Optional[float] = None,
    duration: Optional[float] = None,
    backend_params: Optional[BackendParams] = None,
  ) -> None:
    logger.info(
      "Priming valve lines for plate '%s' (volume=%s, duration=%s).",
      plate.name,
      volume,
      duration,
    )

  async def purge(
    self,
    plate: Plate,
    volume: Optional[float] = None,
    duration: Optional[float] = None,
    backend_params: Optional[BackendParams] = None,
  ) -> None:
    logger.info(
      "Purging valve lines for plate '%s' (volume=%s, duration=%s).",
      plate.name,
      volume,
      duration,
    )
