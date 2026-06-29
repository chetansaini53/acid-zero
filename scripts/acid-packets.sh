#!/bin/bash
# ACID Live Packets - short READ-ONLY capture on the monitor iface, parse 802.11 frame stats.
# Pure recon (no injection). Sniffs alongside pwnagotchi (monitor RX is shared) - non-disruptive.
# Usage: acid-packets.sh [seconds]   ; stats -> /tmp/acid_packets_stats
export PATH="/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
DUR=${1:-5}
OUT=/tmp/acid_packets_stats
RAW=/tmp/acid_packets_raw
echo "capturing" > /tmp/acid_packets_status
# find a monitor-mode iface (prefer wlan0mon = the ACM)
MON=""
for w in wlan0mon $(ls /sys/class/net 2>/dev/null | grep '^wlan'); do
  iw dev "$w" info 2>/dev/null | grep -q "type monitor" && { MON="$w"; break; }
done
if [ -z "$MON" ]; then echo "no monitor iface found" > "$OUT"; echo "done" > /tmp/acid_packets_status; echo PKT_DONE; exit 0; fi
timeout "$DUR" tcpdump -i "$MON" -nn -e -l >"$RAW" 2>/dev/null
total=$(wc -l < "$RAW" 2>/dev/null); [ -z "$total" ] && total=0
beacon=$(grep -c -i "beacon" "$RAW" 2>/dev/null)
probe=$(grep -c -i "probe request" "$RAW" 2>/dev/null)
deauth=$(grep -c -i "deauth" "$RAW" 2>/dev/null)
data=$(grep -c -iE "data" "$RAW" 2>/dev/null)
rate=$(( total / (DUR>0?DUR:1) ))
{
  echo "iface=$MON  total=$total  rate=${rate}/s"
  echo "beacon=$beacon  probe=$probe  deauth=$deauth  data=$data"
  echo "TOPMACS"
  grep -oE 'SA:[0-9a-f:]{17}' "$RAW" 2>/dev/null | sed 's/SA://' | sort | uniq -c | sort -rn | head -5
  echo "PROBES"
  grep -i "probe request" "$RAW" 2>/dev/null | grep -oE '\([^)]*\)' | sort | uniq -c | sort -rn | head -4
} > "$OUT"
echo "done" > /tmp/acid_packets_status
echo "PKT_DONE total=$total"
