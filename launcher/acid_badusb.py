#!/usr/bin/env python3
"""
Acid Zero - BadUSB client (Pi side).

Sends a Flipper-compatible DuckyScript payload over WiFi to the Pico 2 W HID
injector (`acidducky.local:1337`, see firmware/pico-badusb/). The Pico is a USB
HID keyboard plugged into the TARGET; this module is the Pi-side transport the
launcher's Bad USB app imports. Mirrors acid_ir.py / acid_subghz.py in shape:
a small class, no printing from library code.

Scripts live in SCRIPTS_DIR as plain .txt DuckyScript files (drop your Flipper
BadUSB scripts straight in). Structure mirrors the IR app's saved-remotes folder.

AUTHORIZED USE ONLY - keystroke injection into machines you own / are authorized
to test. Educational / own-lab. See ../ETHICS.md.
"""
from __future__ import annotations

import glob
import os
import socket
from typing import Optional

HOST = 'acidducky.local'     # the Pico 2 W advertises this via mDNS
PORT = 1337                  # MUST match firmware/pico-badusb/code.py PORT
SCRIPTS_DIR = '/home/ella3/acid_badusb'    # drop Flipper .txt DuckyScripts here


class BadUSBError(RuntimeError):
    pass


class BadUSB:
    """Pi-side client for the Acid Zero Pico 2 W BadUSB HID injector."""

    def __init__(self, host: str = HOST, port: int = PORT):
        self._host = host
        self._port = port

    # ---------------- transport ----------------
    def _send(self, payload: str, timeout: float = 20.0, connect_timeout: float = 6.0) -> str:
        try:
            s = socket.create_connection((self._host, self._port), timeout=connect_timeout)
        except Exception as e:
            raise BadUSBError('cannot reach Pico at %s:%d (%s) - is it powered, on WiFi, plugged into the target?'
                              % (self._host, self._port, e))
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

    # ---------------- high-level API ----------------
    def ping(self) -> bool:
        """True if the Pico BadUSB server answers (on WiFi and reachable)."""
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

    # ---------------- scripts folder (Flipper .txt) ----------------
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
    bu = BadUSB()
    print('pinging Pico BadUSB...', flush=True)              # GUARD:EXEMPT - CLI self-test
    if not bu.ping():
        print('FAIL: Pico not reachable at %s:%d' % (HOST, PORT))   # GUARD:EXEMPT - CLI self-test
        raise SystemExit(1)
    print('OK - Pico BadUSB online')                        # GUARD:EXEMPT - CLI self-test
    if len(sys.argv) > 1:
        print(bu.run_script(sys.argv[1]))                   # GUARD:EXEMPT - CLI self-test
    else:
        print('scripts:', [n for _p, n in bu.list_scripts()])   # GUARD:EXEMPT - CLI self-test
