"""Tests for the BlueRaven parser (BLR_STAT and related packet types)."""

from featherweight_telemetry import BlueRavenParser
from featherweight_telemetry.models import (
    BLRStatPacket,
    DeviceType,
    PacketType,
    UnknownPacket,
)

# Representative BLR_STAT line built from Appendix A field descriptions.
# Wire format: HG values ×100, XYZ ×1000, Bo pressure ×10000, Bo temp ×100,
#              gy ×100, ang tilt ×10; all others already in natural units.
SAMPLE_BLR_STAT = (
    "@ BLR_STAT 185 2026 5 12 01:23:45.678 "
    "HG: 12 -8 986 "
    "XYZ: 127 -83 9862 "
    "Bo: 9987 7204 "
    "bt: 4102 "
    "gy: 22 -15 31 "
    "ang: 52 127 "
    "vel: -45 "
    "AGL: 897 "
    "CRC: A1B2"
)

# Pre-GPS-lock variant with bare-float time field.
SAMPLE_BLR_STAT_BARE_FLOAT = (
    "@ BLR_STAT 120 2026 5 12 0.200 "
    "HG: 0 0 1002 "
    "XYZ: 3 -2 9998 "
    "Bo: 10001 6800 "
    "bt: 4050 "
    "gy: 1 0 -1 "
    "ang: 3 0 "
    "vel: 0 "
    "AGL: 0 "
    "CRC: F0F0"
)

# Line with negative acceleration values (during boost/descent)
SAMPLE_BLR_STAT_NEGATIVE = (
    "@ BLR_STAT 185 2026 5 12 00:02:30.500 "
    "HG: -150 45 3200 "
    "XYZ: -1500 450 32000 "
    "Bo: 8765 6500 "
    "bt: 3900 "
    "gy: -1200 350 -88 "
    "ang: 450 -270 "
    "vel: 1250 "
    "AGL: 15000 "
    "CRC: 5678"
)

PARSER = BlueRavenParser()


# ---------------------------------------------------------------------------
# Discarded lines
# ---------------------------------------------------------------------------

class TestDiscardedLines:
    def test_none_returns_none(self) -> None:
        assert PARSER.parse_line(None) is None  # type: ignore[arg-type]

    def test_empty_string_returns_none(self) -> None:
        assert PARSER.parse_line("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert PARSER.parse_line("   \t\n") is None

    def test_non_at_line_discarded(self) -> None:
        assert PARSER.parse_line("Blue Raven firmware build Nov  7 2026") is None

    def test_non_at_status_discarded(self) -> None:
        assert PARSER.parse_line("  Connected.") is None


# ---------------------------------------------------------------------------
# Unknown packet (unrecognised @ type)
# ---------------------------------------------------------------------------

class TestUnknownPacket:
    def test_unrecognised_at_type_returns_unknown(self) -> None:
        pkt = PARSER.parse_line("@ UNKNOWN_BLR_TYPE 99 2026 5 12 01:23:46.000 some payload")
        assert isinstance(pkt, UnknownPacket)

    def test_unknown_device_type_is_blue_raven(self) -> None:
        pkt = PARSER.parse_line("@ FOOBAR 50 2026 1 1 0.0 stuff")
        assert isinstance(pkt, UnknownPacket)
        assert pkt.device_type == DeviceType.BLUE_RAVEN

    def test_unknown_preserves_raw_line(self) -> None:
        line = "@ FOOBAR 50 2026 1 1 0.0 stuff"
        pkt = PARSER.parse_line(line)
        assert isinstance(pkt, UnknownPacket)
        assert pkt.raw_line == line


# ---------------------------------------------------------------------------
# BLR_STAT — packet type and device identification
# ---------------------------------------------------------------------------

class TestBLRStatIdentification:
    def test_packet_type(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert pkt.packet_type == PacketType.BLR_STAT

    def test_device_type_is_blue_raven(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert pkt.device_type == DeviceType.BLUE_RAVEN

    def test_raw_line_preserved(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert pkt.raw_line == SAMPLE_BLR_STAT


# ---------------------------------------------------------------------------
# BLR_STAT — date and time fields
# ---------------------------------------------------------------------------

class TestBLRStatDateTime:
    def test_year(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert pkt.year == 2026

    def test_month(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert pkt.month == 5

    def test_date(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert pkt.date == 12

    def test_uptime_hhmmss(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        # 01:23:45.678 = 1*3600 + 23*60 + 45.678 = 5025.678 s
        assert abs(pkt.uptime_s - 5025.678) < 0.001

    def test_uptime_bare_float(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT_BARE_FLOAT)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.uptime_s - 0.200) < 0.001


# ---------------------------------------------------------------------------
# BLR_STAT — hi-G accelerometer (÷100 → Gs)
# ---------------------------------------------------------------------------

class TestBLRStatHiGAccel:
    def test_hg_accel_x(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.hg_accel_x - 0.12) < 1e-6

    def test_hg_accel_y(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.hg_accel_y - (-0.08)) < 1e-6

    def test_hg_accel_z(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.hg_accel_z - 9.86) < 1e-6

    def test_hg_negative_during_boost(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT_NEGATIVE)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.hg_accel_x - (-1.50)) < 1e-6
        assert abs(pkt.hg_accel_z - 32.0) < 1e-6


# ---------------------------------------------------------------------------
# BLR_STAT — low-G accelerometer (÷1000 → Gs)
# ---------------------------------------------------------------------------

class TestBLRStatLoGAccel:
    def test_accel_x(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.accel_x - 0.127) < 1e-6

    def test_accel_y(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.accel_y - (-0.083)) < 1e-6

    def test_accel_z(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.accel_z - 9.862) < 1e-6


# ---------------------------------------------------------------------------
# BLR_STAT — barometric sensor
# ---------------------------------------------------------------------------

class TestBLRStatBaro:
    def test_baro_pressure_atm(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        # 9987 / 10000 = 0.9987 atm (slightly below sea level)
        assert abs(pkt.baro_pres_atm - 0.9987) < 1e-6

    def test_baro_temp_f(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        # 7204 / 100 = 72.04 °F
        assert abs(pkt.baro_temp_f - 72.04) < 1e-4

    def test_baro_temp_c_property(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        # 72.04 °F → ~22.24 °C
        assert abs(pkt.baro_temp_c - (72.04 - 32) * 5 / 9) < 1e-3


# ---------------------------------------------------------------------------
# BLR_STAT — battery
# ---------------------------------------------------------------------------

class TestBLRStatBattery:
    def test_battery_mv(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert pkt.battery_mv == 4102

    def test_battery_v_property(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.battery_v - 4.102) < 1e-6


# ---------------------------------------------------------------------------
# BLR_STAT — gyroscope (÷100 → deg/sec)
# ---------------------------------------------------------------------------

class TestBLRStatGyro:
    def test_gyro_x(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.gyro_x - 0.22) < 1e-6

    def test_gyro_y(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.gyro_y - (-0.15)) < 1e-6

    def test_gyro_z(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.gyro_z - 0.31) < 1e-6

    def test_gyro_large_negative_during_flight(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT_NEGATIVE)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.gyro_x - (-12.0)) < 1e-6


# ---------------------------------------------------------------------------
# BLR_STAT — attitude (tilt ÷10 → deg; roll already in deg)
# ---------------------------------------------------------------------------

class TestBLRStatAttitude:
    def test_tilt_deg(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        # 52 / 10 = 5.2 degrees
        assert abs(pkt.tilt_deg - 5.2) < 1e-6

    def test_roll_deg(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.roll_deg - 127.0) < 1e-6

    def test_tilt_zero_upright(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT_BARE_FLOAT)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.tilt_deg - 0.3) < 1e-6

    def test_negative_roll(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT_NEGATIVE)
        assert isinstance(pkt, BLRStatPacket)
        assert abs(pkt.roll_deg - (-270.0)) < 1e-6


# ---------------------------------------------------------------------------
# BLR_STAT — flight data
# ---------------------------------------------------------------------------

class TestBLRStatFlight:
    def test_vert_vel_fps(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert pkt.vert_vel_fps == -45  # descending

    def test_agl_ft(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT)
        assert isinstance(pkt, BLRStatPacket)
        assert pkt.agl_ft == 897

    def test_zero_agl_on_pad(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT_BARE_FLOAT)
        assert isinstance(pkt, BLRStatPacket)
        assert pkt.agl_ft == 0

    def test_ascent_positive_vel(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT_NEGATIVE)
        assert isinstance(pkt, BLRStatPacket)
        assert pkt.vert_vel_fps == 1250  # climbing at 1250 fps
        assert pkt.agl_ft == 15000


# ---------------------------------------------------------------------------
# Trailing newline tolerance
# ---------------------------------------------------------------------------

class TestLineEndings:
    def test_trailing_lf_stripped(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT + "\n")
        assert isinstance(pkt, BLRStatPacket)

    def test_trailing_crlf_stripped(self) -> None:
        pkt = PARSER.parse_line(SAMPLE_BLR_STAT + "\r\n")
        assert isinstance(pkt, BLRStatPacket)
