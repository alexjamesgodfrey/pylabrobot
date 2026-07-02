"""Thermo Scientific Multidrop Combi nL device (RS232 serial)."""

from __future__ import annotations

from typing import Optional

from pylabrobot.capabilities.bulk_dispensers.valve import ValveDispensing8
from pylabrobot.device import Device
from pylabrobot.thermo_fisher.multidrop_combi.driver import MultidropCombiDriver
from pylabrobot.thermo_fisher.multidrop_combi.multidrop_combi_nl_backend import (
  MultidropCombiNlValveDispensingBackend8,
)


class MultidropCombiNl(Device):
  """Thermo Scientific Multidrop Combi nL reagent dispenser (RS232 serial).

  The Combi nL is a **valve-based, per-well** bulk dispenser: a pressurized reagent
  reservoir feeds 8 solenoid microvalves, with volume metered by valve-open time.
  It is therefore exposed as a
  :class:`~pylabrobot.capabilities.bulk_dispensers.valve.valve8.ValveDispensing8`
  capability (per-well volumes), not the column-based peristaltic capability used by
  the standard Multidrop Combi. It shares the Combi's ASCII command protocol and
  driver, over an RS232 serial connection.

  Args:
    port: Serial port (e.g. "COM3", "/dev/ttyUSB0").
    timeout: Default serial read timeout in seconds.
    driver: Optional pre-built driver (overrides port/timeout).
  """

  def __init__(
    self,
    port: str,
    timeout: float = 30.0,
    *,
    driver: Optional[MultidropCombiDriver] = None,
  ) -> None:
    if driver is None:
      driver = MultidropCombiDriver(port=port, timeout=timeout)
    super().__init__(driver=driver)
    self.driver: MultidropCombiDriver = driver
    self.valve_dispenser = ValveDispensing8(backend=MultidropCombiNlValveDispensingBackend8(driver))
    self._capabilities = [self.valve_dispenser]
