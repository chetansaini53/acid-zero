#!/usr/bin/env python3
"""
Acid Zero - BadUSB client + Pico-AP link manager (Pi side).

The Pico 2 W hosts its OWN WiFi access point (AP mode, see firmware/pico-badusb/):
    SSID  AcidZero-Duck  (WPA2)
    Pico  192.168.4.1:1337   (BadUSB DuckyScript server)

This module (a) joins that AP on a DEDICATED spare adapter (wlan2) via
NetworkManager - with a static IP and NO default route, so the Pi's real uplink
(wlan1) keeps SSH + internet untouched - and (b) sends Flipper-compatible
DuckyScript payloads to the Pico, which types them into the plugged-in TARGET.

Self-contained: needs no external WiFi, so it works ANYWHERE (home / field / a
client site) with no per-location credentials.

AUTHORIZED USE ONLY - keystroke injection into machines you own / are authorized
to test. Educational / own-lab. See ../ETHICS.md.
"""
from __future__ import annotations

import glob
import os
import socket
import subprocess
from typing import Tuple

try:
    import acid_wifiroles
except Exception:
    acid_wifiroles = None

# ---- Pico AP link (dedicated worker adapter, kept off the main SSH uplink) ----
AP_SSID = 'AcidZero-Duck'          # must match firmware AP_SSID
AP_PSK = 'acidzero1337'            # must match firmware AP_PASSWORD (WPA2, >= 8 chars)
AP_IFACE_FALLBACK = 'wlan2'        # used only if the role resolver is unavailable
AP_CONN = 'acidzero-duck'          # NetworkManager connection profile name
PI_ADDR = '192.168.4.2/24'         # static IP for the worker adapter on the Pico AP subnet


def _ap_iface() -> str:
    """The worker adapter for the 'badusb' role - resolved LIVE by chipset (see
    acid_wifiroles.py) so it follows whichever adapter is assigned/plugged in,
    never the SSH uplink. Falls back to the original hardcoded wlan2."""
    if acid_wifiroles is not None:
        try:
            iface, _chip = acid_wifiroles.resolve('badusb')
            if iface:
                return iface
        except Exception:
            pass
    return AP_IFACE_FALLBACK

HOST = '192.168.4.1'               # the Pico AP gateway = the Pico itself
PORT = 1337
SCRIPTS_DIR = '/home/ella3/acid_badusb'    # drop Flipper .txt DuckyScripts here


class BadUSBError(RuntimeError):
    pass


# ==================== Pico-AP link management (NetworkManager) ====================
def _nmcli(*args: str, timeout: float = 25.0) -> Tuple[int, str]:
    """Run nmcli (launcher is root; sudo -n fallback for non-root dev runs)."""
    base = ['nmcli'] if os.geteuid() == 0 else ['sudo', '-n', 'nmcli']
    try:
        p = subprocess.run(base + list(args), capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:
        return 1, str(e)


def ap_visible() -> bool:
    """True if the Pico's AP is currently broadcasting (seen on the worker iface)."""
    iface = _ap_iface()
    _nmcli('dev', 'set', iface, 'managed', 'yes')
    _nmcli('dev', 'wifi', 'rescan', 'ifname', iface)
    _rc, out = _nmcli('-t', '-f', 'SSID', 'dev', 'wifi', 'list', 'ifname', iface)
    return AP_SSID in [ln.strip() for ln in out.split('\n')]


def link_connect() -> Tuple[bool, str]:
    """Join the Pico AP on the dedicated worker adapter (static IP, no default route)."""
    iface = _ap_iface()
    _nmcli('dev', 'set', iface, 'managed', 'yes')
    if not ap_visible():
        return False, "'%s' not found - power the Pico, wait ~20s" % AP_SSID
    _nmcli('con', 'delete', AP_CONN)   # idempotent recreate
    rc, _out = _nmcli('con', 'add', 'type', 'wifi', 'con-name', AP_CONN, 'ifname', iface,
                      'ssid', AP_SSID, 'wifi-sec.key-mgmt', 'wpa-psk', 'wifi-sec.psk', AP_PSK,
                      'ipv4.method', 'manual', 'ipv4.addresses', PI_ADDR, 'ipv4.never-default', 'yes',
                      'ipv6.method', 'ignore', 'connection.autoconnect', 'no')
    if rc != 0:
        return False, 'profile add failed'
    rc, out = _nmcli('con', 'up', AP_CONN)
    if rc != 0:
        return False, 'connect failed: %s' % out.split('\n')[-1][:38]
    return True, 'connected'


def link_disconnect() -> Tuple[bool, str]:
    """Release the worker adapter (SSH always stays on the main uplink)."""
    _nmcli('con', 'down', AP_CONN)
    _nmcli('dev', 'set', _ap_iface(), 'managed', 'yes')   # ready for next connect / NM auto
    return True, 'disconnected'


def link_active() -> bool:
    """True if the worker adapter is currently connected to the Pico AP."""
    _rc, out = _nmcli('-t', '-f', 'GENERAL.CONNECTION', 'dev', 'show', _ap_iface())
    return AP_CONN in out


# ============================== BadUSB transport ==============================
class BadUSB:
    """Pi-side client for the Acid Zero Pico 2 W BadUSB HID injector (AP mode)."""

    def __init__(self, host: str = HOST, port: int = PORT):
        self._host = host
        self._port = port

    def _send(self, payload: str, timeout: float = 20.0, connect_timeout: float = 6.0) -> str:
        try:
            s = socket.create_connection((self._host, self._port), timeout=connect_timeout)
        except Exception as e:
            raise BadUSBError('cannot reach Pico at %s:%d (%s) - CONNECT to its AP first, '
                              'and plug it into the target' % (self._host, self._port, e))
        try:
            s.settimeout(timeout)
            s.sendall(payload.encode('utf-8', 'replace') + b'\x00')   # null = end of payload
            resp = b''
            while True:
                try:
                    chunk = s.recv(512)
                except socket.timeout:
                    break
                if not chunk:
                    break
                resp += chunk
                if b'\n' in resp:
                    break
            return resp.decode('utf-8', 'replace').strip()
        finally:
            try:
                s.close()
            except Exception:
                pass

    def ping(self) -> bool:
        """True if the Pico BadUSB server answers (link up and Pico reachable)."""
        try:
            return 'PONG' in self._send('PING', timeout=5.0, connect_timeout=4.0)
        except BadUSBError:
            return False

    def run_text(self, ducky: str) -> str:
        """Send a DuckyScript string to the Pico; it types it into the target."""
        if not ducky.strip():
            raise BadUSBError('empty payload')
        return self._send(ducky)

    def run_script(self, path: str) -> str:
        """Load a .txt DuckyScript file and run it on the target."""
        if not os.path.exists(path):
            raise BadUSBError('script not found: %s' % path)
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return self.run_text(f.read())

    @staticmethod
    def scripts_dir() -> str:
        os.makedirs(SCRIPTS_DIR, exist_ok=True)
        return SCRIPTS_DIR

    @staticmethod
    def list_scripts():
        """[(path, name), ...] of every .txt DuckyScript in SCRIPTS_DIR."""
        d = BadUSB.scripts_dir()
        return [(p, os.path.basename(p)[:-4]) for p in sorted(glob.glob(os.path.join(d, '*.txt')))]


if __name__ == '__main__':
    import sys
    arg = sys.argv[1] if len(sys.argv) > 1 else ''
    if arg == 'connect':
        ok, msg = link_connect()
        print('connect:', ok, msg)                          # GUARD:EXEMPT - CLI self-test
        raise SystemExit(0 if ok else 1)
    if arg == 'disconnect':
        ok, msg = link_disconnect()
        print('disconnect:', ok, msg)                       # GUARD:EXEMPT - CLI self-test
        raise SystemExit(0)
    bu = BadUSB()
    print('link active:', link_active())                    # GUARD:EXEMPT - CLI self-test
    print('pinging Pico @ %s:%d ...' % (HOST, PORT), flush=True)   # GUARD:EXEMPT - CLI self-test
    if bu.ping():
        print('ONLINE')                                     # GUARD:EXEMPT - CLI self-test
        if len(sys.argv) > 1:
            print(bu.run_script(sys.argv[1]))               # GUARD:EXEMPT - CLI self-test
    else:
        print('OFFLINE - run "acid_badusb.py connect" first')   # GUARD:EXEMPT - CLI self-test
