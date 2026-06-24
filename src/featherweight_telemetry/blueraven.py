"""
High-level BlueRaven convenience class.

Combines BlueRavenSerial + BlueRavenParser into a single entry point for the
most common use case: stream live telemetry from a Blue Raven altimeter via
its direct USB connection.

The Blue Raven is a separate device from the GPS Tracker V2 ground station.
It connects to its own USB serial port and emits @ BLR_STAT status packets
5 times per second.
"""

from __future__ import annotations

from collections.abc import Generator

from .models import AnyPacket
from .serial_port import BlueRavenSerial, list_ports, list_ports_detail


class BlueRaven:
    """
    Receive telemetry from a Featherweight Blue Raven altimeter connected
    via USB serial (direct connection — NOT through the GPS Tracker GS).

    Receive-only — never writes to the serial port.

    Example::

        from featherweight_telemetry import BlueRaven

        raven = BlueRaven(port="/dev/ttyACM0")
        for packet in raven.stream():
            print(packet)

    Args:
        port:      Serial port name.  Examples:
                     Windows : "COM5"
                     Linux   : "/dev/ttyACM0"
                     macOS   : "/dev/cu.usbmodem0001"
        baudrate:  Default 115200.  Only change if directed by Featherweight.
        timeout:   Serial read timeout in seconds (default 1.0).
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 1.0,
    ) -> None:
        self._serial = BlueRavenSerial(port=port, baudrate=baudrate, timeout=timeout)

    def stream(self) -> Generator[AnyPacket, None, None]:
        """
        Yield parsed packets from the Blue Raven.

        Runs until Ctrl-C, then closes the port cleanly.
        Only non-None packets are yielded (blank/non-@ lines are dropped).
        """
        yield from self._serial.stream()

    @staticmethod
    def list_ports() -> list[str]:
        """Return available serial port device names on this machine."""
        return list_ports()

    @staticmethod
    def list_ports_detail() -> list[dict[str, str]]:
        """Return detailed port info (device, description, hwid)."""
        return list_ports_detail()
