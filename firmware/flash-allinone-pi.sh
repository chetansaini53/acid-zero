#!/usr/bin/env bash
# ============================================================
#  Acid Zero - flash the ESP32 All-in-One co-processor (Pi/Linux)
#  (CC1101 + IR merged onto one 38-pin board)
#  Usage:  ./flash-allinone-pi.sh [/dev/ttyUSB0]
#  (defaults to /dev/ttyUSB0 if no port is given)
# ============================================================
set -euo pipefail

PORT="${1:-/dev/ttyUSB0}"
DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$DIR/esp32-allinone/prebuilt/esp32-allinone.merged.bin"

if [ ! -f "$BIN" ]; then
  echo "ERROR: firmware image not found: $BIN" >&2
  exit 1
fi

echo "Flashing $BIN -> $PORT at 921600 baud ..."
esptool --chip esp32 -p "$PORT" -b 921600 write_flash 0x0 "$BIN" \
  || python3 -m esptool --chip esp32 -p "$PORT" -b 921600 write_flash 0x0 "$BIN"
