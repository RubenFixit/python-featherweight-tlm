"""
Record raw serial lines from a GPS Tracker ground station to a log file.

Log files store one raw line per text line, exactly as received from USB.
Raw logs are the preferred source of truth — they can be replayed and
re-parsed at any time without data loss, even as the parser evolves.

Log format:
  - UTF-8 text, one line per entry
  - Lines are written as-is (stripped of trailing CR/LF, then LF appended)
  - No timestamps are added by the recorder; the @ lines already carry them
"""

from __future__ import annotations

from pathlib import Path

from .serial_port import GPSTrackerSerial


def record(
    port: str,
    output: str | Path,
    baudrate: int = 115200,
    quiet: bool = False,
) -> None:
    """
    Record raw serial lines from *port* to *output* log file.

    Runs until Ctrl-C.  The log file is created (or appended to if it already
    exists) and flushed after every line so data is preserved on sudden exit.

    Args:
        port:      Serial port name (e.g. "COM4", "/dev/ttyUSB0").
        output:    Path to the output log file.
        baudrate:  Baud rate (default 115200).
        quiet:     If False, echo each line to stdout as it is recorded.

    Raises:
        SerialConnectionError: If the serial port cannot be opened.
    """
    output_path = Path(output)
    reader = GPSTrackerSerial(port=port, baudrate=baudrate)

    with open(output_path, "a", encoding="utf-8") as fh:
        for line in reader.stream_raw():
            fh.write(line + "\n")
            fh.flush()
            if not quiet:
                print(line, flush=True)
