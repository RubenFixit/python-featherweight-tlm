"""
Replay a raw log file through the GPS Tracker parser.

The log file format is the same one produced by record.py: one raw line per
text line, UTF-8.  Replaying re-runs every line through the parser so you
can test parser changes against captured data without hardware.

Optional real-time mode (realtime=True) respects the timestamps embedded in
@ lines and inserts corresponding sleeps, simulating live data playback.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from pathlib import Path

from .exceptions import ReplayError
from .models import AnyPacket
from .parser import GPSTrackerParser


def replay(
    log_file: str | Path,
    realtime: bool = False,
) -> Generator[AnyPacket, None, None]:
    """
    Replay a raw log file, yielding parsed packets.

    Args:
        log_file: Path to the log file produced by ``record()``.
        realtime: If True, sleep between packets to match the original timing
                  using the ``uptime_s`` field embedded in each packet.
                  Falls back to no delay for lines that carry no timestamp.

    Yields:
        GPSPacket, LinkPacket, or UnknownPacket for each parseable line.

    Raises:
        ReplayError: If the log file cannot be opened.
    """
    path = Path(log_file)
    if not path.exists():
        raise ReplayError(f"Log file not found: {path}")

    parser = GPSTrackerParser()
    last_uptime: float | None = None

    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.rstrip("\r\n")
                packet = parser.parse_line(line)
                if packet is None:
                    continue

                if realtime:
                    current_uptime = getattr(packet, "uptime_s", None)
                    if current_uptime is not None and last_uptime is not None:
                        delta = current_uptime - last_uptime
                        if 0 < delta < 10:  # sanity cap: ignore rollovers / gaps
                            time.sleep(delta)
                    if current_uptime is not None:
                        last_uptime = current_uptime

                yield packet

    except OSError as exc:
        raise ReplayError(f"Cannot read log file {path}: {exc}") from exc


def replay_raw(log_file: str | Path) -> Generator[str, None, None]:
    """Yield raw text lines from a log file without parsing."""
    path = Path(log_file)
    if not path.exists():
        raise ReplayError(f"Log file not found: {path}")
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                yield line.rstrip("\r\n")
    except OSError as exc:
        raise ReplayError(f"Cannot read log file {path}: {exc}") from exc
