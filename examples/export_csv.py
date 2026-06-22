"""
Export a recorded log file to CSV or JSON Lines.

Usage:
    python export_csv.py flight.log --format csv --output flight.csv
    python export_csv.py flight.log --format jsonl --output flight.jsonl
"""

import argparse
import sys

from featherweight_telemetry import replay, export_csv, export_jsonl


def main() -> None:
    ap = argparse.ArgumentParser(description="Export a GPS Tracker log file")
    ap.add_argument("log_file", help="Input log file")
    ap.add_argument("--format", choices=["csv", "jsonl"], default="csv", help="Output format")
    ap.add_argument("--output", required=True, help="Output file path")
    args = ap.parse_args()

    packets = list(replay(args.log_file))
    if not packets:
        print("No packets found in log file.", file=sys.stderr)
        sys.exit(1)

    if args.format == "csv":
        n = export_csv(packets, args.output)
    else:
        n = export_jsonl(packets, args.output)

    print(f"Exported {n} packets to {args.output} ({args.format.upper()})")


if __name__ == "__main__":
    main()
