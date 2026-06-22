# featherweight-telemetry

Python library for reading, parsing, recording, replaying, and exporting
telemetry from [Featherweight Altimeters](https://www.featherweightaltimeters.com/)
devices.

**v0.1 — Featherweight GPS Tracker V2 USB ground station, receive-only.**
No commands are sent to the device. This library never writes to the serial port.

---

## Supported devices

| Device | Status |
|--------|--------|
| Featherweight GPS Tracker V2 ground station (USB) | ✅ v0.1 |
| Blue Raven altimeter | 🔲 planned |
| GPS Tracker V1 | ❌ V1 USB is charge-only, no serial data |

---

## Install

```bash
pip install featherweight-telemetry
```

Requires Python 3.10+. The only runtime dependency is `pyserial`.

---

## Quick start — live telemetry

```python
from featherweight_telemetry import GPSTracker

tracker = GPSTracker(port="COM4")          # Windows
# tracker = GPSTracker(port="/dev/ttyUSB0")  # Linux
# tracker = GPSTracker(port="/dev/cu.usbserial-0001")  # macOS

for packet in tracker.stream():
    print(packet)
```

Press **Ctrl-C** to stop; the serial port is always closed cleanly.

---

## Parser-only usage (no serial port)

```python
from featherweight_telemetry import GPSTrackerParser

parser = GPSTrackerParser()

line = "@ GPS_STAT 203 2020 11 15 01:20:21.986 CRC_OK TRK myTracker Alt 5655 lt 39.55612 ln -105.1032 Vel 0 -155 0 Fix 3 # 9 4 2 0 CRC: 6A1D"
packet = parser.parse_line(line)

if packet is not None:
    print(packet)
```

`parse_line` returns:
- `GPSPacket` for `GPS_STAT` lines
- `LinkPacket` for `RX_NOMTK` lines
- `UnknownPacket` for any other `@`-prefixed line
- `None` for blank lines, binary `FWT` packets, and non-`@` lines

---

## Find your serial port

```python
from featherweight_telemetry import list_ports, list_ports_detail

print(list_ports())          # ['COM4'] or ['/dev/ttyUSB0']
print(list_ports_detail())   # includes description and hardware ID
```

CLI:
```bash
featherweight-telemetry ports
```

Typical port names:

| Platform | Port |
|----------|------|
| Windows  | `COM4` (Device Manager → Ports → CP2102 or CH340) |
| Linux    | `/dev/ttyUSB0` or `/dev/ttyACM0` |
| macOS    | `/dev/cu.usbserial-*` or `/dev/cu.SLAB_USBtoUART` |

---

## Recording

Save every raw serial line to a log file:

```python
from featherweight_telemetry import record

record(port="/dev/ttyUSB0", output="flight.log")
```

CLI:
```bash
featherweight-telemetry record --port /dev/ttyUSB0 --output flight.log
```

Log files are plain UTF-8 text (one line per entry) and are the preferred
source of truth — replay them as many times as needed.

---

## Replay

Replay a recorded log file through the parser:

```python
from featherweight_telemetry import replay

for packet in replay("flight.log"):
    print(packet)

# Replay at original speed (uses timestamps embedded in packets)
for packet in replay("flight.log", realtime=True):
    print(packet)
```

CLI:
```bash
featherweight-telemetry replay flight.log
featherweight-telemetry replay flight.log --realtime
```

---

## Export to CSV / JSON Lines

```python
from featherweight_telemetry import replay, export_csv, export_jsonl

packets = list(replay("flight.log"))

export_csv(packets, "flight.csv")
export_jsonl(packets, "flight.jsonl")
```

CLI:
```bash
featherweight-telemetry export flight.log --format csv    --output flight.csv
featherweight-telemetry export flight.log --format jsonl  --output flight.jsonl
```

---

## Data model

```python
from featherweight_telemetry import GPSPacket, LinkPacket, UnknownPacket
from featherweight_telemetry.models import FixType

packet = parser.parse_line(line)

if isinstance(packet, GPSPacket):
    print(packet.tracker_id)      # "myTracker"
    print(packet.latitude)        # 39.55612  (decimal degrees)
    print(packet.longitude)       # -105.1032
    print(packet.altitude_ft)     # 5655      (feet ASL)
    print(packet.h_vel_fps)       # horizontal velocity, ft/s
    print(packet.heading_deg)     # heading from North
    print(packet.v_vel_fps)       # vertical velocity, ft/s (up = positive)
    print(packet.fix_type)        # FixType.FIX_3D
    print(packet.sat_total)       # 9
    print(packet.has_gps_lock)    # True

elif isinstance(packet, LinkPacket):
    print(packet.gs_rssi)         # -87  (dBm)
    print(packet.gs_snr)          # +5   (dB)
    print(packet.trk_rssi)        # -92  (dBm)
    print(packet.lora_sf)         # 9    (spreading factor)
    print(packet.frequency_hz)    # 915000000
    print(packet.battery_mv)      # 3950 (millivolts)
    print(packet.battery_v)       # 3.95 (volts, computed property)
    print(packet.pkt_rx)          # packets received
    print(packet.relay_temp_c)    # 0 when not a relay packet
```

All packets carry `raw_line` (the original text) and `packet_type`.

---

## CLI reference

```
featherweight-telemetry ports
featherweight-telemetry live   --port COM4 [--baudrate 115200]
featherweight-telemetry record --port COM4 --output flight.log [--quiet]
featherweight-telemetry replay flight.log  [--realtime]
featherweight-telemetry export flight.log  --format csv --output flight.csv
featherweight-telemetry export flight.log  --format jsonl --output flight.jsonl
```

---

## Install for development

```bash
git clone https://github.com/rubenfixit/python-featherweight-tlm.git
cd python-featherweight-tlm
python -m pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check src/ tests/

# Type-check
mypy src/featherweight_telemetry/
```

---

## Safety note

**v0.1 is strictly receive-only.** The library never writes to the serial port.
There is no risk of accidentally transmitting RF signals to the tracker or
changing its configuration.

---

## Protocol notes

- Only **V2 ground stations** (sold from November 2020) have an active USB
  data port. The V1 micro-USB port is for charging only.
- Serial settings: **115200 baud, 8N1**, no flow control.
- Formatted telemetry lines start with `@`. Binary LoRa microcontroller
  packets start with `FWT` and are silently discarded.
- Two main packet types are parsed:
  - `GPS_STAT` → `GPSPacket` (position, velocity, satellites)
  - `RX_NOMTK` → `LinkPacket` (RF link quality, counters, battery)
- `CRC_ERR` lines are parsed normally — the parser does not discard them.
- The packet timestamp comes from the GPS module. `year`/`month`/`date` are
  `0` until the first GPS lock.

---

## TODO roadmap

- [ ] Validate parser against real Featherweight GPS Tracker V2 serial output
- [ ] Validate heading sign convention (manual shows -155°; expected 0–359)
- [ ] Parse per-satellite triplets (AAA_EE_SS format, Appendix A)
- [ ] Parse `BATT_BLE` packets (ground station battery + BLE state)
- [ ] Parse `TX_STAT` packets (per-transmission spreading factor and frequency)
- [ ] CRC-16/BUYPASS verification (optionally reject mismatched lines)
- [ ] Add Blue Raven altimeter support
- [ ] Map / KML / GeoJSON export
- [ ] Optional OpenC3/COSMOS adapter (see [openc3-cosmos-featherweight-gps](https://github.com/rubenfixit/openc3-cosmos-featherweight-gps))
- [ ] Optional live plotting dashboard

---

## License

Apache License 2.0 — Copyright 2026 Featherweight Telemetry Contributors.
