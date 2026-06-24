"""
Parser for the Featherweight Blue Raven altimeter USB serial output.

The Blue Raven connects DIRECTLY to a computer via USB — it is an independent
device from the GPS Tracker V2 ground station.  Both use 115200 baud 8N1 but
on separate serial ports.

Input:  one text line (trailing newline already stripped, or not — both work).
Output: BLRStatPacket, EventPacket, UnknownPacket, or None.

None means the line is silently discarded:
  - blank / whitespace-only
  - non-@ lines (USB echo, prompts, etc.)

Protocol reference: Blue Raven User's Guide, May 2026, Appendix A.

Line formats:

  @ BLR_STAT <len> <year> <month> <date> <time>
      HG: <hg_x> <hg_y> <hg_z>
      XYZ: <xyz_x> <xyz_y> <xyz_z>
      Bo: <baro_pres> <baro_temp>
      bt: <battery_mv>
      gy: <gy_x> <gy_y> <gy_z>
      ang: <tilt> <roll>
      vel: <vert_vel>
      AGL: <agl_ft>
      CRC: XXXX

  @ LOG_LOW <len> <year> <month> <date> <hour> <minute> <second> ...
  @ LOG_HIR <len> <year> <month> <date> <hour> <minute> <second> ...
  @ SUMMARY <len> ...   (multi-line response to <download summary> command)

Wire format scaling (BLR_STAT only):
  HG  values:  raw integer / 100  → Gs
  XYZ values:  raw integer / 1000 → Gs
  Bo  pressure: raw integer / 10000 → atm
  Bo  temp:     raw integer / 100   → °F
  gy  values:  raw integer / 100  → deg/sec
  ang tilt:    raw integer / 10   → degrees
  ang roll:    raw integer (already degrees)
  vel:         raw integer (already ft/sec)
  AGL:         raw integer (already feet)
"""

from __future__ import annotations

import re

from .models import (
    AnyPacket,
    BLRStatPacket,
    DeviceType,
    EventPacket,
    PacketType,
    UnknownPacket,
)
from .parser import _parse_time  # reuse the shared time-parsing helper

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

# BLR_STAT capture groups:
#  1=year  2=month  3=date  4=time
#  5=hg_x_raw   6=hg_y_raw   7=hg_z_raw
#  8=xyz_x_raw  9=xyz_y_raw  10=xyz_z_raw
# 11=baro_pres_raw  12=baro_temp_raw
# 13=battery_mv
# 14=gy_x_raw  15=gy_y_raw  16=gy_z_raw
# 17=tilt_raw  18=roll_raw
# 19=vert_vel_fps
# 20=agl_ft
#
# No CRC_OK/CRC_ERR field — BLR_STAT is local USB data, not a LoRa-forwarded packet.
#
# Sample (constructed from Appendix A field descriptions):
#   @ BLR_STAT 185 2026 5 12 01:23:45.678 HG: 12 -8 986 XYZ: 127 -83 9862
#       Bo: 9987 7204 bt: 4102 gy: 22 -15 31 ang: 52 127 vel: -45 AGL: 897 CRC: A1B2
_BLR_STAT_RE = re.compile(
    r"""
    \A@ \s* BLR_STAT \s+ \S+ \s+                        # sync + type + packet-length
    (\d+) \s+ (\d+) \s+ (\d+) \s+                       # year  month  date
    ([\d:.eE+\-]+) \s+                                   # time (HH:MM:SS.mmm | bare float)
    HG: \s+ ([+-]?\d+) \s+ ([+-]?\d+) \s+ ([+-]?\d+) \s+   # hi-G accel X Y Z (Gs x100)
    XYZ: \s+ ([+-]?\d+) \s+ ([+-]?\d+) \s+ ([+-]?\d+) \s+  # low-G accel X Y Z (Gs x1000)
    Bo: \s+ ([+-]?\d+) \s+ ([+-]?\d+) \s+               # baro pressure (atm x10000), temp (°F x100)
    bt: \s+ (\d+) \s+                                    # battery, mV
    gy: \s+ ([+-]?\d+) \s+ ([+-]?\d+) \s+ ([+-]?\d+) \s+   # gyro X Y Z (deg/sec x100)
    ang: \s+ ([+-]?\d+) \s+ ([+-]?\d+) \s+              # tilt (deg x10), roll (deg)
    vel: \s+ ([+-]?\d+) \s+                              # vertical velocity, ft/sec
    AGL: \s+ ([+-]?\d+)                                  # altitude AGL from baro, ft
    """,
    re.VERBOSE,
)

# Generic event-header pattern (same structure as in parser.py, for BLR types
# that share the standard header layout).
_BLR_EVENT_HEADER_RE = re.compile(
    r"""
    \A@ \s* (\w+) \s+ \S+ \s+               # event type name + packet-length
    (\d+) \s+ (\d+) \s+ (\d+) \s+           # year  month  date
    ([\d:.eE+\-]+) \s*                       # time
    (.*)                                     # raw payload
    """,
    re.VERBOSE | re.DOTALL,
)

# Known Blue Raven packet types that use a parseable standard header.
# LOG_LOW and LOG_HIR use a different date/time layout (separate H M S fields)
# so they will not match _BLR_EVENT_HEADER_RE and fall through to UnknownPacket.
_KNOWN_BLR_EVENT_TYPES: frozenset[str] = frozenset({
    "LOG_LOW",   # low-rate recorded data download (header-parseable)
    "LOG_HIR",   # high-rate recorded data download (header-parseable)
})


# ---------------------------------------------------------------------------
# Public parser class
# ---------------------------------------------------------------------------


class BlueRavenParser:
    """
    Stateless line-oriented parser for the Featherweight Blue Raven altimeter
    USB serial stream.

    Usage::

        parser = BlueRavenParser()
        for raw_line in source:
            packet = parser.parse_line(raw_line)
            if packet is not None:
                process(packet)

    The parser never raises on malformed input — it returns UnknownPacket for
    unrecognised @ lines and None for silently-discarded lines.

    Fully parsed packet types:
      @ BLR_STAT → BLRStatPacket

    Header-only stubs (payload preserved in EventPacket.payload):
      @ LOG_LOW, @ LOG_HIR

    Not yet supported (returned as UnknownPacket):
      @ SUMMARY  (multi-line format; first line only is captured)
    """

    def parse_line(self, line: str) -> AnyPacket | None:
        """
        Parse one text line from the Blue Raven USB serial stream.

        Returns:
            BLRStatPacket, EventPacket, or UnknownPacket on a parseable @ line.
            None if the line should be silently discarded (blank, non-@).
        """
        if not line:
            return None

        stripped = line.strip()
        if not stripped:
            return None

        if not stripped.startswith("@"):
            return None

        m = _BLR_STAT_RE.match(stripped)
        if m:
            return self._parse_blr_stat(stripped, m)

        em = _BLR_EVENT_HEADER_RE.match(stripped)
        if em and em.group(1) in _KNOWN_BLR_EVENT_TYPES:
            return self._parse_event(stripped, em)

        return UnknownPacket(
            raw_line=stripped,
            device_type=DeviceType.BLUE_RAVEN,
            packet_type=PacketType.UNKNOWN,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_blr_stat(self, raw: str, m: re.Match) -> BLRStatPacket:  # type: ignore[type-arg]
        return BLRStatPacket(
            raw_line=raw,
            device_type=DeviceType.BLUE_RAVEN,
            packet_type=PacketType.BLR_STAT,
            year=int(m.group(1)),
            month=int(m.group(2)),
            date=int(m.group(3)),
            uptime_s=_parse_time(m.group(4)),
            hg_accel_x=int(m.group(5)) / 100.0,
            hg_accel_y=int(m.group(6)) / 100.0,
            hg_accel_z=int(m.group(7)) / 100.0,
            accel_x=int(m.group(8)) / 1000.0,
            accel_y=int(m.group(9)) / 1000.0,
            accel_z=int(m.group(10)) / 1000.0,
            baro_pres_atm=int(m.group(11)) / 10000.0,
            baro_temp_f=int(m.group(12)) / 100.0,
            battery_mv=int(m.group(13)),
            gyro_x=int(m.group(14)) / 100.0,
            gyro_y=int(m.group(15)) / 100.0,
            gyro_z=int(m.group(16)) / 100.0,
            tilt_deg=int(m.group(17)) / 10.0,
            roll_deg=float(m.group(18)),
            vert_vel_fps=int(m.group(19)),
            agl_ft=int(m.group(20)),
        )

    def _parse_event(self, raw: str, m: re.Match) -> EventPacket:  # type: ignore[type-arg]
        return EventPacket(
            raw_line=raw,
            device_type=DeviceType.BLUE_RAVEN,
            packet_type=PacketType.EVENT,
            event_name=m.group(1),
            year=int(m.group(2)),
            month=int(m.group(3)),
            date=int(m.group(4)),
            uptime_s=_parse_time(m.group(5)),
            payload=m.group(6).strip(),
        )
