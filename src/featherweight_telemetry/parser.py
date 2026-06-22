"""
Parser for Featherweight GPS Tracker V2 ground station USB serial output.

Input:  a single text line (trailing newline already stripped or not — both work).
Output: GPSPacket, LinkPacket, UnknownPacket, or None.

None means the line is silently discarded:
  - blank / whitespace-only
  - binary FWT packets from the LoRa microcontroller
  - non-@ lines (build info, separator lines, etc.)

An UnknownPacket is returned for any @-prefixed line that did not match a
known type, so callers always have the raw text for debugging.

Protocol reference: Featherweight GPS Tracker User's Manual, Feb 2025, Appendix A.

Line formats (simplified):
  @ GPS_STAT <len> <year> <month> <date> <time> CRC_OK|CRC_ERR <unit_type> <tracker_id>
      Alt <alt_ft> lt <lat> ln <lon> Vel <h_vel> <heading> <v_vel>
      Fix <fix_type> # <sat_total> <sat_24db> <sat_32db> <sat_40db> [satellite triplets] CRC: XXXX

  @ RX_NOMTK <len> <year> <month> <date> <time> CRC_OK|CRC_ERR Rx NomTrk <tracker_id>
      PkRx <pkt_rx> PkTx <pkt_tx> RSSI <gs_rssi> SNR <gs_snr>
      AckRx <ack_rx> AckTx <ack_tx> RSSI <trk_rssi> SNR <trk_snr>
      SF <lora_sf> frq <frequency_hz> trk_B_V <battery_mv> [<relay_temp_c> C] CRC: XXXX

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
    DeviceType,
    FixType,
    GPSPacket,
    LinkPacket,
    PacketType,
    UnitType,
    UnknownPacket,
)

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

# Common header prefix shared by all @ lines:
#   @ <TYPE> <len> <year> <month> <date> <time> CRC_OK|CRC_ERR ...
#
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
            GPSPacket, LinkPacket, or UnknownPacket on success.
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

        # Known unimplemented types: TX_STAT FRST_FIX RX_TMOUT RLY_DIST
        # RX_FOUND RX_COORD RX_CRDFD GS_COORD COORDFND FS_CHNGE BATT_BLE
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


def _parse_time(s: str) -> float:
    """
    Convert the time token from a packet header to seconds (float).

    Formats observed in firmware:
      HH:MM:SS.mmm  — GPS_STAT with GPS lock (most common)
      MM:SS.s       — some packet types using internal clock
      SS.sss        — bare float seconds
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
