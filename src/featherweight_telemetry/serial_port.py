"""
Serial port interface for the Featherweight GPS Tracker V2 ground station.

Receive-only — this module never writes to the serial port.
Serial settings: 115200 baud, 8N1, no flow control.

Only V2 ground stations (sold from November 2020) have an active USB data port.
The V1 micro-USB port is for charging only and will not emit data.

Typical port names by platform:
  Windows : COM4  (check Device Manager → Ports → CP2102 or CH340)
  Linux   : /dev/ttyUSB0  or  /dev/ttyACM0
  macOS   : /dev/cu.usbserial-*  or  /dev/cu.SLAB_USBtoUART
"""

from __future__ import annotations

from collections.abc import Generator

import serial
import serial.tools.list_ports

from .exceptions import SerialConnectionError
from .models import AnyPacket
from .parser import GPSTrackerParser

DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 1.0  # seconds; controls readline blocking interval


def list_ports() -> list[str]:
    """Return a list of available serial port device names on this machine."""
    return [p.device for p in serial.tools.list_ports.comports()]


def list_ports_detail() -> list[dict[str, str]]:
    """Return a list of dicts with device, description, and hwid for each port."""
    return [
        {"device": p.device, "description": p.description, "hwid": p.hwid}
        for p in serial.tools.list_ports.comports()
    ]


class GPSTrackerSerial:
    """
    Receive-only serial reader for the Featherweight GPS Tracker V2 ground station.

    Opens the serial port, reads lines, and yields parsed packets.  Gracefully
    handles KeyboardInterrupt (Ctrl-C) so the port is always closed on exit.

    Example::

        reader = GPSTrackerSerial(port="COM4")
        for packet in reader.stream():
            print(packet)
    """

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._parser = GPSTrackerParser()
        self._serial: serial.Serial | None = None

    def open(self) -> None:
        """Open the serial port.  Raises SerialConnectionError on failure."""
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                write_timeout=0,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
        except serial.SerialException as exc:
            raise SerialConnectionError(f"Cannot open {self.port}: {exc}") from exc

    def close(self) -> None:
        """Close the serial port if open."""
        if self._serial and self._serial.is_open:
            self._serial.close()

    def __enter__(self) -> GPSTrackerSerial:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def stream(self) -> Generator[AnyPacket, None, None]:
        """
        Yield parsed packets from the serial port indefinitely.

        Opens the port if not already open.  Stops cleanly on KeyboardInterrupt
        and always closes the port on exit.

        Only yields non-None packets (blank/binary/non-@ lines are skipped).
        """
        if self._serial is None:
            self.open()

        assert self._serial is not None
        try:
            while True:
                try:
                    raw = self._serial.readline()
                except serial.SerialException as exc:
                    raise SerialConnectionError(f"Serial read error on {self.port}: {exc}") from exc

                if not raw:
                    continue

                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                packet = self._parser.parse_line(line)
                if packet is not None:
                    yield packet

        except KeyboardInterrupt:
            pass
        finally:
            self.close()

    def stream_raw(self) -> Generator[str, None, None]:
        """
        Yield raw decoded lines from the serial port, including blank and
        non-@ lines.  Useful for recording.

        Opens the port if not already open.  Stops cleanly on KeyboardInterrupt.
        """
        if self._serial is None:
            self.open()

        assert self._serial is not None
        try:
            while True:
                try:
                    raw = self._serial.readline()
                except serial.SerialException as exc:
                    raise SerialConnectionError(f"Serial read error on {self.port}: {exc}") from exc

                if not raw:
                    continue

                yield raw.decode("utf-8", errors="replace").rstrip("\r\n")

        except KeyboardInterrupt:
            pass
        finally:
            self.close()
