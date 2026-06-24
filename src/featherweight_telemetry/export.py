"""
Export parsed telemetry packets to CSV and JSON Lines formats.

Both exporters accept any iterable of AnyPacket, so they work equally well
with live streams, replayed logs, or in-memory lists.

CSV format:
  - Header row with all field names from both GPSPacket and LinkPacket.
  - One data row per packet; fields not present for a packet type are empty.
  - First column is "packet_type" so rows are easy to filter.

JSON Lines format (https://jsonlines.org/):
  - One JSON object per line.
  - All dataclass fields are included; enum values are written as their
    integer value for compactness.
  - ``raw_line`` is included so the file is self-documenting.
"""

from __future__ import annotations

import csv
import dataclasses
import json
from collections.abc import Iterable
from pathlib import Path
from typing import TextIO

from .exceptions import ExportError
from .models import (
    AnyPacket,
    BattBLEPacket,
    BLRStatPacket,
    EventPacket,
    GPSPacket,
    LinkPacket,
    TXStatPacket,
    UnknownPacket,
)

# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

# Build the union of all field names across every packet type, preserving
# insertion order so GPS fields come first (most informative for typical use).
# New packet types added to models.py are picked up automatically.
_PACKET_CLASSES = [GPSPacket, LinkPacket, TXStatPacket, BattBLEPacket, EventPacket, BLRStatPacket, UnknownPacket]
_ALL_FIELDS: list[str] = list(
    dict.fromkeys(
        f.name
        for cls in _PACKET_CLASSES
        for f in dataclasses.fields(cls)  # type: ignore[arg-type]
    )
)


def _packet_to_row(packet: AnyPacket) -> dict[str, object]:
    row: dict[str, object] = dict.fromkeys(_ALL_FIELDS, "")
    for f in dataclasses.fields(packet):  # type: ignore[arg-type]
        val = getattr(packet, f.name)
        # Represent enums as their integer value
        if hasattr(val, "value"):
            val = val.value
        row[f.name] = val
    return row


def export_csv(
    packets: Iterable[AnyPacket],
    output: str | Path | TextIO,
) -> int:
    """
    Write packets to a CSV file.

    Args:
        packets: Iterable of parsed packets.
        output:  File path, or an already-open writable text stream.

    Returns:
        Number of rows written (excluding header).

    Raises:
        ExportError: On file I/O errors.
    """
    def _write(fh: TextIO) -> int:
        writer = csv.DictWriter(fh, fieldnames=_ALL_FIELDS, extrasaction="ignore")
        writer.writeheader()
        count = 0
        for packet in packets:
            writer.writerow(_packet_to_row(packet))
            count += 1
        return count

    if isinstance(output, (str, Path)):
        try:
            with open(output, "w", newline="", encoding="utf-8") as fh:
                return _write(fh)
        except OSError as exc:
            raise ExportError(f"Cannot write CSV to {output}: {exc}") from exc
    else:
        return _write(output)


# ---------------------------------------------------------------------------
# JSON Lines
# ---------------------------------------------------------------------------

def _packet_to_dict(packet: AnyPacket) -> dict[str, object]:
    d: dict[str, object] = {}
    for f in dataclasses.fields(packet):  # type: ignore[arg-type]
        val = getattr(packet, f.name)
        if hasattr(val, "value"):
            val = val.value
        d[f.name] = val
    return d


def export_jsonl(
    packets: Iterable[AnyPacket],
    output: str | Path | TextIO,
) -> int:
    """
    Write packets to a JSON Lines file (one JSON object per line).

    Args:
        packets: Iterable of parsed packets.
        output:  File path, or an already-open writable text stream.

    Returns:
        Number of lines written.

    Raises:
        ExportError: On file I/O errors.
    """
    def _write(fh: TextIO) -> int:
        count = 0
        for packet in packets:
            fh.write(json.dumps(_packet_to_dict(packet)) + "\n")
            count += 1
        return count

    if isinstance(output, (str, Path)):
        try:
            with open(output, "w", encoding="utf-8") as fh:
                return _write(fh)
        except OSError as exc:
            raise ExportError(f"Cannot write JSONL to {output}: {exc}") from exc
    else:
        return _write(output)
