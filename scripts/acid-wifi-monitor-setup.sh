#!/usr/bin/env bash
# Acid Zero - WiFi monitor hygiene (idempotent; run once as root after flashing).
#
# On a Pi 3B+ the onboard BCM4345 "nexmon" radio CRASHES when driven to monitor-mode
# 5GHz channel-hopping (brcmf_fw_crashed): the capture interface dies and pwnagotchi
# sits "sad" catching nothing. Acid Zero therefore runs monitor on an EXTERNAL adapter
# and leaves the onboard free (e.g. for the BadUSB Pico link). This script makes that
# split clean and reboot-proof:
#
#   1. pwnlib start_monitor_interface(): prefer an external monitor adapter
#      (MT7612U/Alfa first, else RTL8821AU/Archer), set it to monitor DIRECTLY, point
#      bettercap's caplets + pwnagotchi main.iface at it, and never touch the onboard
#      nexmon or the live-SSH uplink. Built-in nexmon/wlan0mon stays as the fallback
#      only when no external adapter is present (so single-radio rigs still work).
#   2. NetworkManager: mark the monitor adapter unmanaged so NM never fights bettercap
#      for it across reboots.
#   3. wpa-sec plugin display fix: its on_ui_update() hardcodes the cracked-potfile at
#      /etc/pwnagotchi/handshakes/... while the download side writes to the configured
#      handshakes dir (usually /home/pi/handshakes) -> the on-screen password readout
#      shows "File not found". Symlink the former to the latter.
#
# Idempotent + backs up every file it edits. Does NOT configure your SSH uplink or any
# network credentials - assign SSH to its own adapter separately (see
# launcher/acid_wifiroles.py). After running: reboot, or `sudo monstart` to apply now.

[ "$(id -u)" -eq 0 ] || { echo "run as root: sudo $0" >&2; exit 1; }

PWNLIB=/usr/bin/pwnlib
CFG=/etc/pwnagotchi/config.toml
NMCONF=/etc/NetworkManager/conf.d/99-acidzero-unmanage-monitor.conf

# driver names that identify an external, monitor-capable adapter
is_monitor_driver() {
    case "$1" in
        mt76x2u|rtl8821au|rtl88XXau|8812au|88x2bu) return 0 ;;
        *) return 1 ;;
    esac
}

# the live default-route interface (the SSH uplink) - never to be touched
ssh_iface() {
    ip route get 1.1.1.1 2>/dev/null | grep -oE 'dev [a-z0-9]+' | awk '{print $2}'
}

# first external monitor adapter, skipping the SSH uplink (Alfa preferred over Archer)
monitor_iface() {
    local sshif w drv pick=""
    sshif=$(ssh_iface)
    for w in $(ls /sys/class/net 2>/dev/null | grep -E '^wlan' || true); do
        [ "$w" = "$sshif" ] && continue
        drv=$(basename "$(readlink -f /sys/class/net/$w/device/driver 2>/dev/null)" 2>/dev/null)
        if [ "$drv" = "mt76x2u" ]; then echo "$w"; return 0; fi
        if is_monitor_driver "$drv" && [ -z "$pick" ]; then pick="$w"; fi
    done
    [ -n "$pick" ] && echo "$pick"
}

# ---------- 1. patch pwnlib start_monitor_interface() ----------
if [ -f "$PWNLIB" ] && ! grep -q 'monitor source = external' "$PWNLIB"; then
    cp -n "$PWNLIB" "$PWNLIB.acidbak"
    python3 - "$PWNLIB" <<'PYEOF'
import re, sys
p = sys.argv[1]
s = open(p).read()
new = r'''start_monitor_interface() {
  # ACID: monitor = external adapter (MT7612U Alfa first, else RTL8821AU Archer). Set it
  # DIRECTLY to monitor and point bettercap caplets + main.iface at it. Never touch the
  # onboard nexmon or the live-SSH uplink. Built-in nexmon/wlan0mon is the no-external fallback.
  local EXT="" EXTDRV="" drv SSHIF
  SSHIF=$(ip route get 1.1.1.1 2>/dev/null | grep -oE 'dev [a-z0-9]+' | awk '{print $2}')
  local CAPS="/usr/local/share/bettercap/caplets/pwnagotchi-auto.cap /usr/local/share/bettercap/caplets/pwnagotchi-manual.cap"
  for w in $(ls /sys/class/net 2>/dev/null | grep -E '^wlan'); do
    [ "$w" = "$SSHIF" ] && continue
    drv=$(basename "$(readlink -f /sys/class/net/$w/device/driver 2>/dev/null)" 2>/dev/null)
    case "$drv" in
      mt76x2u) EXT=$w; EXTDRV=$drv; break ;;
      rtl8821au|rtl88XXau|8812au|88x2bu) if [ -z "$EXT" ]; then EXT=$w; EXTDRV=$drv; fi ;;
    esac
  done
  if [ -n "$EXT" ]; then
    nmcli dev set "$EXT" managed no 2>/dev/null
    rfkill unblock all
    ip link set "$EXT" down 2>/dev/null
    iw dev "$EXT" set type monitor 2>/dev/null
    ip link set "$EXT" up 2>/dev/null
    iw dev "$EXT" set power_save off 2>/dev/null
    for c in $CAPS; do sed -i "s/^set wifi.interface .*/set wifi.interface $EXT/" "$c" 2>/dev/null; done
    sed -i "s/^\( *main.iface *= *\).*/\1\"$EXT\"/" /etc/pwnagotchi/config.toml 2>/dev/null
    echo "[acid] monitor source = external $EXT ($EXTDRV) set monitor; caplets/main.iface -> $EXT (SSH=$SSHIF untouched)"
    return 0
  fi
  ifconfig wlan0 up
  sleep 3
  local MONPHY
  MONPHY=$(cat /sys/class/net/wlan0/phy80211/name 2>/dev/null)
  [ -z "$MONPHY" ] && MONPHY="$(iw phy | head -1 | cut -d' ' -f2)"
  iw dev wlan0mon del 2>/dev/null
  iw phy "$MONPHY" interface add wlan0mon type monitor
  sleep 2
  rfkill unblock all
  ifconfig wlan0 down 2>/dev/null
  ifconfig wlan0mon up
  iw dev wlan0mon set power_save off
  for c in $CAPS; do sed -i "s/^set wifi.interface .*/set wifi.interface wlan0mon/" "$c" 2>/dev/null; done
  sed -i "s/^\( *main.iface *= *\).*/\1\"wlan0mon\"/" /etc/pwnagotchi/config.toml 2>/dev/null
  echo "[acid] monitor source = built-in nexmon wlan0mon"
}'''
s2 = re.sub(r'start_monitor_interface\(\) \{.*?\n\}', lambda m: new, s, count=1, flags=re.S)
if s2 == s:
    sys.stderr.write("start_monitor_interface() not found - pwnlib not patched\n"); sys.exit(1)
open(p, 'w').write(s2)
PYEOF
    echo "[1/3] pwnlib start_monitor_interface() patched (backup: $PWNLIB.acidbak)"
else
    echo "[1/3] pwnlib already patched or absent - skipped"
fi

# ---------- 2. leave the monitor adapter unmanaged by NetworkManager ----------
MON=$(monitor_iface)
if [ -n "$MON" ]; then
    printf '[keyfile]\nunmanaged-devices=interface-name:%s\n' "$MON" > "$NMCONF"
    echo "[2/3] NetworkManager will leave $MON unmanaged ($NMCONF)"
else
    echo "[2/3] no external monitor adapter detected - NM conf skipped"
fi

# ---------- 3. wpa-sec password-display potfile symlink ----------
HS=$(grep -E '^[[:space:]]*handshakes[[:space:]]*=' "$CFG" 2>/dev/null | head -1 | sed -E 's/.*=[[:space:]]*"([^"]+)".*/\1/')
[ -z "$HS" ] && HS=/home/pi/handshakes
if [ ! -e /etc/pwnagotchi/handshakes ]; then
    ln -s "$HS" /etc/pwnagotchi/handshakes
    echo "[3/3] wpa-sec display symlink: /etc/pwnagotchi/handshakes -> $HS"
else
    echo "[3/3] /etc/pwnagotchi/handshakes already present - symlink skipped"
fi

echo "done. reboot, or run 'sudo monstart' to apply the monitor change now."
