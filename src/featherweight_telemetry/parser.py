"""
Parser for Featherweight GPS Tracker V2 ground station USB serial output.

Input:  a single text line (trailing newline already stripped or not — both work).
Output: GPSPacket, LinkPacket, TXStatPacket, BattBLEPacket, EventPacket,
        UnknownPacket, or None.

None means the line is silently discarded:
  - blank / whitespace-only
  - binary FWT packets from the LoRa microcontroller
  - non-@ lines (build info, separator lines, etc.)

An UnknownPacket is returned for any @-prefixed line that did not match any
known type, so callers always have the raw text for debugging.

Protocol reference: Featherweight GPS Tracker User's Manual, Feb 2025, Appendix A.

Line formats (simplified):

  @ GPS_STAT <len> <year> <month> <date> <time> CRC_OK|CRC_ERR <unit_type> <tracker_id>
      Alt <alt_ft> lt <lat> ln <lon> Vel <h_vel> <heading> <v_vel>
      Fix <fix_type> # <sat_total> <sat_24db> <sat_32db> <sat_40db> [...] CRC: XXXX

  @ RX_NOMTK <len> <year> <month> <date> <time> CRC_OK|CRC_ERR Rx NomTrk <tracker_id>
      PkRx <pkt_rx> PkTx <pkt_tx> RSSI <gs_rssi> SNR <gs_snr>
      AckRx <ack_rx> AckTx <ack_tx> RSSI <trk_rssi> SNR <trk_snr>
      SF <lora_sf> frq <frequency_hz> trk_B_V <battery_mv> [<relay_temp_c> C] CRC: XXXX

  @ TX_STAT <len> <year> <month> <date> <time>
      Tx Apid <apid> Tx dur: <duration_ms> msec. SF<lora_sf> Freq <frequency_hz> CRC: XXXX

  @ BATT_BLE <len> <year> <month> <date> <time>
      <battery_mv> BLE+|- <temperature_c> degC CRC: XXXX [XXXX]

  @ <KNOWN_EVENT> <len> <year> <month> <date> <time> <payload...>

Tolerances handled:
  - Positive integers may or may not carry a leading '+' (firmware variation)
  - Integers may be zero-padded (e.g. 002053, +0000)
  - Multiple spaces between tokens
  - CRC_ERR lines are parsed normally (not discarded)
  - Time field appears in HH:MM:SS.mmm, MM:SS.s, or bare float formats
"""

from __future__ import annotations

import re

from .models import (
    AnyPacket,
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

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

# GPS_STAT capture groups:
#  1=year 2=month 3=date 4=time  5=unit_type  6=tracker_id
#  7=altitude_ft  8=latitude  9=longitude
# 10=h_vel_fps  11=heading_deg  12=v_vel_fps
# 13=fix_type  14=sat_total  15=sat_24db  16=sat_32db  17=sat_40db
_GPS_STAT_RE = re.compile(
    r"""
    \A@ \s* GPS_STAT \s+ \S+ \s+            # sync + type + packet-length
    (\d+) \s+ (\d+) \s+ (\d+) \s+           # year  month  date
    ([\d:.eE+\-]+) \s+                       # time (HH:MM:SS.mmm | MM:SS.s | float)
    CRC_\w+ \s+                              # CRC status (OK or ERR — both accepted)
    (TRK|GS|FND) \s+                         # unit type
    (\S+) \s+                                # tracker ID (callsign / LoRa ID)
    Alt \s+ ([+-]?\d+) \s+                   # altitude, feet
    lt  \s+ ([+-]?\d+\.\d+) \s+             # latitude, decimal degrees
    ln  \s+ ([+-]?\d+\.\d+) \s+             # longitude, decimal degrees
    Vel \s+ ([+-]?\d+) \s+                  # horizontal velocity, ft/s
            ([+-]?\d+) \s+                  # heading, degrees
            ([+-]?\d+) \s+                  # vertical velocity, ft/s
    Fix \s+ (\d) \s+                         # fix type
    \# \s+ (\d+) \s+                         # total satellites
             (\d+) \s+                       # sats > 24 dB-Hz
             (\d+) \s+                       # sats > 32 dB-Hz
             (\d+)                           # sats > 40 dB-Hz
    """,
    re.VERBOSE,
)

# RX_NOMTK capture groups:
#  1=year 2=month 3=date 4=time  5=tracker_id
#  6=pkt_rx  7=pkt_tx  8=gs_rssi  9=gs_snr
# 10=ack_rx  11=ack_tx  12=trk_rssi  13=trk_snr
# 14=lora_sf  15=frequency_hz  16=battery_mv
# 17=relay_temp_c  (optional)
_RX_NOMTK_RE = re.compile(
    r"""
    \A@ \s* RX_NOMTK \s+ \S+ \s+            # sync + type + packet-length
    (\d+) \s+ (\d+) \s+ (\d+) \s+           # year  month  date
    ([\d:.eE+\-]+) \s+                       # time
    CRC_\w+ \s+                              # CRC status
    Rx \s+ NomTrk \s+                        # literal header
    (\S+) \s+                                # tracker ID (may contain hyphens)
    PkRx  \s+ (\d+) \s+                      # packets received by GS
    PkTx  \s+ (\d+) \s+                      # packets sent by tracker
    RSSI  \s+ ([+-]?\d+) \s+                 # GS RSSI, dBm
    SNR   \s+ ([+-]?\d+) \s+                 # GS SNR, dB
    AckRx \s+ (\d+) \s+                      # acks received by tracker
    AckTx \s+ (\d+) \s+                      # acks sent by GS
    RSSI  \s+ ([+-]?\d+) \s+                 # tracker RSSI, dBm
    SNR   \s+ ([+-]?\d+) \s+                 # tracker SNR, dB
    SF    \s+ (\d+) \s+                       # LoRa spreading factor
    frq   \s+ (\d+) \s+                       # frequency, Hz
    trk_B_V \s+ (\d+)                         # battery, millivolts
    (?:                                        # optional relay temperature
        \s+ ([+-]?\d+) \s+ C
    )?
    """,
    re.VERBOSE,
)

# TX_STAT capture groups:
#  1=year 2=month 3=date 4=time
#  5=apid  6=tx_duration_ms  7=lora_sf  8=frequency_hz
#
# Sample: @ TX_STAT 91 2019 11 27 00:16:49.800 Tx Apid 11 Tx dur: 371 msec. SF12 Freq 926800000 CRC: B4E3
_TX_STAT_RE = re.compile(
    r"""
    \A@ \s* TX_STAT \s+ \S+ \s+              # sync + type + packet-length
    (\d+) \s+ (\d+) \s+ (\d+) \s+           # year  month  date
    ([\d:.eE+\-]+) \s+                       # time
    Tx \s+ Apid \s+ (\S+) \s+               # antenna/tracker apid token
    Tx \s+ dur: \s+ (\d+) \s+ msec\. \s+   # on-air duration, ms
    SF(\d+) \s+                              # LoRa spreading factor (no space before digit)
    Freq \s+ (\d+)                           # center frequency, Hz
    """,
    re.VERBOSE,
)

# BATT_BLE capture groups:
#  1=year 2=month 3=date 4=time
#  5=battery_mv  6=ble_status ("BLE+" or "BLE-")  7=temperature_c
#
# Sample: @ BATT_BLE 68 2020 5 17 0.176433519 4189 BLE+ 36 degC CRC: 3176 6C19
_BATT_BLE_RE = re.compile(
    r"""
    \A@ \s* BATT_BLE \s+ \S+ \s+            # sync + type + packet-length
    (\d+) \s+ (\d+) \s+ (\d+) \s+           # year  month  date
    ([\d:.eE+\-]+) \s+                       # time (bare float common pre-GPS-lock)
    (\d+) \s+                                # ground station battery, mV
    (BLE[+-]) \s+                            # BLE state: BLE+ (connected) or BLE- (off/disconnected)
    ([+-]?\d+) \s+ degC                      # board temperature, degrees C
    """,
    re.VERBOSE,
)

# Generic event-header pattern for known-but-not-yet-fully-decoded packet types.
# Captures the common header (type name, date, time) plus the raw payload.
#
# Capture groups:  1=event_name  2=year  3=month  4=date  5=time  6=payload
_EVENT_HEADER_RE = re.compile(
    r"""
    \A@ \s* (\w+) \s+ \S+ \s+               # event type name + packet-length
    (\d+) \s+ (\d+) \s+ (\d+) \s+           # year  month  date
    ([\d:.eE+\-]+) \s*                       # time
    (.*)                                     # raw payload (verbatim; per-type parsing deferred)
    """,
    re.VERBOSE | re.DOTALL,
)

# Known packet type names whose payload format is not yet fully decoded.
# These yield EventPacket (header parsed) rather than UnknownPacket (raw only).
# Per-type dataclasses are deferred until real hardware sample lines are available.
_KNOWN_EVENT_TYPES: frozenset[str] = frozenset({
    "FRST_FIX",   # first GPS fix after power-on
    "RX_TMOUT",   # receive timeout — no tracker packet heard in window
    "RLY_DIST",   # relay-node distance report
    "RX_FOUND",   # tracker found (lost-rocket search mode)
    "RX_COORD",   # coordinate received from tracker
    "RX_CRDFD",   # coordinate confirmed / acknowledged
    "GS_COORD",   # ground station coordinate broadcast
    "COORDFND",   # coordinate found
    "FS_CHNGE",   # frequency or spreading-factor change
})

_UNIT_TYPE_MAP: dict[str, UnitType] = {
    "TRK": UnitType.TRK,
    "GS": UnitType.GS,
    "FND": UnitType.FND,
}


# ---------------------------------------------------------------------------
# Public parser class
# ---------------------------------------------------------------------------


class GPSTrackerParser:
    """
    Stateless line-oriented parser for the Featherweight GPS Tracker V2
    ground station USB serial stream.

    Usage::

        parser = GPSTrackerParser()
        for raw_line in source:
            packet = parser.parse_line(raw_line)
            if packet is not None:
                process(packet)

    The parser never raises on malformed input — it returns UnknownPacket
    for unrecognised @ lines and None for silently-discarded lines.
    """

    def parse_line(self, line: str) -> AnyPacket | None:
        """
        Parse one text line from the ground station serial stream.

        Returns:
            GPSPacket, LinkPacket, TXStatPacket, BattBLEPacket, EventPacket,
            or UnknownPacket on a parseable @ line.
            None if the line should be silently discarded (blank, binary, non-@).
        """
        if not line:
            return None

        stripped = line.strip()
        if not stripped:
            return None

        # Binary LoRa MCU packets start with "FWT" — silently discard.
        if stripped.startswith("FWT"):
            return None

        # Only @ lines carry formatted telemetry.
        if not stripped.startswith("@"):
            return None

        m = _GPS_STAT_RE.match(stripped)
        if m:
            return self._parse_gps_stat(stripped, m)

        m = _RX_NOMTK_RE.match(stripped)
        if m:
            return self._parse_rx_nomtk(stripped, m)

        m = _TX_STAT_RE.match(stripped)
        if m:
            return self._parse_tx_stat(stripped, m)

        m = _BATT_BLE_RE.match(stripped)
        if m:
            return self._parse_batt_ble(stripped, m)

        # Known event types: parse the common header, preserve raw payload.
        em = _EVENT_HEADER_RE.match(stripped)
        if em and em.group(1) in _KNOWN_EVENT_TYPES:
            return self._parse_event(stripped, em)

        return UnknownPacket(raw_line=stripped)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_gps_stat(self, raw: str, m: re.Match) -> GPSPacket:  # type: ignore[type-arg]
        return GPSPacket(
            raw_line=raw,
            device_type=DeviceType.GPS_TRACKER_V2,
            packet_type=PacketType.GPS_STATUS,
            year=int(m.group(1)),
            month=int(m.group(2)),
            date=int(m.group(3)),
            uptime_s=_parse_time(m.group(4)),
            unit_type=_UNIT_TYPE_MAP.get(m.group(5), UnitType.TRK),
            tracker_id=m.group(6),
            altitude_ft=int(m.group(7)),
            latitude=float(m.group(8)),
            longitude=float(m.group(9)),
            h_vel_fps=int(m.group(10)),
            heading_deg=int(m.group(11)),
            v_vel_fps=int(m.group(12)),
            fix_type=FixType(int(m.group(13))),
            sat_total=int(m.group(14)),
            sat_24db=int(m.group(15)),
            sat_32db=int(m.group(16)),
            sat_40db=int(m.group(17)),
        )

    def _parse_rx_nomtk(self, raw: str, m: re.Match) -> LinkPacket:  # type: ignore[type-arg]
        relay_temp = int(m.group(17)) if m.group(17) is not None else 0
        return LinkPacket(
            raw_line=raw,
            device_type=DeviceType.GPS_TRACKER_V2,
            packet_type=PacketType.LINK_STATUS,
            year=int(m.group(1)),
            month=int(m.group(2)),
            date=int(m.group(3)),
            uptime_s=_parse_time(m.group(4)),
            tracker_id=m.group(5),
            pkt_rx=int(m.group(6)),
            pkt_tx=int(m.group(7)),
            gs_rssi=int(m.group(8)),
            gs_snr=int(m.group(9)),
            ack_rx=int(m.group(10)),
            ack_tx=int(m.group(11)),
            trk_rssi=int(m.group(12)),
            trk_snr=int(m.group(13)),
            lora_sf=int(m.group(14)),
            frequency_hz=int(m.group(15)),
            battery_mv=int(m.group(16)),
            relay_temp_c=relay_temp,
        )

    def _parse_tx_stat(self, raw: str, m: re.Match) -> TXStatPacket:  # type: ignore[type-arg]
        return TXStatPacket(
            raw_line=raw,
            device_type=DeviceType.GPS_TRACKER_V2,
            packet_type=PacketType.TX_STAT,
            year=int(m.group(1)),
            month=int(m.group(2)),
            date=int(m.group(3)),
            uptime_s=_parse_time(m.group(4)),
            apid=m.group(5),
            tx_duration_ms=int(m.group(6)),
            lora_sf=int(m.group(7)),
            frequency_hz=int(m.group(8)),
        )

    def _parse_batt_ble(self, raw: str, m: re.Match) -> BattBLEPacket:  # type: ignore[type-arg]
        return BattBLEPacket(
            raw_line=raw,
            device_type=DeviceType.GPS_TRACKER_V2,
            packet_type=PacketType.BATT_BLE,
            year=int(m.group(1)),
            month=int(m.group(2)),
            date=int(m.group(3)),
            uptime_s=_parse_time(m.group(4)),
            battery_mv=int(m.group(5)),
            ble_connected=m.group(6) == "BLE+",
            temperature_c=int(m.group(7)),
        )

    def _parse_event(self, raw: str, m: re.Match) -> EventPacket:  # type: ignore[type-arg]
        return EventPacket(
            raw_line=raw,
            device_type=DeviceType.GPS_TRACKER_V2,
            packet_type=PacketType.EVENT,
            event_name=m.group(1),
            year=int(m.group(2)),
            month=int(m.group(3)),
            date=int(m.group(4)),
            uptime_s=_parse_time(m.group(5)),
            payload=m.group(6).strip(),
        )


def _parse_time(s: str) -> float:
    """
    Convert the time token from a packet header to seconds (float).

    Formats observed in firmware:
      HH:MM:SS.mmm  — GPS_STAT with GPS lock (most common)
      MM:SS.s       — some packet types using internal clock
      SS.sss        — bare float seconds (common in BATT_BLE pre-GPS-lock)
      scientific    — firmware quirk; falls back to 0.0
    """
    if not s:
        return 0.0
    try:
        parts = s.split(":")
        if len(parts) == 3:
            return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
        if len(parts) == 2:
            return float(parts[0]) * 60.0 + float(parts[1])
        return float(parts[0])
    except (ValueError, IndexError):
        return 0.0
