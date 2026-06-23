"""Tests for replay and export functions."""

import csv
import io
import json
from pathlib import Path

import pytest

from featherweight_telemetry import export_csv, export_jsonl, replay, replay_raw
from featherweight_telemetry.exceptions import ReplayError
from featherweight_telemetry.models import GPSPacket, LinkPacket

SAMPLE_LOG = Path(__file__).parent / "data" / "sample_gps_tracker.log"


class TestReplay:
    def test_replay_yields_packets(self) -> None:
        packets = list(replay(SAMPLE_LOG))
        assert len(packets) > 0

    def test_replay_yields_gps_and_link_packets(self) -> None:
        packets = list(replay(SAMPLE_LOG))
        types = {type(p) for p in packets}
        assert GPSPacket in types
        assert LinkPacket in types

    def test_replay_yields_diverse_packet_types(self) -> None:
        from featherweight_telemetry.models import BattBLEPacket, EventPacket, TXStatPacket

        packets = list(replay(SAMPLE_LOG))
        types = {type(p) for p in packets}
        assert TXStatPacket in types
        assert BattBLEPacket in types
        assert EventPacket in types

    def test_replay_missing_file_raises(self) -> None:
        with pytest.raises(ReplayError):
            list(replay("/nonexistent/path/file.log"))

    def test_replay_raw_yields_all_lines(self) -> None:
        raw_lines = list(replay_raw(SAMPLE_LOG))
        assert len(raw_lines) > 0

    def test_replay_raw_includes_non_at_lines(self) -> None:
        raw_lines = list(replay_raw(SAMPLE_LOG))
        non_at = [ln for ln in raw_lines if not ln.startswith("@") and ln.strip()]
        assert len(non_at) >= 1  # "Build date and time..." line


class TestExportCSV:
    def test_csv_has_header(self) -> None:
        packets = list(replay(SAMPLE_LOG))
        buf = io.StringIO()
        export_csv(packets, buf)
        buf.seek(0)
        reader = csv.DictReader(buf)
        assert reader.fieldnames is not None
        assert "packet_type" in reader.fieldnames
        assert "latitude" in reader.fieldnames

    def test_csv_row_count_matches_packet_count(self) -> None:
        packets = list(replay(SAMPLE_LOG))
        buf = io.StringIO()
        n = export_csv(packets, buf)
        assert n == len(packets)
        buf.seek(0)
        rows = list(csv.DictReader(buf))
        assert len(rows) == len(packets)

    def test_csv_gps_values(self) -> None:
        packets = list(replay(SAMPLE_LOG))
        buf = io.StringIO()
        export_csv(packets, buf)
        buf.seek(0)
        rows = list(csv.DictReader(buf))
        gps_rows = [r for r in rows if r["packet_type"] == "1"]
        assert len(gps_rows) > 0
        first = gps_rows[0]
        assert first["tracker_id"] == "secondTrk"
        assert float(first["latitude"]) == pytest.approx(39.55612, abs=1e-4)

    def test_csv_to_file(self, tmp_path: Path) -> None:
        packets = list(replay(SAMPLE_LOG))
        out = tmp_path / "out.csv"
        n = export_csv(packets, out)
        assert n > 0
        assert out.exists()


class TestExportJSONL:
    def test_jsonl_line_count_matches(self) -> None:
        packets = list(replay(SAMPLE_LOG))
        buf = io.StringIO()
        n = export_jsonl(packets, buf)
        assert n == len(packets)
        buf.seek(0)
        lines = [json.loads(ln) for ln in buf if ln.strip()]
        assert len(lines) == len(packets)

    def test_jsonl_contains_raw_line(self) -> None:
        packets = list(replay(SAMPLE_LOG))
        buf = io.StringIO()
        export_jsonl(packets, buf)
        buf.seek(0)
        objs = [json.loads(ln) for ln in buf if ln.strip()]
        assert all("raw_line" in o for o in objs)

    def test_jsonl_gps_fields_present(self) -> None:
        packets = list(replay(SAMPLE_LOG))
        buf = io.StringIO()
        export_jsonl(packets, buf)
        buf.seek(0)
        gps_objs = [json.loads(ln) for ln in buf if ln.strip() and json.loads(ln).get("packet_type") == 1]
        assert len(gps_objs) > 0
        assert "latitude" in gps_objs[0]
        assert "longitude" in gps_objs[0]

    def test_jsonl_to_file(self, tmp_path: Path) -> None:
        packets = list(replay(SAMPLE_LOG))
        out = tmp_path / "out.jsonl"
        n = export_jsonl(packets, out)
        assert n > 0
        assert out.exists()
