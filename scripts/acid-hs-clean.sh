#!/bin/bash
# ACID handshake cleaner - validate pwnagotchi captures with hcxpcapngtool and quarantine
# the INVALID ones (no extractable WPA handshake AND no PMKID) so wpa-sec stops re-uploading
# dead files every cycle. Validation uses the SAME criteria wpa-sec accepts, so valid /
# crackable captures are kept untouched.
# Usage:  acid-hs-clean.sh           -> DRY RUN (report only, moves nothing)
#         acid-hs-clean.sh --apply   -> quarantine invalid -> /home/pi/handshakes_invalid/
export PATH="/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
HDIR=/home/pi/handshakes
QDIR=/home/pi/handshakes_invalid
APPLY=0; [ "$1" = "--apply" ] && APPLY=1
TMP=/tmp/hsval.22000
valid=0; invalid=0
shopt -s nullglob
[ "$APPLY" = 1 ] && mkdir -p "$QDIR"
NOW=$(date +%s)
for f in "$HDIR"/*.pcap "$HDIR"/*.cap; do
  [ -f "$f" ] || continue
  age=$(( NOW - $(stat -c %Y "$f" 2>/dev/null || echo "$NOW") ))
  [ "$age" -lt 180 ] && continue   # skip in-progress / very recent captures (<3 min)
  rm -f "$TMP"
  hcxpcapngtool -o "$TMP" "$f" >/dev/null 2>&1
  if [ -s "$TMP" ]; then
    valid=$((valid+1))
  else
    invalid=$((invalid+1))
    echo "INVALID: $(basename "$f")"
    [ "$APPLY" = 1 ] && mv "$f" "$QDIR/" 2>/dev/null
  fi
done
rm -f "$TMP"
echo "----------------------------------------"
echo "TOTAL valid=$valid  invalid=$invalid"
if [ "$APPLY" = 1 ]; then echo "QUARANTINED $invalid invalid -> $QDIR (reversible: mv back if needed)"; else echo "DRY RUN - nothing moved. Re-run with --apply to quarantine the invalid ones."; fi
echo "HSCLEAN_DONE"
