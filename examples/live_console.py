"""
Live telemetry console — prints parsed packets as they arrive from the
Featherweight GPS Tracker V2 ground station over USB serial.

Usage:
    python live_console.py --port COM4
    python live_console.py --port /dev/ttyUSB0
    python live_console.py --port /dev/cu.usbserial-0001

Press Ctrl-C to stop.
"""

import argparse

from featherweight_telemetry import GPSTracker, GPSPacket, LinkPacket, UnknownPacket
from featherweight_telemetry.models import FixType


def format_gps(p: GPSPacket) -> str:
    fix = "3D" if p.fix_type == FixType.FIX_3D else ("2D" if p.fix_type == FixType.FIX_2D else "NO_FIX")
    return (
        f"GPS  {p.tracker_id:<12} "
        f"lat={p.latitude:+.5f} lon={p.longitude:+.5f} alt={p.altitude_ft:6d}ft  "
        f"vel={p.h_vel_fps:4d}fps hdg={p.heading_deg:4d}° vvel={p.v_vel_fps:+d}fps  "
        f"fix={fix} sats={p.sat_total}"
    )


def format_link(p: LinkPacket) -> str:
    return (
        f"LINK {p.tracker_id:<12} "
        f"GS RSSI={p.gs_rssi:4d}dBm SNR={p.gs_snr:+3d}dB  "
        f"TRK RSSI={p.trk_rssi:4d}dBm SNR={p.trk_snr:+3d}dB  "
        f"SF={p.lora_sf} frq={p.frequency_hz/1e6:.3f}MHz  "
        f"batt={p.battery_v:.2f}V  pkts rx/tx={p.pkt_rx}/{p.pkt_tx}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Featherweight GPS Tracker live console")
    ap.add_argument("--port", required=True, help="Serial port (e.g. COM4, /dev/ttyUSB0)")
    ap.add_argument("--baudrate", type=int, default=115200)
    args = ap.parse_args()

    print(f"Connecting to {args.port} at {args.baudrate} baud. Press Ctrl-C to stop.\n")
    tracker = GPSTracker(port=args.port, baudrate=args.baudrate)

    for packet in tracker.stream():
        if isinstance(packet, GPSPacket):
            print(format_gps(packet))
        elif isinstance(packet, LinkPacket):
            print(format_link(packet))
        elif isinstance(packet, UnknownPacket):
            print(f"UNKN {packet.raw_line[:80]}")


if __name__ == "__main__":
    main()
