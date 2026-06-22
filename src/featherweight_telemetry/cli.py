"""
featherweight-telemetry CLI.

Commands:
  ports   — list available serial ports
  live    — print live telemetry to stdout
  record  — record raw serial lines to a log file
  replay  — replay a log file through the parser
  export  — export a log file to CSV or JSON Lines
"""

from __future__ import annotations

import argparse
import sys


def _cmd_ports(_args: argparse.Namespace) -> None:
    from .serial_port import list_ports_detail

    ports = list_ports_detail()
    if not ports:
        print("No serial ports found.")
        return
    for p in ports:
        print(f"{p['device']:20s}  {p['description']}")


def _cmd_live(args: argparse.Namespace) -> None:
    from .gps_tracker import GPSTracker

    print(f"Connecting to {args.port} at {args.baudrate} baud. Press Ctrl-C to stop.")
    tracker = GPSTracker(port=args.port, baudrate=args.baudrate)
    for packet in tracker.stream():
        print(packet)


def _cmd_record(args: argparse.Namespace) -> None:
    from .record import record

    print(f"Recording {args.port} → {args.output}. Press Ctrl-C to stop.")
    record(port=args.port, output=args.output, baudrate=args.baudrate, quiet=args.quiet)
    print(f"\nLog saved to {args.output}")


def _cmd_replay(args: argparse.Namespace) -> None:
    from .replay import replay

    for packet in replay(args.log_file, realtime=args.realtime):
        print(packet)


def _cmd_export(args: argparse.Namespace) -> None:
    from .export import export_csv, export_jsonl
    from .replay import replay

    packets = list(replay(args.log_file))
    fmt = args.format.lower()
    out = args.output

    if fmt == "csv":
        n = export_csv(packets, out)
    elif fmt in ("jsonl", "json"):
        n = export_jsonl(packets, out)
    else:
        print(f"Unknown format '{fmt}'. Use csv or jsonl.", file=sys.stderr)
        sys.exit(1)

    print(f"Exported {n} packets to {out}")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="featherweight-telemetry",
        description="Featherweight Altimeters telemetry tool (v0.1, receive-only)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # ports
    sub.add_parser("ports", help="List available serial ports")

    # live
    live = sub.add_parser("live", help="Stream live telemetry to stdout")
    live.add_argument("--port", required=True, help="Serial port (e.g. COM4, /dev/ttyUSB0)")
    live.add_argument("--baudrate", type=int, default=115200, help="Baud rate (default 115200)")

    # record
    rec = sub.add_parser("record", help="Record raw serial lines to a log file")
    rec.add_argument("--port", required=True, help="Serial port")
    rec.add_argument("--output", required=True, help="Output log file path")
    rec.add_argument("--baudrate", type=int, default=115200, help="Baud rate (default 115200)")
    rec.add_argument("--quiet", action="store_true", help="Suppress echoing lines to stdout")

    # replay
    rep = sub.add_parser("replay", help="Replay a log file through the parser")
    rep.add_argument("log_file", help="Path to log file")
    rep.add_argument("--realtime", action="store_true", help="Replay at original speed")

    # export
    exp = sub.add_parser("export", help="Export a log file to CSV or JSON Lines")
    exp.add_argument("log_file", help="Path to log file")
    exp.add_argument("--format", default="csv", choices=["csv", "jsonl"], help="Output format")
    exp.add_argument("--output", required=True, help="Output file path")

    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    dispatch = {
        "ports": _cmd_ports,
        "live": _cmd_live,
        "record": _cmd_record,
        "replay": _cmd_replay,
        "export": _cmd_export,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
