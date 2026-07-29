#!/bin/bash
# ACID Web File Server - WPA2 AP bring-up for the on-device root file manager.
# Launched by acid_fileap.py, which has already written /run/acid_fileap/creds.json (0600)
# and the ephemeral TLS cert. This brings up hostapd (WPA2) + dnsmasq (DHCP only, NO DNS
# hijack), starts the HTTPS file server, then tears EVERYTHING down - AP down, creds+cert
# WIPED, iface left unmanaged (SSH-safe) - on stop, server death, or hostapd death.
#   args:  <apiface> <ssid> <psk> [channel]
#   stop:  touch /run/acid_fileap/stop
export PATH="/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
APIF="$1"; SSID="$2"; PSK="$3"; CH="${4:-6}"
GW=10.13.37.1
DIR=/run/acid_fileap
STOP="$DIR/stop"

[ -z "$APIF" ] && { echo "[fap] no AP iface given"; exit 1; }
SSHIF=$(ip -o route show default 2>/dev/null | awk '{print $5; exit}')
# refuse if the AP iface is the default-route uplink OR carries an established SSH (:22) session -
# gateway-less lab nets have no default route, so the route check alone would fail open on SSH.
ap_has_ssh() {
  local sip
  for sip in $(ss -tnH state established '( sport = :22 )' 2>/dev/null | awk '{print $3}' | sed 's/:[0-9]*$//' | sort -u); do
    ip -o -4 addr show dev "$1" 2>/dev/null | grep -qw "$sip" && return 0
  done
  return 1
}
if [ "$APIF" = "$SSHIF" ] || ap_has_ssh "$APIF"; then
  echo "[fap] REFUSE: AP iface carries the live SSH session"; exit 1
fi
rm -f "$STOP"

teardown() {
  echo "[fap] teardown $(date '+%H:%M:%S')"
  [ -f "$DIR/pids" ] && { read -ra _p < "$DIR/pids"; kill "${_p[@]}" 2>/dev/null; }
  pkill -f acid-fileserver.py 2>/dev/null
  ip addr flush dev "$APIF" 2>/dev/null; ip link set "$APIF" down 2>/dev/null
  nmcli dev set "$APIF" managed no 2>/dev/null      # keep unmanaged so NM never fights the SSH radio
  shred -u "$DIR/tls.key" 2>/dev/null
  rm -f "$DIR/creds.json" "$DIR/tls.crt" "$DIR/tls.key" "$DIR/pids" "$DIR/status.json" \
        "$DIR/hostapd.conf" "$DIR/dnsmasq.conf" /tmp/acid_active_radio 2>/dev/null
  echo "[fap] done - creds wiped, $APIF unmanaged, SSH safe"
}
trap teardown EXIT

nmcli dev set "$APIF" managed no 2>/dev/null; sleep 1
ip link set "$APIF" down 2>/dev/null; ip addr flush dev "$APIF" 2>/dev/null
ip link set "$APIF" up 2>/dev/null; ip addr add "$GW/24" dev "$APIF" 2>/dev/null

umask 077
cat > "$DIR/hostapd.conf" <<EOF
interface=$APIF
driver=nl80211
ssid=$SSID
hw_mode=g
channel=$CH
wmm_enabled=1
auth_algs=1
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
wpa_passphrase=$PSK
ignore_broadcast_ssid=0
EOF

cat > "$DIR/dnsmasq.conf" <<EOF
interface=$APIF
bind-interfaces
except-interface=lo
port=0
dhcp-range=10.13.37.50,10.13.37.150,255.255.255.0,12h
dhcp-option=3,$GW
EOF

hostapd "$DIR/hostapd.conf" >"$DIR/hostapd.log" 2>&1 & HPID=$!
sleep 3
if ! kill -0 $HPID 2>/dev/null; then
  echo "[fap] hostapd FAILED:"; tail -6 "$DIR/hostapd.log"; exit 1
fi
dnsmasq -C "$DIR/dnsmasq.conf" -d >"$DIR/dnsmasq.log" 2>&1 & DPID=$!
python3 /usr/local/bin/acid-fileserver.py >"$DIR/server.log" 2>&1 & WPID=$!
echo "$HPID $DPID $WPID" > "$DIR/pids"
echo "File Server AP: $APIF" > /tmp/acid_active_radio
echo "[fap] UP  hostapd=$HPID dnsmasq=$DPID server=$WPID  '$SSID' on $APIF @ $GW"

while [ ! -f "$STOP" ]; do
  sleep 2
  kill -0 $HPID 2>/dev/null || { echo "[fap] hostapd died"; break; }
  kill -0 $WPID 2>/dev/null || { echo "[fap] server exited (watchdog / fail-closed)"; break; }
done
# teardown runs via the EXIT trap
