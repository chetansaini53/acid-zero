#!/usr/bin/env bash
# ============================================================
#  Acid Zero - flash the ESP32 Sub-GHz co-processor (Pi/Linux)
#  Usage:  ./flash-pi.sh [/dev/ttyUSB0]
#  (defaults to /dev/ttyUSB0 if no port is given)
# ============================================================
set -euo pipefail

PORT="${1:-/dev/ttyUSB0}"
DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$DIR/esp32-cc1101/prebuilt/esp32-cc1101.merged.bin"

if [ ! -f "$BIN" ]; then
  echo "ERROR: firmware image not found: $BIN" >&2
  exit 1
fi

echo "Flashing $BIN -> $PORT at 921600 baud ..."
esptool --chip esp32 -p "$PORT" -b 921600 write_flash 0x0 "$BIN" \
  || python3 -m esptool --chip esp32 -p "$PORT" -b 921600 write_flash 0x0 "$BIN"
