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

# --- 1. display + touch overlay ----------------------------------------------
# Append any MISSING lines under a FRESH [all] block. A bare EOF append is WRONG:
# the stock jayofelony config.txt ends inside a per-model section ([pi5]), so lines
# added there never apply on a Pi 3B+ and the TFT stays blank. A new [all] header
# re-opens all-model scope regardless of the preceding section. Idempotent: a re-run
# finds every line already present and appends nothing.
CFG=/boot/firmware/config.txt
[ -f "$CFG" ] || CFG=/boot/config.txt
[ -f "$CFG" ] || { echo "config.txt not found in /boot/firmware/ or /boot/" >&2; exit 1; }
log "Display overlay ($CFG)"
NEED_LINE=('dtparam=spi=on' 'dtparam=i2c1=on' 'dtparam=i2c_arm=on' 'dtoverlay=spi0-2cs' 'dtoverlay=piscreen,speed=16000000,rotate=270')
NEED_KEY=('^[[:space:]]*dtparam=spi=on' '^[[:space:]]*dtparam=i2c1=on' '^[[:space:]]*dtparam=i2c_arm=on' '^[[:space:]]*dtoverlay=spi0-2cs' '^[[:space:]]*dtoverlay=piscreen')
missing=()
for i in "${!NEED_LINE[@]}"; do
  if grep -qE "${NEED_KEY[$i]}" "$CFG"; then ok "present: ${NEED_LINE[$i]}"
  else missing+=("${NEED_LINE[$i]}"); fi
done
if [ "${#missing[@]}" -gt 0 ]; then
  { echo ''; echo '# >>> Acid Zero display (install.sh) >>>'; echo '[all]'
    printf '%s\n' "${missing[@]}"; echo '# <<< Acid Zero display <<<'; } >> "$CFG"
  for m in "${missing[@]}"; do ok "added:   $m  [all]"; done
fi

# --- 2. dependencies (apt) ---------------------------------------------------
log "Dependencies (apt)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || warn "apt update failed — continuing with the local cache"
apt-get install -y python3-pil python3-numpy python3-serial python3-smbus i2c-tools \
                   python3-dbus python3-gi openssl libnfc-bin \
                   aircrack-ng hcxtools hostapd dnsmasq bluez
ok "apt packages installed"
# hostapd + dnsmasq install as always-on units (dnsmasq binds :53); Acid Zero's Evil
# Portal starts its own on demand, so stop the standing units to avoid a port/interface
# clash — they stay installed, just not auto-running.
systemctl disable --now dnsmasq hostapd 2>/dev/null || true
# The BLE HID media-remote needs bluetoothd's experimental D-Bus API (LEAdvertisingManager
# + secure HID characteristics). Enable it via a drop-in - harmless if you never use it.
BTD="$(command -v bluetoothd || true)"; [ -x "$BTD" ] || BTD=/usr/libexec/bluetooth/bluetoothd
[ -x "$BTD" ] || BTD=/usr/lib/bluetooth/bluetoothd
if [ -x "$BTD" ] && ! pgrep -f 'bluetoothd.*--experimental' >/dev/null 2>&1; then
  mkdir -p /etc/systemd/system/bluetooth.service.d
  printf '[Service]\nExecStart=\nExecStart=%s --experimental\n' "$BTD" \
    > /etc/systemd/system/bluetooth.service.d/acid-experimental.conf
  systemctl daemon-reload; systemctl restart bluetooth 2>/dev/null || true
  ok "bluetoothd --experimental enabled (for BLE HID remote)"
fi
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

# --- 4b. NFC/RFID reader (ACR122U) -------------------------------------------
# The ACS ACR122U is a PN532 USB reader libnfc drives natively (acr122_usb).
# libnfc-bin (installed above) gives read/dump/clone; two one-time fixes + an
# optional source-built emulator complete it. Entire section is never fatal.
log "NFC/RFID reader (ACR122U)"
# (a) The kernel's pn533/nfc modules grab the reader before libnfc can — blacklist
#     them so libnfc owns the ACR122U (takes effect on the next reboot).
NFC_BL=/etc/modprobe.d/blacklist-libnfc.conf
if grep -q '^blacklist pn533$' "$NFC_BL" 2>/dev/null; then
  ok "pn533/nfc kernel modules already blacklisted"
else
  printf 'blacklist pn533\nblacklist pn533_usb\nblacklist nfc\n' > "$NFC_BL"
  ok "blacklisted pn533/pn533_usb/nfc ($NFC_BL) — unbinds at next reboot"
fi
# (b) A stock /etc/nfc/libnfc.conf may pin a serial device (pn532_uart:/dev/ttyUSB0)
#     that errors first; comment it so libnfc autoscans and finds the USB ACR122U.
NFC_CONF=/etc/nfc/libnfc.conf
if [ -f "$NFC_CONF" ] && grep -qE '^[[:space:]]*device\.connstring' "$NFC_CONF"; then
  sed -i 's/^[[:space:]]*device\.connstring/# device.connstring/' "$NFC_CONF"
  ok "libnfc.conf: neutralized stray serial device (USB autoscan only)"
fi
# (c) EMULATE (present a saved UID for a Flipper to read) needs nfc-emulate-uid, a
#     libnfc *example* tool Debian doesn't package. Build it from the pinned,
#     sha256-verified upstream release against the system libnfc, using a minimal
#     toolchain (gcc + libc6-dev, not full build-essential). Optional + never fatal:
#     read/dump/clone all work without it and the NFC app degrades gracefully.
build_nfc_emulate() {
  if command -v nfc-emulate-uid >/dev/null 2>&1; then ok "nfc-emulate-uid already present"; return 0; fi
  local ver=1.8.0
  local sha=6d9ad31c86408711f0a60f05b1933101c7497683c2e0d8917d1611a3feba3dd5
  local url=https://github.com/nfc-tools/libnfc/releases/download/libnfc-$ver/libnfc-$ver.tar.bz2
  local tmp; tmp=$(mktemp -d) || return 0
  if ! apt-get install -y --no-install-recommends gcc libc6-dev libnfc-dev wget >/dev/null 2>&1; then
    warn "nfc-emulate-uid: build tools unavailable — EMULATE off (read/clone still work)"; rm -rf "$tmp"; return 0; fi
  if ! wget -qO "$tmp/s.tar.bz2" "$url"; then
    warn "nfc-emulate-uid: source download failed — EMULATE off"; rm -rf "$tmp"; return 0; fi
  if ! printf '%s  %s\n' "$sha" "$tmp/s.tar.bz2" | sha256sum -c - >/dev/null 2>&1; then
    warn "nfc-emulate-uid: sha256 mismatch — refusing to build"; rm -rf "$tmp"; return 0; fi
  # Patch in the -a ATQA / -s SAK options so emulation presents the real card's
  # protocol signature (else a Flipper sees the hardcoded Classic-1K default and
  # reports "multiple protocols"). Non-fatal: if the patch anchor is absent the
  # build simply falls to the warn branch below.
  if tar xjf "$tmp/s.tar.bz2" -C "$tmp" \
     && python3 "$REPO/patches/nfc-emulate-uid.py" "$tmp/libnfc-$ver/examples/nfc-emulate-uid.c" >/dev/null 2>&1 \
     && gcc -O2 -o "$tmp/nfc-emulate-uid" \
            "$tmp/libnfc-$ver/examples/nfc-emulate-uid.c" \
            "$tmp/libnfc-$ver/utils/nfc-utils.c" \
            -I"$tmp/libnfc-$ver" -I"$tmp/libnfc-$ver/utils" -lnfc >/dev/null 2>&1 \
     && install -m 0755 "$tmp/nfc-emulate-uid" /usr/local/bin/nfc-emulate-uid; then
    ok "built nfc-emulate-uid (UID + protocol emulation) → /usr/local/bin"
  else
    warn "nfc-emulate-uid: build failed — EMULATE off (read/clone still work)"
  fi
  rm -rf "$tmp"
}
build_nfc_emulate

# --- 5. enable services ------------------------------------------------------
log "Enable services"
systemctl daemon-reload
systemctl enable --now acidzero.service
systemctl enable --now acid-hs-clean.timer
systemctl enable --now acid-ups.service               # Waveshare UPS HAT (D) monitor + safe shutdown (harmless if no HAT)
# LAN clipboard bridge for the Terminal app (paste a command from the laptop). Mint a
# strong random token if none exists yet; the daemon also self-mints, this just lets
# us print it now for the laptop-side sync script.
if [ ! -s /etc/acid-clip.token ]; then
  # umask 077 -> the secret is 0600 from creation (never world-readable, even briefly)
  ( umask 077; /usr/bin/python3 -c "import os;open('/etc/acid-clip.token','w').write(os.urandom(18).hex())" )
fi
systemctl enable --now acid-clip.service
ok "acidzero + acid-hs-clean + acid-ups + acid-clip services enabled"
warn "clipboard token: read it yourself with  sudo cat /etc/acid-clip.token  then pass it to"
warn "  tools/acid-clip-sync.ps1 on your laptop. Keep it private - never commit it."

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
