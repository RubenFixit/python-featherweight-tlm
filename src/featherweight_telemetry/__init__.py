"""
featherweight_telemetry — Python library for Featherweight Altimeters telemetry.

v0.1 supports the Featherweight GPS Tracker V2 ground station USB serial stream,
receive-only.  No commands are sent to the device.

Quick start::

    from featherweight_telemetry import GPSTracker

    for packet in GPSTracker(port="COM4").stream():
        print(packet)

Parser-only::

    from featherweight_telemetry import GPSTrackerParser

    parser = GPSTrackerParser()
    packet = parser.parse_line(line)
"""

from .exceptions import (
    ExportError,
    FeatherweightError,
    ParseError,
    ReplayError,
    SerialConnectionError,
)
from .export import export_csv, export_jsonl
from .gps_tracker import GPSTracker
from .models import (
    AnyPacket,
    BasePacket,
    BattBLEPacket,
    DeviceType,
    EventPacket,
    FixType,
    GPSPacket,
    LinkPacket,
    PacketType,
    TXStatPacket,
    UnitType,
    UnknownPacket,
)
from .parser import GPSTrackerParser
from .record import record
from .replay import replay, replay_raw
from .serial_port import list_ports, list_ports_detail

__version__ = "0.1.0"
__all__ = [
    # High-level API
    "GPSTracker",
    "GPSTrackerParser",
    # Models
    "AnyPacket",
    "BasePacket",
    "BattBLEPacket",
    "DeviceType",
    "EventPacket",
    "FixType",
    "GPSPacket",
    "LinkPacket",
    "PacketType",
    "TXStatPacket",
    "UnitType",
    "UnknownPacket",
    # I/O
    "list_ports",
    "list_ports_detail",
    "record",
    "replay",
    "replay_raw",
    "export_csv",
    "export_jsonl",
    # Exceptions
    "ExportError",
    "FeatherweightError",
    "ParseError",
    "ReplayError",
    "SerialConnectionError",
]
