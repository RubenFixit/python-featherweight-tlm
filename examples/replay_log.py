"""
Replay a recorded log file through the parser.

Usage:
    python replay_log.py flight.log
    python replay_log.py flight.log --realtime   # respect original timing
"""

import argparse

from featherweight_telemetry import replay, GPSPacket, LinkPacket, UnknownPacket


def main() -> None:
    ap = argparse.ArgumentParser(description="Replay a Featherweight GPS Tracker log file")
    ap.add_argument("log_file", help="Path to the log file")
    ap.add_argument("--realtime", action="store_true", help="Replay at original speed")
    args = ap.parse_args()

    count = 0
    for packet in replay(args.log_file, realtime=args.realtime):
        if isinstance(packet, GPSPacket):
            print(f"GPS  {packet.tracker_id} lat={packet.latitude:.5f} lon={packet.longitude:.5f} alt={packet.altitude_ft}ft")
        elif isinstance(packet, LinkPacket):
            print(f"LINK {packet.tracker_id} rssi={packet.gs_rssi}dBm batt={packet.battery_v:.2f}V")
        else:
            print(f"UNKN {packet.raw_line[:60]}")
        count += 1

    print(f"\nReplayed {count} packets from {args.log_file}")


if __name__ == "__main__":
    main()
