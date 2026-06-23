"""
Data models for Featherweight telemetry packets.

All packets are plain dataclasses — no Pydantic, no heavy dependencies.

Protocol reference: Featherweight GPS Tracker User's Manual, Feb 2025, Appendix A.
Serial settings: 115200 baud, 8N1, no flow control, V2 ground station USB only.

Packet types produced by the USB ground station serial stream:
  GPS_STAT   → GPSPacket        (position, velocity, fix state, satellites)
  RX_NOMTK   → LinkPacket       (RF link quality, packet counters, tracker battery)
  TX_STAT    → TXStatPacket     (per-transmission LoRa radio parameters)
  BATT_BLE   → BattBLEPacket    (ground station battery and BLE connection)
  known type → EventPacket      (header parsed; payload preserved pending sample data)
  anything   → UnknownPacket    (raw line preserved; never a crash)

Field units match the manual:
  altitude    – feet above sea level
  velocity    – feet per second
  heading     – degrees from North (may be negative; TODO validate sign convention)
  latitude    – decimal degrees, negative = South
  longitude   – decimal degrees, negative = West
  RSSI        – dBm
  SNR         – dB
  frequency   – Hz
  battery     – millivolts (divide by 1000 for volts)
  temperature – degrees Celsius
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class DeviceType(IntEnum):
    """Source of the telemetry stream."""

    GPS_TRACKER_V2 = 1


class PacketType(IntEnum):
    GPS_STATUS = 1
    LINK_STATUS = 2
    TX_STAT = 3
    BATT_BLE = 4
    EVENT = 5       # known type whose payload is not yet fully decoded
    UNKNOWN = 255   # truly unrecognised @ line


class UnitType(IntEnum):
    """Unit type encoded in GPS_STAT packets."""

    TRK = 1  # tracker (rocket)
    GS = 2   # ground station
    FND = 3  # "found" — lost-rocket mode


class FixType(IntEnum):
    NO_FIX = 0
    FIX_2D = 2
    FIX_3D = 3


@dataclass
class BasePacket:
    """Fields common to every parsed packet."""

    raw_line: str
    """The original unmodified text line from the serial stream."""

    device_type: DeviceType = DeviceType.GPS_TRACKER_V2
    packet_type: PacketType = PacketType.UNKNOWN


@dataclass
class GPSPacket(BasePacket):
    """
    Parsed GPS_STAT line from the Featherweight GPS Tracker ground station.

    Emitted approximately once per second when the tracker is transmitting.
    Year/month/date are 0 before the first GPS lock.

    TODO: Validate heading sign convention against real V2 hardware.
          The manual shows -155° which is unusual (expected 0–359).
    TODO: Parse optional per-satellite triplets (AAA_EE_SS format, Appendix A)
          appended after the standard fields on some firmware versions.
    """

    packet_type: PacketType = PacketType.GPS_STATUS

    # Source identification
    unit_type: UnitType = UnitType.TRK
    tracker_id: str = ""

    # UTC date (0 before GPS lock)
    year: int = 0
    month: int = 0
    date: int = 0

    # Time as seconds since midnight UTC (converted from HH:MM:SS.mmm or similar)
    uptime_s: float = 0.0

    # Position
    latitude: float = 0.0
    longitude: float = 0.0
    altitude_ft: int = 0

    # Velocity
    h_vel_fps: int = 0
    heading_deg: int = 0
    v_vel_fps: int = 0

    # GPS quality
    fix_type: FixType = FixType.NO_FIX
    sat_total: int = 0
    sat_24db: int = 0   # satellites ≥ 24 dB-Hz (yellow bar)
    sat_32db: int = 0   # satellites ≥ 32 dB-Hz (green bar)
    sat_40db: int = 0   # satellites ≥ 40 dB-Hz (blue bar)

    @property
    def has_gps_lock(self) -> bool:
        return self.fix_type != FixType.NO_FIX

    @property
    def battery_v(self) -> float | None:
        """GPS packets do not carry battery voltage; always None."""
        return None


@dataclass
class LinkPacket(BasePacket):
    """
    Parsed RX_NOMTK line from the Featherweight GPS Tracker ground station.

    Emitted once per received tracker packet, containing RF link statistics
    and the tracker's battery voltage.

    relay_temp_c is non-zero only when the packet was forwarded through a
    relay node — it reports the relay's temperature, not the tracker's.
    """

    packet_type: PacketType = PacketType.LINK_STATUS

    # Source identification
    tracker_id: str = ""

    # UTC date
    year: int = 0
    month: int = 0
    date: int = 0
    uptime_s: float = 0.0

    # Packet counters
    pkt_rx: int = 0   # tracker packets received by ground station
    pkt_tx: int = 0   # tracker packets sent (cumulative)
    ack_rx: int = 0   # GS acks received by tracker
    ack_tx: int = 0   # GS acks sent

    # Ground station receive quality
    gs_rssi: int = 0   # dBm
    gs_snr: int = 0    # dB

    # Tracker receive quality (ack direction)
    trk_rssi: int = 0  # dBm
    trk_snr: int = 0   # dB

    # LoRa radio
    lora_sf: int = 0          # spreading factor 7–12
    frequency_hz: int = 0     # center frequency, Hz

    # Power
    battery_mv: int = 0       # tracker battery, millivolts; divide by 1000 for volts

    # Relay (0 when not a relay-forwarded packet)
    relay_temp_c: int = 0

    @property
    def battery_v(self) -> float:
        return self.battery_mv / 1000.0

    @property
    def link_budget_db(self) -> int:
        """Rough downlink margin: SNR relative to minimum usable (-20 dB for SF12)."""
        return self.gs_snr


@dataclass
class TXStatPacket(BasePacket):
    """
    Parsed TX_STAT line from the Featherweight GPS Tracker ground station.

    Emitted after each LoRa uplink transmission reporting the radio parameters used.
    Useful for verifying which spreading factor and frequency the radio selected.

    Sample line (from reference repo spec, firmware Nov 2019):
      @ TX_STAT 91 2019 11 27 00:16:49.800 Tx Apid 11 Tx dur: 371 msec. SF12 Freq 926800000 CRC: B4E3

    TODO: Validate 'apid' semantics — appears to be an antenna/tracker identifier integer.
    """

    packet_type: PacketType = PacketType.TX_STAT

    year: int = 0
    month: int = 0
    date: int = 0
    uptime_s: float = 0.0

    apid: str = ""           # antenna / tracker ID token (e.g. "11")
    tx_duration_ms: int = 0  # on-air duration of the transmission, milliseconds
    lora_sf: int = 0         # LoRa spreading factor used (7–12)
    frequency_hz: int = 0    # center frequency, Hz


@dataclass
class BattBLEPacket(BasePacket):
    """
    Parsed BATT_BLE line from the Featherweight GPS Tracker ground station.

    Reports the GROUND STATION's own battery voltage and Bluetooth LE state.
    (The tracker's battery is in LinkPacket.battery_mv.)

    Sample line (from reference repo spec, firmware May 2020):
      @ BATT_BLE 68 2020 5 17 0.176433519 4189 BLE+ 36 degC CRC: 3176 6C19

    TODO: Validate BLE state strings — only "BLE+" has been observed.
          "BLE-" (disconnected) is assumed by analogy.
    TODO: Clarify the two-token CRC field seen in the sample (CRC: 3176 6C19).
    """

    packet_type: PacketType = PacketType.BATT_BLE

    year: int = 0
    month: int = 0
    date: int = 0
    uptime_s: float = 0.0

    battery_mv: int = 0        # ground station battery, millivolts
    ble_connected: bool = False # True when "BLE+"; False when "BLE-"
    temperature_c: int = 0     # ground station board temperature, degrees C

    @property
    def battery_v(self) -> float:
        return self.battery_mv / 1000.0


@dataclass
class EventPacket(BasePacket):
    """
    Header-parsed stub for known @ packet types that lack sample data.

    The common header fields (year/month/date/uptime_s) are extracted from
    every @ line; the remaining payload is preserved verbatim in ``payload``
    for future full parsing once real sample lines are available.

    Known types that currently map here:
      FRST_FIX  — first GPS fix after power-on
      RX_TMOUT  — receive timeout (no tracker packet heard within window)
      RLY_DIST  — relay-node distance report
      RX_FOUND  — tracker found (lost-rocket mode)
      RX_COORD  — coordinate received
      RX_CRDFD  — coordinate confirmed/acknowledged
      GS_COORD  — ground station coordinate broadcast
      COORDFND  — coordinate found
      FS_CHNGE  — frequency or spreading-factor change

    TODO: Add a dedicated dataclass for each type once sample lines are captured
          from real V2 hardware and the payload structure is confirmed.
    """

    packet_type: PacketType = PacketType.EVENT

    event_name: str = ""  # raw type string, e.g. "FRST_FIX"
    year: int = 0
    month: int = 0
    date: int = 0
    uptime_s: float = 0.0
    payload: str = ""     # everything after the time field, TODO fully parse


@dataclass
class UnknownPacket(BasePacket):
    """
    Any @ line that did not match any known packet type.

    The raw line is preserved so callers can log or inspect it without crashing.
    If you see a type here regularly, consider adding it to EventPacket's known
    list or implementing a full parser for it.
    """

    packet_type: PacketType = PacketType.UNKNOWN


# Type alias used throughout the library
AnyPacket = GPSPacket | LinkPacket | TXStatPacket | BattBLEPacket | EventPacket | UnknownPacket
