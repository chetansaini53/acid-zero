#!/usr/bin/env python3
"""
Acid Zero - Web File Server control (start / stop / status).

Resolves an SSH-safe AP adapter via acid_wifiroles.resolve_ap() (refuses if only the SSH
radio exists - never strands SSH), mints EPHEMERAL AP + web creds and a self-signed TLS
cert into tmpfs /run/acid_fileap (0600, wiped on stop), and launches the WPA2 AP + HTTPS
root file manager (acid-fileap.sh -> acid-fileserver.py). Off-by-default; nothing persists
to the SD card. Own-lab use only - this grants root-equivalent remote access on purpose.
"""
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, '/usr/local/bin')
import acid_wifiroles  # noqa: E402

DIR = '/run/acid_fileap'
CREDS = DIR + '/creds.json'
STATUS = DIR + '/status.json'
STOP = DIR + '/stop'
PIDS = DIR + '/pids'
PORT = 8443
AP_PREFIX = 'AcidFS'
_PW = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'   # unambiguous (no 0/O/1/l/I)


def is_running():
    try:
        return any(os.path.exists('/proc/%s' % p) for p in open(PIDS).read().split())
    except Exception:
        return False


def status():
    try:
        with open(STATUS) as f:
            return json.load(f)
    except Exception:
        return {}


def creds():
    try:
        with open(CREDS) as f:
            return json.load(f)
    except Exception:
        return {}


def _write0600(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix='.fap')
    try:
        os.write(fd, data.encode('utf-8'))
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _uplink_ip():
    try:
        live = acid_wifiroles.active_uplink_iface()
        out = subprocess.run(['ip', '-o', '-4', 'addr', 'show'], capture_output=True,
                             text=True, timeout=3).stdout
        for ln in out.splitlines():
            p = ln.split()
            if len(p) >= 4 and p[1] == live:
                return p[3].split('/')[0]
    except Exception:
        pass
    return None


def _gen_cert():
    try:
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'ec',
                        '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes',
                        '-keyout', DIR + '/tls.key', '-out', DIR + '/tls.crt',
                        '-days', '1', '-subj', '/CN=acidzero-fileserver'],
                       capture_output=True, timeout=25)
        os.chmod(DIR + '/tls.key', 0o600)
        os.chmod(DIR + '/tls.crt', 0o600)
        return os.path.exists(DIR + '/tls.crt') and os.path.exists(DIR + '/tls.key')
    except Exception:
        return False


def start():
    """-> (ok, message). Refuses if no SSH-safe AP radio is free."""
    if is_running():
        return True, 'already running'
    iface, chip = acid_wifiroles.resolve_ap()
    if not iface:
        return False, 'no free AP radio (only the SSH adapter) - refused'
    os.makedirs(DIR, exist_ok=True)
    try: os.chmod(DIR, 0o700)
    except Exception: pass
    try: os.remove(STOP)
    except Exception: pass
    ssid = '%s-%s' % (AP_PREFIX, secrets.token_hex(2))
    psk = ''.join(secrets.choice(_PW) for _ in range(16))            # ~92 bits, hand-typeable off the TFT
    web_user = 'a' + secrets.token_hex(2)                            # kills root:* guessing
    web_pass = ''.join(secrets.choice(_PW) for _ in range(12))       # ~66 bits
    _write0600(CREDS, json.dumps({'ap_ssid': ssid, 'ap_psk': psk, 'web_user': web_user,
                                  'web_pass': web_pass, 'port': PORT, 'started': int(time.time())}))
    if not _gen_cert():
        return False, 'TLS cert generation failed (openssl missing?)'
    subprocess.Popen(['setsid', 'bash', '/usr/local/bin/acid-fileap.sh', iface, ssid, psk, '6'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    _write0600(STATUS, json.dumps({'iface': iface, 'chip': chip, 'ap_ip': '10.13.37.1',
                                   'home_ip': _uplink_ip(), 'port': PORT, 'started': int(time.time())}))
    return True, 'started on %s' % iface


def stop():
    try:
        with open(STOP, 'w') as f:              # the AP script's loop + EXIT trap tear down + wipe
            f.write('1')
        return True
    except Exception:
        return False
