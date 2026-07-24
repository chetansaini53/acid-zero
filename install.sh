#!/usr/bin/env bash
# Acid Zero one-command installer.
#
#   Flash a stock jayofelony pwnagotchi image (see INSTALL.md step 1), SSH in,
#   clone this repo, then from the repo root:  sudo ./install.sh
#
# Idempotent + re-run safe: it only adds config lines that are missing, apt is a
# no-op on already-installed packages, and re-running after `git pull` is the
# update path. For authorized, own-lab, educational use only (see ETHICS.md).
set -euo pipefail
trap 'printf "\n\033[31m✗ install failed at line %s\033[0m\n" "$LINENO" >&2' ERR

log()  { printf '\n\033[1;35m▸ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

# --- preconditions -----------------------------------------------------------
[ "$(id -u)" -eq 0 ] || { echo "Run as root:  sudo ./install.sh" >&2; exit 1; }

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"
for d in launcher scripts apps lib/acid-ble systemd; do
  [ -d "$d" ] || { echo "Missing $d/ — run this from the acid-zero repo root." >&2; exit 1; }
done
ok "repo root: $REPO"

# --- 1. display + touch overlay (idempotent, no duplicate lines) -------------
CFG=/boot/firmware/config.txt
[ -f "$CFG" ] || CFG=/boot/config.txt
[ -f "$CFG" ] || { echo "config.txt not found in /boot/firmware/ or /boot/" >&2; exit 1; }
log "Display overlay ($CFG)"
cfg_add() {  # $1 = ERE key to test for, $2 = full line to append if absent
  if grep -qE "$1" "$CFG"; then ok "present: $2"
  else printf '%s\n' "$2" >> "$CFG"; ok "added:   $2"; fi
}
cfg_add '^[[:space:]]*dtparam=spi=on'     'dtparam=spi=on'
cfg_add '^[[:space:]]*dtparam=i2c1=on'    'dtparam=i2c1=on'
cfg_add '^[[:space:]]*dtparam=i2c_arm=on' 'dtparam=i2c_arm=on'
cfg_add '^[[:space:]]*dtoverlay=spi0-2cs' 'dtoverlay=spi0-2cs'
cfg_add '^[[:space:]]*dtoverlay=piscreen' 'dtoverlay=piscreen,speed=16000000,rotate=270'

# --- 2. dependencies (apt) ---------------------------------------------------
log "Dependencies (apt)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || warn "apt update failed — continuing with the local cache"
apt-get install -y python3-pil python3-numpy python3-serial \
                   aircrack-ng hcxtools hostapd dnsmasq bluez
ok "apt packages installed"
# hostapd + dnsmasq install as always-on units (dnsmasq binds :53); Acid Zero's Evil
# Portal starts its own on demand, so stop the standing units to avoid a port/interface
# clash — they stay installed, just not auto-running.
systemctl disable --now dnsmasq hostapd 2>/dev/null || true
if /usr/bin/python3 -c 'import PIL, numpy' 2>/dev/null; then
  ok "PIL + numpy import OK under /usr/bin/python3"
else
  echo "PIL/numpy not importable under the system python3" >&2; exit 1
fi

# --- 3. deploy the files -----------------------------------------------------
log "Deploy launcher, scripts, libraries, plugins"
cp launcher/*.py /usr/local/bin/
cp scripts/*.sh scripts/*.py /usr/local/bin/
chmod +x /usr/local/bin/acidzero.py /usr/local/bin/acid-*.sh /usr/local/bin/acid-*.py
ok "launcher + scripts → /usr/local/bin"

mkdir -p /usr/local/lib/acid-ble
cp -r lib/acid-ble/* /usr/local/lib/acid-ble/
ok "BLE library → /usr/local/lib/acid-ble"

mkdir -p /usr/local/lib/acid-apps
cp -r apps/* /usr/local/lib/acid-apps/
find /usr/local/lib/acid-ble /usr/local/lib/acid-apps -name __pycache__ -type d -prune \
     -exec rm -rf {} + 2>/dev/null || true
# native-app executables must be runnable — real files only, never following a symlink
find /usr/local/lib/acid-apps -mindepth 2 -maxdepth 2 -type f ! -type l -exec chmod +x {} + 2>/dev/null || true
ok "plugins → /usr/local/lib/acid-apps (__pycache__ stripped)"

cp systemd/* /etc/systemd/system/
ok "systemd units → /etc/systemd/system"

# --- 4. co-processor Flasher support (optional; never fatal) ------------------
log "Co-processor Flasher support (optional)"
if /usr/bin/python3 -m esptool version >/dev/null 2>&1 \
   || command -v esptool >/dev/null 2>&1 || command -v esptool.py >/dev/null 2>&1; then
  ok "esptool present"
elif apt-get install -y esptool >/dev/null 2>&1; then
  ok "esptool installed (apt, signed repo)"
elif command -v pip3 >/dev/null 2>&1 \
     && python3 -m pip install --break-system-packages -q esptool >/dev/null 2>&1; then
  ok "esptool installed (pip fallback)"
else
  warn "esptool not installed — ESP32 flashing in the Flasher app is disabled"
  warn "  install it later: sudo apt install esptool"
fi
FW=/usr/local/share/acid-firmware
mkdir -p "$FW/pico-badusb"
bundle() {  # copy a firmware asset if present; never fatal (this whole section is optional)
  if [ ! -e "$1" ]; then warn "not in repo (skipped): $1"; return 0; fi
  if cp -r "$1" "$2"; then ok "bundled $(basename "$1")"; else warn "could not bundle $1"; fi
}
bundle firmware/esp32-allinone/prebuilt/esp32-allinone.merged.bin "$FW/"
bundle firmware/circuitpython/circuitpython-pico2w.uf2            "$FW/"
bundle firmware/pico-badusb/code.py                              "$FW/pico-badusb/"
bundle firmware/pico-badusb/boot.py                              "$FW/pico-badusb/"
bundle firmware/pico-badusb/lib                                  "$FW/pico-badusb/"

# --- 5. enable services ------------------------------------------------------
log "Enable services"
systemctl daemon-reload
systemctl enable --now acidzero.service
systemctl enable --now acid-hs-clean.timer
ok "acidzero.service + acid-hs-clean.timer enabled"

# --- 6. verify ---------------------------------------------------------------
log "Verify"
sleep 2
if systemctl is-active --quiet acidzero.service; then
  ok "acidzero.service is active"
else
  warn "acidzero.service is not active yet — inspect: journalctl -u acidzero.service -e"
fi

# --- done --------------------------------------------------------------------
# Decide on ACTUAL panel state, not just this run's edits: a previous run may have
# added the overlay and then aborted before the reboot ever happened.
panel_up() { grep -qil 'ili9486' /sys/class/graphics/fb*/name 2>/dev/null; }
if panel_up; then
  log "Done — the ILI9486 panel is up; the TFT should show the Acid Zero home screen."
else
  log "Display overlay is set but the panel isn't up yet → reboot to load it:  sudo reboot"
  echo "  (until the panel appears the UI service simply waits for it — expected, not a crash)"
fi
