#!/usr/bin/env python3
"""Single source of truth for the Pico 2 W Bad USB access-point credentials.

The **Flasher** writes these onto the Pico (as `settings.toml`) AND saves them
here on a successful flash; the **Bad USB** app reads them here to CONNECT - so
whatever you flashed is exactly what CONNECT joins, with no re-typing. Either app
can edit them. Missing/broken store -> the public defaults.

Own-device / educational. The store lives in the user's home (root-owned, 0600);
it holds a WPA2 pre-shared key in plaintext, so it is never committed to the repo.
"""
import json
import os

PATH = '/home/ella3/.acid_ap.json'
DEFAULT_SSID = 'AcidZero-Duck'
DEFAULT_PSK = 'acidzero1337'


def validate(ssid, psk):
    """-> (ok, reason). Enforce the WPA2 constraints BEFORE flashing/saving so the
    Pico's AP and this store can never disagree or hold an unstartable password."""
    s = (ssid or '').strip()
    p = (psk or '').strip()
    if not s:
        return False, 'SSID cannot be empty'
    if len(s) > 32:
        return False, 'SSID too long (max 32)'
    if not (8 <= len(p) <= 63):
        return False, 'password must be 8-63 chars (WPA2)'
    # Reject anything that can break the double-quoted TOML string written to the
    # Pico (settings.toml) or nmcli terse parsing -> keeps the store, the Pico and
    # CONNECT from ever disagreeing. (Quotes/backslash are the reachable triggers.)
    for c in s + p:
        if ord(c) < 0x20 or ord(c) == 0x7f or c in '"\\':
            return False, 'no quotes, backslashes or control chars'
    return True, ''


def _clean_ssid(s):
    return (s or '').strip()[:32] or DEFAULT_SSID


def _clean_psk(p):
    p = (p or '').strip()
    # WPA2 PSK must be 8..63 chars; fall back to the default if out of range.
    return p if 8 <= len(p) <= 63 else DEFAULT_PSK


def load():
    """-> (ssid, psk). Always valid; defaults if the store is missing/corrupt."""
    try:
        with open(PATH) as f:
            d = json.load(f)
        return _clean_ssid(d.get('ssid')), _clean_psk(d.get('psk'))
    except Exception:
        return DEFAULT_SSID, DEFAULT_PSK


def save(ssid, psk):
    """Persist the AP creds (0600). -> True on success."""
    s, p = _clean_ssid(ssid), _clean_psk(psk)
    try:
        # Create 0600 atomically (no world-readable window under the default umask);
        # the plaintext WPA2 PSK never touches a loosely-permissioned file.
        fd = os.open(PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump({'ssid': s, 'psk': p}, f)
        try:
            os.chmod(PATH, 0o600)   # normalize a pre-existing loosened file
        except Exception:
            pass
        return True
    except Exception:
        return False
