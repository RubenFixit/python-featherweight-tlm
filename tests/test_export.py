"""Tests for export_csv and export_jsonl."""

import csv
import io
import json
from pathlib import Path

import pytest

from featherweight_telemetry import export_csv, export_jsonl
from featherweight_telemetry.exceptions import ExportError
from featherweight_telemetry.models import (
    BLRStatPacket,
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
# Shared sample packets
# ---------------------------------------------------------------------------

GPS_PKT = GPSPacket(
    raw_line="@ GPS_STAT 203 2020 11 15 01:20:21.986 CRC_OK TRK testTrk Alt 5655 lt 39.55612 ln -105.1032 Vel 0 -155 0 Fix 3 # 9 4 2 0",
    device_type=DeviceType.GPS_TRACKER_V2,
    packet_type=PacketType.GPS_STATUS,
    year=2020, month=11, date=15,
    uptime_s=4821.986,
    unit_type=UnitType.TRK,
    tracker_id="testTrk",
    altitude_ft=5655,
    latitude=39.55612,
    longitude=-105.1032,
    h_vel_fps=0, heading_deg=-155, v_vel_fps=0,
    fix_type=FixType.FIX_3D,
    sat_total=9, sat_24db=4, sat_32db=2, sat_40db=0,
)

LINK_PKT = LinkPacket(
    raw_line="@ RX_NOMTK ...",
    device_type=DeviceType.GPS_TRACKER_V2,
    packet_type=PacketType.LINK_STATUS,
    year=2020, month=6, date=17,
    uptime_s=3056.9,
    tracker_id="FthrWt04072",
    pkt_rx=143, pkt_tx=38,
    gs_rssi=-124, gs_snr=-20,
    ack_rx=0, ack_tx=0,
    trk_rssi=-50, trk_snr=0,
    lora_sf=11, frequency_hz=908_599_976,
    battery_mv=4102,
)

TX_PKT = TXStatPacket(
    raw_line="@ TX_STAT ...",
    device_type=DeviceType.GPS_TRACKER_V2,
    packet_type=PacketType.TX_STAT,
    year=2019, month=11, date=27,
    uptime_s=1009.8,
    apid="11",
    tx_duration_ms=371,
    lora_sf=12,
    frequency_hz=926_800_000,
)

BATT_PKT = BattBLEPacket(
    raw_line="@ BATT_BLE ...",
    device_type=DeviceType.GPS_TRACKER_V2,
    packet_type=PacketType.BATT_BLE,
    year=2020, month=5, date=17,
    uptime_s=0.176,
    battery_mv=4189,
    ble_connected=True,
    temperature_c=36,
)

EVENT_PKT = EventPacket(
    raw_line="@ FRST_FIX 50 2020 11 15 01:18:44.000 Fix acquired CRC: AAAA",
    device_type=DeviceType.GPS_TRACKER_V2,
    packet_type=PacketType.EVENT,
    event_name="FRST_FIX",
    year=2020, month=11, date=15,
    uptime_s=4724.0,
    payload="Fix acquired CRC: AAAA",
)

BLR_PKT = BLRStatPacket(
    raw_line="@ BLR_STAT 185 2026 5 12 01:23:45.678 HG: 12 -8 986 XYZ: 127 -83 9862 Bo: 9987 7204 bt: 4102 gy: 22 -15 31 ang: 52 127 vel: -45 AGL: 897 CRC: A1B2",
    device_type=DeviceType.BLUE_RAVEN,
    packet_type=PacketType.BLR_STAT,
    year=2026, month=5, date=12,
    uptime_s=5025.678,
    hg_accel_x=0.12, hg_accel_y=-0.08, hg_accel_z=9.86,
    accel_x=0.127, accel_y=-0.083, accel_z=9.862,
    baro_pres_atm=0.9987, baro_temp_f=72.04,
    battery_mv=4102,
    gyro_x=0.22, gyro_y=-0.15, gyro_z=0.31,
    tilt_deg=5.2, roll_deg=127.0,
    vert_vel_fps=-45, agl_ft=897,
)

UNKNOWN_PKT = UnknownPacket(
    raw_line="@ FOOBAR 99 2020 1 1 0.0 stuff CRC: 1234",
    device_type=DeviceType.GPS_TRACKER_V2,
    packet_type=PacketType.UNKNOWN,
)

ALL_PACKETS = [GPS_PKT, LINK_PKT, TX_PKT, BATT_PKT, EVENT_PKT, BLR_PKT, UNKNOWN_PKT]


# ---------------------------------------------------------------------------
# CSV — return value and header
# ---------------------------------------------------------------------------

class TestExportCsvBasics:
    def test_returns_row_count(self) -> None:
        buf = io.StringIO()
        assert export_csv([GPS_PKT, BLR_PKT], buf) == 2

    def test_returns_zero_for_empty_iterable(self) -> None:
        buf = io.StringIO()
        assert export_csv([], buf) == 0

    def test_header_row_present(self) -> None:
        buf = io.StringIO()
        export_csv([GPS_PKT], buf)
        buf.seek(0)
        reader = csv.DictReader(buf)
        assert reader.fieldnames is not None
        assert "packet_type" in reader.fieldnames
        assert "raw_line" in reader.fieldnames

    def test_empty_iterable_still_writes_header(self) -> None:
        buf = io.StringIO()
        export_csv([], buf)
        buf.seek(0)
        lines = buf.readlines()
        assert len(lines) == 1  # header only

    def test_all_packet_types_same_column_count(self) -> None:
        buf = io.StringIO()
        export_csv(ALL_PACKETS, buf)
        buf.seek(0)
        reader = csv.reader(buf)
        rows = list(reader)
        col_count = len(rows[0])
        for row in rows[1:]:
            assert len(row) == col_count


# ---------------------------------------------------------------------------
# CSV — field values
# ---------------------------------------------------------------------------

class TestExportCsvFields:
    def _parse_row(self, packet) -> dict:
        buf = io.StringIO()
        export_csv([packet], buf)
        buf.seek(0)
        return next(csv.DictReader(buf))

    def test_gps_packet_type_as_integer(self) -> None:
        row = self._parse_row(GPS_PKT)
        assert row["packet_type"] == str(int(PacketType.GPS_STATUS))

    def test_gps_device_type_as_integer(self) -> None:
        row = self._parse_row(GPS_PKT)
        assert row["device_type"] == str(int(DeviceType.GPS_TRACKER_V2))

    def test_gps_altitude(self) -> None:
        row = self._parse_row(GPS_PKT)
        assert row["altitude_ft"] == "5655"

    def test_gps_latitude(self) -> None:
        row = self._parse_row(GPS_PKT)
        assert abs(float(row["latitude"]) - 39.55612) < 1e-5

    def test_gps_tracker_id(self) -> None:
        row = self._parse_row(GPS_PKT)
        assert row["tracker_id"] == "testTrk"

    def test_gps_raw_line_preserved(self) -> None:
        row = self._parse_row(GPS_PKT)
        assert "GPS_STAT" in row["raw_line"]

    def test_blr_packet_type_as_integer(self) -> None:
        row = self._parse_row(BLR_PKT)
        assert row["packet_type"] == str(int(PacketType.BLR_STAT))

    def test_blr_agl_ft(self) -> None:
        row = self._parse_row(BLR_PKT)
        assert row["agl_ft"] == "897"

    def test_blr_hg_accel_x(self) -> None:
        row = self._parse_row(BLR_PKT)
        assert abs(float(row["hg_accel_x"]) - 0.12) < 1e-6

    def test_gps_fields_empty_in_blr_row(self) -> None:
        row = self._parse_row(BLR_PKT)
        assert row["altitude_ft"] == ""
        assert row["latitude"] == ""
        assert row["tracker_id"] == ""

    def test_blr_fields_empty_in_gps_row(self) -> None:
        row = self._parse_row(GPS_PKT)
        assert row["agl_ft"] == ""
        assert row["hg_accel_x"] == ""

    def test_fix_type_as_integer(self) -> None:
        row = self._parse_row(GPS_PKT)
        assert row["fix_type"] == str(int(FixType.FIX_3D))

    def test_unit_type_as_integer(self) -> None:
        row = self._parse_row(GPS_PKT)
        assert row["unit_type"] == str(int(UnitType.TRK))

    def test_unknown_packet_raw_line(self) -> None:
        row = self._parse_row(UNKNOWN_PKT)
        assert "FOOBAR" in row["raw_line"]


# ---------------------------------------------------------------------------
# CSV — output destinations
# ---------------------------------------------------------------------------

class TestExportCsvDestinations:
    def test_writes_to_file_path_string(self, tmp_path: Path) -> None:
        out = str(tmp_path / "out.csv")
        count = export_csv([GPS_PKT, BLR_PKT], out)
        assert count == 2
        with open(out, newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2

    def test_writes_to_path_object(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        export_csv([GPS_PKT], out)
        assert out.exists()

    def test_file_contains_correct_header(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        export_csv([GPS_PKT], out)
        with open(out, newline="") as f:
            reader = csv.DictReader(f)
            assert "packet_type" in (reader.fieldnames or [])

    def test_invalid_path_raises_export_error(self) -> None:
        with pytest.raises(ExportError):
            export_csv([GPS_PKT], "/nonexistent_directory_xyz/out.csv")

    def test_writes_to_text_stream(self) -> None:
        buf = io.StringIO()
        export_csv([GPS_PKT, BLR_PKT], buf)
        buf.seek(0)
        content = buf.read()
        assert "GPS_STAT" in content
        assert "BLR_STAT" in content


# ---------------------------------------------------------------------------
# JSONL — return value and structure
# ---------------------------------------------------------------------------

class TestExportJsonlBasics:
    def test_returns_line_count(self) -> None:
        buf = io.StringIO()
        assert export_jsonl([GPS_PKT, BLR_PKT], buf) == 2

    def test_returns_zero_for_empty_iterable(self) -> None:
        buf = io.StringIO()
        assert export_jsonl([], buf) == 0

    def test_empty_iterable_writes_nothing(self) -> None:
        buf = io.StringIO()
        export_jsonl([], buf)
        assert buf.getvalue() == ""

    def test_one_json_object_per_line(self) -> None:
        buf = io.StringIO()
        export_jsonl([GPS_PKT, BLR_PKT, UNKNOWN_PKT], buf)
        lines = buf.getvalue().strip().splitlines()
        assert len(lines) == 3
        for line in lines:
            json.loads(line)  # must not raise

    def test_all_packet_types_valid_json(self) -> None:
        buf = io.StringIO()
        export_jsonl(ALL_PACKETS, buf)
        for line in buf.getvalue().strip().splitlines():
            json.loads(line)


# ---------------------------------------------------------------------------
# JSONL — field values
# ---------------------------------------------------------------------------

class TestExportJsonlFields:
    def _parse_obj(self, packet) -> dict:
        buf = io.StringIO()
        export_jsonl([packet], buf)
        return json.loads(buf.getvalue())

    def test_gps_packet_type_as_integer(self) -> None:
        obj = self._parse_obj(GPS_PKT)
        assert obj["packet_type"] == int(PacketType.GPS_STATUS)

    def test_gps_device_type_as_integer(self) -> None:
        obj = self._parse_obj(GPS_PKT)
        assert obj["device_type"] == int(DeviceType.GPS_TRACKER_V2)

    def test_gps_altitude(self) -> None:
        obj = self._parse_obj(GPS_PKT)
        assert obj["altitude_ft"] == 5655

    def test_gps_latitude(self) -> None:
        obj = self._parse_obj(GPS_PKT)
        assert abs(obj["latitude"] - 39.55612) < 1e-5

    def test_gps_raw_line_included(self) -> None:
        obj = self._parse_obj(GPS_PKT)
        assert "GPS_STAT" in obj["raw_line"]

    def test_blr_packet_type_as_integer(self) -> None:
        obj = self._parse_obj(BLR_PKT)
        assert obj["packet_type"] == int(PacketType.BLR_STAT)

    def test_blr_agl_ft(self) -> None:
        obj = self._parse_obj(BLR_PKT)
        assert obj["agl_ft"] == 897

    def test_blr_baro_pres_atm(self) -> None:
        obj = self._parse_obj(BLR_PKT)
        assert abs(obj["baro_pres_atm"] - 0.9987) < 1e-6

    def test_blr_device_type_is_blue_raven(self) -> None:
        obj = self._parse_obj(BLR_PKT)
        assert obj["device_type"] == int(DeviceType.BLUE_RAVEN)

    def test_fix_type_as_integer(self) -> None:
        obj = self._parse_obj(GPS_PKT)
        assert obj["fix_type"] == int(FixType.FIX_3D)

    def test_batt_ble_connected_bool(self) -> None:
        obj = self._parse_obj(BATT_PKT)
        assert obj["ble_connected"] is True

    def test_event_packet_name_preserved(self) -> None:
        obj = self._parse_obj(EVENT_PKT)
        assert obj["event_name"] == "FRST_FIX"
        assert "Fix acquired" in obj["payload"]

    def test_unknown_packet_raw_line(self) -> None:
        obj = self._parse_obj(UNKNOWN_PKT)
        assert "FOOBAR" in obj["raw_line"]

    def test_jsonl_has_only_packet_fields_not_properties(self) -> None:
        obj = self._parse_obj(BLR_PKT)
        assert "battery_v" not in obj
        assert "baro_temp_c" not in obj


# ---------------------------------------------------------------------------
# JSONL — output destinations
# ---------------------------------------------------------------------------

class TestExportJsonlDestinations:
    def test_writes_to_file_path_string(self, tmp_path: Path) -> None:
        out = str(tmp_path / "out.jsonl")
        count = export_jsonl([GPS_PKT, BLR_PKT], out)
        assert count == 2
        with open(out) as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_writes_to_path_object(self, tmp_path: Path) -> None:
        out = tmp_path / "out.jsonl"
        export_jsonl([GPS_PKT], out)
        assert out.exists()

    def test_file_contains_valid_json(self, tmp_path: Path) -> None:
        out = tmp_path / "out.jsonl"
        export_jsonl([GPS_PKT, BLR_PKT], out)
        with open(out) as f:
            for line in f:
                json.loads(line)

    def test_invalid_path_raises_export_error(self) -> None:
        with pytest.raises(ExportError):
            export_jsonl([GPS_PKT], "/nonexistent_directory_xyz/out.jsonl")

    def test_writes_to_text_stream(self) -> None:
        buf = io.StringIO()
        export_jsonl([GPS_PKT, BLR_PKT], buf)
        buf.seek(0)
        content = buf.read()
        assert "GPS_STAT" in content
        assert "BLR_STAT" in content
