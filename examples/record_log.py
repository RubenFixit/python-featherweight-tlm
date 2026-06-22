"""
Record raw serial lines from the GPS Tracker ground station to a log file.

Usage:
    python record_log.py --port COM4 --output flight.log
    python record_log.py --port /dev/ttyUSB0 --output flight.log --quiet

Press Ctrl-C to stop recording.

The log file can later be replayed or exported with replay_log.py / export_csv.py.
"""

import argparse

from featherweight_telemetry import record


def main() -> None:
    ap = argparse.ArgumentParser(description="Record GPS Tracker serial stream to file")
    ap.add_argument("--port", required=True, help="Serial port (e.g. COM4, /dev/ttyUSB0)")
    ap.add_argument("--output", required=True, help="Output log file path")
    ap.add_argument("--baudrate", type=int, default=115200)
    ap.add_argument("--quiet", action="store_true", help="Don't echo lines to stdout")
    args = ap.parse_args()

    print(f"Recording {args.port} → {args.output}. Press Ctrl-C to stop.")
    record(port=args.port, output=args.output, baudrate=args.baudrate, quiet=args.quiet)
    print(f"\nDone. Log saved to {args.output}")


if __name__ == "__main__":
    main()
