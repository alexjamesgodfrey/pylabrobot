"""Micronic Code Reader device."""

from __future__ import annotations

from typing import Optional

from pylabrobot.capabilities.barcode_scanning import BarcodeScanner
from pylabrobot.capabilities.rack_reading import RackReader
from pylabrobot.device import Device

from .barcode_scanning_backend import MicronicIOMonitorBarcodeScannerBackend
from .direct_rack_reading_backend import MicronicDirectDriver, MicronicDirectRackReadingBackend
from .driver import MicronicIOMonitorDriver
from .rack_reading_backend import MicronicIOMonitorRackReadingBackend


class MicronicCodeReader(Device):
  """Micronic Code Reader device using the IO Monitor HTTP server."""

  def __init__(
    self,
    host: str = "localhost",
    port: int = 2500,
    timeout: float = 60.0,
    poll_interval: float = 1.0,
    driver: Optional[MicronicIOMonitorDriver] = None,
  ):
    if driver is None:
      driver = MicronicIOMonitorDriver(host=host, port=port, timeout=timeout)
    super().__init__(driver=driver)
    self.driver: MicronicIOMonitorDriver = driver
    self.default_timeout = timeout
    self.default_poll_interval = poll_interval
    self.rack_reading = RackReader(backend=MicronicIOMonitorRackReadingBackend(driver))
    self.barcode_scanning = BarcodeScanner(
      backend=MicronicIOMonitorBarcodeScannerBackend(
        driver,
        timeout=timeout,
        poll_interval=poll_interval,
      )
    )
    self._capabilities = [self.rack_reading, self.barcode_scanning]

  def serialize(self) -> dict:
    return {
      **super().serialize(),
      "timeout": self.default_timeout,
      "poll_interval": self.default_poll_interval,
    }


class MicronicDirectCodeReader(Device):
  """Micronic rack reader that controls scanner hardware directly.

  This frontend follows the same v1b1 rack-reading capability surface as
  ``MicronicCodeReader`` but uses the direct hardware backend instead of the
  Micronic IO Monitor HTTP server.
  """

  def __init__(
    self,
    twain_scanner_path: Optional[str] = None,
    twain_source: str = "AVA6PlusG",
    image_dir: Optional[str] = None,
    serial_port: str = "COM4",
    timeout: float = 90.0,
    poll_interval: float = 1.0,
    serial_timeout_ms: int = 2500,
    min_wells: int = 96,
    keep_images: bool = False,
    image_input: Optional[str] = None,
    rack_id_override: Optional[str] = None,
    driver: Optional[MicronicDirectDriver] = None,
  ):
    if driver is None:
      driver = MicronicDirectDriver()
    super().__init__(driver=driver)
    self.driver: MicronicDirectDriver = driver
    self.default_timeout = timeout
    self.default_poll_interval = poll_interval
    self.rack_reading = RackReader(
      backend=MicronicDirectRackReadingBackend(
        twain_scanner_path=twain_scanner_path,
        twain_source=twain_source,
        image_dir=image_dir,
        serial_port=serial_port,
        scanner_timeout_ms=int(timeout * 1000),
        serial_timeout_ms=serial_timeout_ms,
        min_wells=min_wells,
        keep_images=keep_images,
        image_input=image_input,
        rack_id_override=rack_id_override,
      )
    )
    self._capabilities = [self.rack_reading]

  def serialize(self) -> dict:
    return {
      **super().serialize(),
      "timeout": self.default_timeout,
      "poll_interval": self.default_poll_interval,
    }
