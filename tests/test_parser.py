"""
Tests for GPSTrackerParser.

Sample lines are drawn from:
  - The official Featherweight GPS Tracker User's Manual (Feb 2025, Appendix A)
  - The Rosetta project (real V2 ground station output, older firmware)

Lines marked # TODO need validation against real V2 hardware.
"""

import pytest

from featherweight_telemetry import GPSTrackerParser
from featherweight_telemetry.models import (
    BattBLEPacket,
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
# Shared sample lines
# ---------------------------------------------------------------------------

# From the official manual, Appendix A (positive lat without '+' sign)
MANUAL_GPS_STAT = (
    "@ GPS_STAT 203 2020 11 15 01:20:21.986 CRC_OK TRK secondTrk "
    "Alt 5655 lt 39.55612 ln -105.1032 Vel 0 -155 0 Fix 3 "
    "# 9 4 2 0 000_00_00 000_00_00 000_00_00 000_00_00 000_00_00 CRC: 6A1D"
)

# From the Rosetta project (older firmware — explicit '+', zero-padded, pre-GPS-lock)
ROSETTA_GPS_STAT = (
    "@ GPS_STAT 203 0000 00 00 00:37:53.145 CRC_OK  TRK FthrWt04072 "
    "Alt 002053 lt +35.34776 ln -117.80913 Vel +0000 +027 +0000 Fix 3 "
    "# 29 23 10  0"
)

# From the manual (CRC_ERR, relay packet with optional temperature)
MANUAL_RX_NOMTK = (
    "@ RX_NOMTK 202 2020 6 17 50:56.9 CRC_ERR Rx NomTrk RLY-19-Whip "
    "PkRx 143 PkTx  38 RSSI -124 SNR -20 AckRx 0 AckTx 0 "
    "RSSI -50 SNR  +0 SF 11 frq 908599976 trk_B_V 4102  -69 C CRC: EFD0"
)

# RX_NOMTK without optional temperature field
RX_NOMTK_NO_TEMP = (
    "@ RX_NOMTK 202 2020 6 17 50:56.9 CRC_OK Rx NomTrk FthrWt04072 "
    "PkRx 2242 PkTx 2715 RSSI -079 SNR +08 AckRx 2218 AckTx 2248 "
    "RSSI -099 SNR -10 SF 10 frq 919000000 trk_B_V 4098 CRC: EFD0"
)

# From the reference repo spec (firmware Nov 2019)
MANUAL_TX_STAT = (
    "@ TX_STAT 91 2019 11 27 00:16:49.800 Tx Apid 11 Tx dur: 371 msec. SF12 Freq 926800000 CRC: B4E3"
)

# From the reference repo spec (firmware May 2020)
MANUAL_BATT_BLE = (
    "@ BATT_BLE 68 2020 5 17 0.176433519 4189 BLE+ 36 degC CRC: 3176 6C19"
)

# TODO: Placeholder event lines — format not validated against real hardware.
PLACEHOLDER_FRST_FIX = "@ FRST_FIX 50 2020 11 15 01:18:44.000 Fix acquired CRC: AAAA"
PLACEHOLDER_RX_TMOUT = "@ RX_TMOUT 50 2020 11 15 01:19:00.000 No packet received CRC: BBBB"
PLACEHOLDER_FS_CHNGE = "@ FS_CHNGE 60 2020 11 15 01:19:30.000 SF9 Freq 915000000 CRC: CCCC"


@pytest.fixture
def parser() -> GPSTrackerParser:
    return GPSTrackerParser()


# ---------------------------------------------------------------------------
# Silently-discarded lines
# ---------------------------------------------------------------------------

class TestDiscardedLines:
    def test_none_input(self, parser: GPSTrackerParser) -> None:
        assert parser.parse_line(None) is None  # type: ignore[arg-type]

    def test_empty_string(self, parser: GPSTrackerParser) -> None:
        assert parser.parse_line("") is None

    def test_whitespace_only(self, parser: GPSTrackerParser) -> None:
        assert parser.parse_line("   \t  ") is None

    def test_binary_fwt_packet(self, parser: GPSTrackerParser) -> None:
        assert parser.parse_line("FWT\x00\x01\x02\x03") is None

    def test_non_at_info_line(self, parser: GPSTrackerParser) -> None:
        assert parser.parse_line("Build date and time +DT4 Nov 7 2020") is None

    def test_non_at_separator(self, parser: GPSTrackerParser) -> None:
        assert parser.parse_line("---") is None


# ---------------------------------------------------------------------------
# UnknownPacket — truly unrecognised @ lines
# ---------------------------------------------------------------------------

class TestUnknownPacket:
    def test_completely_unknown_type_returns_unknown(self, parser: GPSTrackerParser) -> None:
        line = "@ FOOBAR 99 2020 1 1 0.0 some payload CRC: 1234"
        result = parser.parse_line(line)
        assert isinstance(result, UnknownPacket)
        assert result.packet_type == PacketType.UNKNOWN

    def test_unknown_preserves_raw_line(self, parser: GPSTrackerParser) -> None:
        line = "@ FOOBAR 99 2020 1 1 0.0 something CRC: 1234"
        result = parser.parse_line(line)
        assert isinstance(result, UnknownPacket)
        assert "FOOBAR" in result.raw_line

    def test_truncated_tx_stat_is_unknown(self, parser: GPSTrackerParser) -> None:
        # TX_STAT missing Tx dur and Freq fields — falls through to Unknown
        line = "@ TX_STAT 91 2019 11 27 00:16:49.800 Tx Apid 11 SF12 CRC: B4E3"
        result = parser.parse_line(line)
        assert isinstance(result, UnknownPacket)


# ---------------------------------------------------------------------------
# GPS_STAT — manual example
# ---------------------------------------------------------------------------

class TestManualGPSStat:
    @pytest.fixture
    def packet(self, parser: GPSTrackerParser) -> GPSPacket:
        result = parser.parse_line(MANUAL_GPS_STAT)
        assert isinstance(result, GPSPacket)
        return result

    def test_packet_type(self, packet: GPSPacket) -> None:
        assert packet.packet_type == PacketType.GPS_STATUS

    def test_utc_date(self, packet: GPSPacket) -> None:
        assert packet.year == 2020
        assert packet.month == 11
        assert packet.date == 15

    def test_uptime_seconds(self, packet: GPSPacket) -> None:
        # 01:20:21.986 → 1*3600 + 20*60 + 21.986 = 4821.986
        assert abs(packet.uptime_s - 4821.986) < 0.001

    def test_unit_type_trk(self, packet: GPSPacket) -> None:
        assert packet.unit_type == UnitType.TRK

    def test_tracker_id(self, packet: GPSPacket) -> None:
        assert packet.tracker_id == "secondTrk"

    def test_altitude(self, packet: GPSPacket) -> None:
        assert packet.altitude_ft == 5655

    def test_latitude(self, packet: GPSPacket) -> None:
        assert abs(packet.latitude - 39.55612) < 1e-5

    def test_longitude(self, packet: GPSPacket) -> None:
        assert abs(packet.longitude - (-105.1032)) < 1e-5

    def test_horizontal_velocity(self, packet: GPSPacket) -> None:
        assert packet.h_vel_fps == 0

    def test_heading(self, packet: GPSPacket) -> None:
        # TODO: validate sign convention against real V2 hardware
        assert packet.heading_deg == -155

    def test_vertical_velocity(self, packet: GPSPacket) -> None:
        assert packet.v_vel_fps == 0

    def test_fix_type_3d(self, packet: GPSPacket) -> None:
        assert packet.fix_type == FixType.FIX_3D

    def test_satellite_counts(self, packet: GPSPacket) -> None:
        assert packet.sat_total == 9
        assert packet.sat_24db == 4
        assert packet.sat_32db == 2
        assert packet.sat_40db == 0

    def test_has_gps_lock(self, packet: GPSPacket) -> None:
        assert packet.has_gps_lock is True

    def test_raw_line_preserved(self, packet: GPSPacket) -> None:
        assert "GPS_STAT" in packet.raw_line


# ---------------------------------------------------------------------------
# GPS_STAT — Rosetta / older firmware
# ---------------------------------------------------------------------------

class TestRosettaGPSStat:
    @pytest.fixture
    def packet(self, parser: GPSTrackerParser) -> GPSPacket:
        result = parser.parse_line(ROSETTA_GPS_STAT)
        assert isinstance(result, GPSPacket)
        return result

    def test_pre_lock_date_is_zero(self, packet: GPSPacket) -> None:
        assert packet.year == 0
        assert packet.month == 0
        assert packet.date == 0

    def test_uptime_with_leading_zeros(self, packet: GPSPacket) -> None:
        # 00:37:53.145 → 37*60 + 53.145 = 2273.145
        assert abs(packet.uptime_s - 2273.145) < 0.001

    def test_zero_padded_altitude(self, packet: GPSPacket) -> None:
        assert packet.altitude_ft == 2053

    def test_positive_latitude_with_plus(self, packet: GPSPacket) -> None:
        assert abs(packet.latitude - 35.34776) < 1e-5

    def test_heading_with_plus(self, packet: GPSPacket) -> None:
        assert packet.heading_deg == 27

    def test_satellite_counts_with_extra_whitespace(self, packet: GPSPacket) -> None:
        assert packet.sat_total == 29
        assert packet.sat_24db == 23
        assert packet.sat_32db == 10
        assert packet.sat_40db == 0


# ---------------------------------------------------------------------------
# RX_NOMTK — manual example (CRC_ERR, relay, temperature present)
# ---------------------------------------------------------------------------

class TestManualRxNomtk:
    @pytest.fixture
    def packet(self, parser: GPSTrackerParser) -> LinkPacket:
        result = parser.parse_line(MANUAL_RX_NOMTK)
        assert isinstance(result, LinkPacket)
        return result

    def test_parsed_despite_crc_err(self, packet: LinkPacket) -> None:
        assert packet.packet_type == PacketType.LINK_STATUS

    def test_tracker_id_with_hyphens(self, packet: LinkPacket) -> None:
        assert packet.tracker_id == "RLY-19-Whip"

    def test_packet_counters(self, packet: LinkPacket) -> None:
        assert packet.pkt_rx == 143
        assert packet.pkt_tx == 38

    def test_gs_rssi_and_snr(self, packet: LinkPacket) -> None:
        assert packet.gs_rssi == -124
        assert packet.gs_snr == -20

    def test_ack_counters(self, packet: LinkPacket) -> None:
        assert packet.ack_rx == 0
        assert packet.ack_tx == 0

    def test_tracker_rssi_and_snr(self, packet: LinkPacket) -> None:
        assert packet.trk_rssi == -50
        assert packet.trk_snr == 0

    def test_lora_sf(self, packet: LinkPacket) -> None:
        assert packet.lora_sf == 11

    def test_frequency(self, packet: LinkPacket) -> None:
        assert packet.frequency_hz == 908_599_976

    def test_battery_mv(self, packet: LinkPacket) -> None:
        assert packet.battery_mv == 4102

    def test_battery_v_property(self, packet: LinkPacket) -> None:
        assert abs(packet.battery_v - 4.102) < 0.001

    def test_relay_temp(self, packet: LinkPacket) -> None:
        assert packet.relay_temp_c == -69


# ---------------------------------------------------------------------------
# RX_NOMTK — no optional temperature field
# ---------------------------------------------------------------------------

class TestRxNomtkNoTemp:
    def test_relay_temp_defaults_to_zero(self, parser: GPSTrackerParser) -> None:
        result = parser.parse_line(RX_NOMTK_NO_TEMP)
        assert isinstance(result, LinkPacket)
        assert result.relay_temp_c == 0


# ---------------------------------------------------------------------------
# TX_STAT
# ---------------------------------------------------------------------------

class TestTXStat:
    @pytest.fixture
    def packet(self, parser: GPSTrackerParser) -> TXStatPacket:
        result = parser.parse_line(MANUAL_TX_STAT)
        assert isinstance(result, TXStatPacket)
        return result

    def test_packet_type(self, packet: TXStatPacket) -> None:
        assert packet.packet_type == PacketType.TX_STAT

    def test_utc_date(self, packet: TXStatPacket) -> None:
        assert packet.year == 2019
        assert packet.month == 11
        assert packet.date == 27

    def test_uptime_seconds(self, packet: TXStatPacket) -> None:
        # 00:16:49.800 → 16*60 + 49.800 = 1009.800
        assert abs(packet.uptime_s - 1009.800) < 0.001

    def test_apid(self, packet: TXStatPacket) -> None:
        assert packet.apid == "11"

    def test_tx_duration(self, packet: TXStatPacket) -> None:
        assert packet.tx_duration_ms == 371

    def test_lora_sf(self, packet: TXStatPacket) -> None:
        assert packet.lora_sf == 12

    def test_frequency(self, packet: TXStatPacket) -> None:
        assert packet.frequency_hz == 926_800_000

    def test_raw_line_preserved(self, packet: TXStatPacket) -> None:
        assert "TX_STAT" in packet.raw_line


# ---------------------------------------------------------------------------
# BATT_BLE
# ---------------------------------------------------------------------------

class TestBattBLE:
    @pytest.fixture
    def packet(self, parser: GPSTrackerParser) -> BattBLEPacket:
        result = parser.parse_line(MANUAL_BATT_BLE)
        assert isinstance(result, BattBLEPacket)
        return result

    def test_packet_type(self, packet: BattBLEPacket) -> None:
        assert packet.packet_type == PacketType.BATT_BLE

    def test_utc_date(self, packet: BattBLEPacket) -> None:
        assert packet.year == 2020
        assert packet.month == 5
        assert packet.date == 17

    def test_uptime_bare_float(self, packet: BattBLEPacket) -> None:
        assert abs(packet.uptime_s - 0.176433519) < 1e-7

    def test_ground_station_battery_mv(self, packet: BattBLEPacket) -> None:
        assert packet.battery_mv == 4189

    def test_battery_v_property(self, packet: BattBLEPacket) -> None:
        assert abs(packet.battery_v - 4.189) < 0.001

    def test_ble_connected_true(self, packet: BattBLEPacket) -> None:
        assert packet.ble_connected is True

    def test_temperature(self, packet: BattBLEPacket) -> None:
        assert packet.temperature_c == 36

    def test_ble_disconnected(self, parser: GPSTrackerParser) -> None:
        line = "@ BATT_BLE 68 2020 5 17 1.5 3900 BLE- 35 degC CRC: AABB"
        result = parser.parse_line(line)
        assert isinstance(result, BattBLEPacket)
        assert result.ble_connected is False
        assert result.battery_mv == 3900

    def test_raw_line_preserved(self, packet: BattBLEPacket) -> None:
        assert "BATT_BLE" in packet.raw_line


# ---------------------------------------------------------------------------
# EventPacket — known types with header parsed, payload preserved
# ---------------------------------------------------------------------------

class TestEventPacket:
    def test_frst_fix_returns_event(self, parser: GPSTrackerParser) -> None:
        result = parser.parse_line(PLACEHOLDER_FRST_FIX)
        assert isinstance(result, EventPacket)
        assert result.packet_type == PacketType.EVENT

    def test_event_name_extracted(self, parser: GPSTrackerParser) -> None:
        result = parser.parse_line(PLACEHOLDER_FRST_FIX)
        assert isinstance(result, EventPacket)
        assert result.event_name == "FRST_FIX"

    def test_event_date_extracted(self, parser: GPSTrackerParser) -> None:
        result = parser.parse_line(PLACEHOLDER_FRST_FIX)
        assert isinstance(result, EventPacket)
        assert result.year == 2020
        assert result.month == 11
        assert result.date == 15

    def test_event_uptime_extracted(self, parser: GPSTrackerParser) -> None:
        # 01:18:44.000 → 1*3600 + 18*60 + 44.0 = 4724.0
        result = parser.parse_line(PLACEHOLDER_FRST_FIX)
        assert isinstance(result, EventPacket)
        assert abs(result.uptime_s - 4724.0) < 0.001

    def test_event_payload_preserved(self, parser: GPSTrackerParser) -> None:
        result = parser.parse_line(PLACEHOLDER_FRST_FIX)
        assert isinstance(result, EventPacket)
        assert "Fix acquired" in result.payload

    def test_rx_tmout_event(self, parser: GPSTrackerParser) -> None:
        result = parser.parse_line(PLACEHOLDER_RX_TMOUT)
        assert isinstance(result, EventPacket)
        assert result.event_name == "RX_TMOUT"

    def test_fs_chnge_event(self, parser: GPSTrackerParser) -> None:
        result = parser.parse_line(PLACEHOLDER_FS_CHNGE)
        assert isinstance(result, EventPacket)
        assert result.event_name == "FS_CHNGE"

    def test_all_nine_known_event_types_yield_event_packet(
        self, parser: GPSTrackerParser
    ) -> None:
        known_types = [
            "FRST_FIX", "RX_TMOUT", "RLY_DIST", "RX_FOUND",
            "RX_COORD", "RX_CRDFD", "GS_COORD", "COORDFND", "FS_CHNGE",
        ]
        for name in known_types:
            line = f"@ {name} 50 2020 1 1 0.0 payload CRC: 1234"
            result = parser.parse_line(line)
            assert isinstance(result, EventPacket), f"{name} should yield EventPacket"
            assert result.event_name == name


# ---------------------------------------------------------------------------
# Time parsing (tested via parse_line)
# ---------------------------------------------------------------------------

class TestTimeParsing:
    def test_hhmmss_format(self, parser: GPSTrackerParser) -> None:
        result = parser.parse_line(MANUAL_GPS_STAT)
        assert isinstance(result, GPSPacket)
        assert abs(result.uptime_s - 4821.986) < 0.001

    def test_mmss_format(self, parser: GPSTrackerParser) -> None:
        # 50:56.9 → 50*60 + 56.9 = 3056.9
        result = parser.parse_line(MANUAL_RX_NOMTK)
        assert isinstance(result, LinkPacket)
        assert abs(result.uptime_s - 3056.9) < 0.01

    def test_bare_float_format(self, parser: GPSTrackerParser) -> None:
        result = parser.parse_line(MANUAL_BATT_BLE)
        assert isinstance(result, BattBLEPacket)
        assert abs(result.uptime_s - 0.176433519) < 1e-7

    def test_trailing_newline_handled(self, parser: GPSTrackerParser) -> None:
        result = parser.parse_line(MANUAL_GPS_STAT + "\n")
        assert result is not None

    def test_crlf_handled(self, parser: GPSTrackerParser) -> None:
        result = parser.parse_line(MANUAL_GPS_STAT + "\r\n")
        assert result is not None
