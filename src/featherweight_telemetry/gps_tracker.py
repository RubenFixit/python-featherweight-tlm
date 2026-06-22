"""
High-level GPSTracker convenience class.

Combines GPSTrackerSerial + GPSTrackerParser into a single entry point
for the most common use case: stream live telemetry from a USB ground station.
"""

from __future__ import annotations

from collections.abc import Generator

from .models import AnyPacket
from .serial_port import GPSTrackerSerial, list_ports, list_ports_detail


class GPSTracker:
    """
    Receive telemetry from a Featherweight GPS Tracker V2 ground station
    connected via USB serial.

    Receive-only — never writes to the serial port.

    Example::

        from featherweight_telemetry import GPSTracker

        tracker = GPSTracker(port="COM4")
        for packet in tracker.stream():
            print(packet)

    Args:
        port:      Serial port name.  Examples:
                     Windows : "COM4"
                     Linux   : "/dev/ttyUSB0"
                     macOS   : "/dev/cu.usbserial-0001"
        baudrate:  Default 115200.  Only change if directed by Featherweight.
        timeout:   Serial read timeout in seconds (default 1.0).
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 1.0,
    ) -> None:
        self._serial = GPSTrackerSerial(port=port, baudrate=baudrate, timeout=timeout)

    def stream(self) -> Generator[AnyPacket, None, None]:
        """
        Yield parsed packets from the ground station.

        Runs until Ctrl-C, then closes the port cleanly.
        Only non-None packets are yielded (blank/binary lines are dropped).
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
