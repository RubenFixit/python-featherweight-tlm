"""
featherweight_telemetry — Python library for Featherweight Altimeters telemetry.

v0.1 supports two devices, both receive-only (no commands sent):
  - GPS Tracker V2 ground station USB serial stream
  - Blue Raven altimeter USB serial stream (direct connection)

Quick start — GPS Tracker::

    from featherweight_telemetry import GPSTracker

    for packet in GPSTracker(port="COM4").stream():
        print(packet)

Quick start — Blue Raven::

    from featherweight_telemetry import BlueRaven

    for packet in BlueRaven(port="COM5").stream():
        print(packet)

Parser-only::

    from featherweight_telemetry import GPSTrackerParser, BlueRavenParser

    gps_parser = GPSTrackerParser()
    blr_parser = BlueRavenParser()
"""

from .blueraven import BlueRaven
from .blueraven_parser import BlueRavenParser
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
    BLRStatPacket,
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
    # High-level API — GPS Tracker V2
    "GPSTracker",
    "GPSTrackerParser",
    # High-level API — Blue Raven
    "BlueRaven",
    "BlueRavenParser",
    # Models
    "AnyPacket",
    "BasePacket",
    "BattBLEPacket",
    "BLRStatPacket",
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
