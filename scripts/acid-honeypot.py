#!/usr/bin/env python3
# Acid Zero - Honeypot Lab daemon (LOW-INTERACTION, DEFENSIVE).
#
# Fake SSH / HTTP / Telnet listeners that NEVER grant real access - they only present a
# banner, record who connects and what credentials / commands they try, and surface it
# live for the UI. A honeypot has zero legitimate users, so ANY hit is a scan / intrusion
# attempt -> near-zero false positives. OWN-NETWORK / AUTHORIZED monitoring only.
# See ETHICS.md.
#
# Writes:
#   /home/pi/acid_loot/honeypot.log   persistent JSONL of every hit
#   /tmp/acid_honeypot_status         live view the UI polls
#   /tmp/acid_honeypot.pid            pid so the UI can STOP it (SIGTERM)
import json
import os
import signal
import socket
import threading
import time
from collections import deque

LOOT_DIR = '/home/pi/acid_loot'
LOG = os.path.join(LOOT_DIR, 'honeypot.log')
STATUS = '/tmp/acid_honeypot_status'
PIDFILE = '/tmp/acid_honeypot.pid'
MAX_READ = 2048                      # per-connection byte cap (never trust the client)
SERVICES = [('ssh', 2222), ('http', 80), ('telnet', 23)]   # ssh keeps 2222 (22 = real mgmt sshd)

_lock = threading.Lock()
_recent = deque(maxlen=12)           # ring buffer of recent hits for the UI
_total = 0
_ips = set()
_run = True


def _log_hit(service, ip, port, detail):
    global _total
    detail = (detail or 'connect').replace('\n', ' ').replace('\r', ' ')[:80]
    rec = {'t': time.strftime('%Y-%m-%d %H:%M:%S'), 'ip': ip, 'port': port,
           'service': service, 'detail': detail}
    with _lock:
        _total += 1
        _ips.add(ip)
        _recent.appendleft((time.strftime('%H:%M:%S'), ip, service, detail))
        try:
            os.makedirs(LOOT_DIR, exist_ok=True)
            with open(LOG, 'a') as f:
                f.write(json.dumps(rec) + '\n')
        except Exception:
            pass
    _write_status()


def _write_status():
    with _lock:
        lines = ['RUNNING',
                 'listen ' + ' '.join('%s:%d' % (s, p) for s, p in SERVICES),
                 'total %d' % _total,
                 'uniq %d' % len(_ips),
                 'HITS']
        lines += ['%s %s %s %s' % (t, ip, svc, det) for t, ip, svc, det in _recent]
    try:
        open(STATUS, 'w').write('\n'.join(lines) + '\n')
    except Exception:
        pass


def _recv(conn, n=MAX_READ):
    try:
        conn.settimeout(8.0)
        return conn.recv(n)
    except Exception:
        return b''


def handle_ssh(conn, ip, port):
    detail = 'connect'
    try:
        conn.sendall(b'SSH-2.0-OpenSSH_8.4p1 Debian-5\r\n')
        data = _recv(conn)
        if data:
            detail = 'client: ' + data.decode('latin-1', 'replace').strip()
    except Exception:
        pass
    _log_hit('ssh', ip, port, detail)


def handle_telnet(conn, ip, port):
    user = pw = cmd = ''
    try:
        conn.sendall(b'\r\nUbuntu 22.04.3 LTS\r\nlogin: ')
        user = _recv(conn, 128).decode('latin-1', 'replace').strip()
        conn.sendall(b'Password: ')
        pw = _recv(conn, 128).decode('latin-1', 'replace').strip()
        conn.sendall(b'\r\nLast login: Mon from 10.0.0.2\r\n$ ')
        cmd = _recv(conn, 256).decode('latin-1', 'replace').strip()
    except Exception:
        pass
    _log_hit('telnet', ip, port, 'login %s/%s cmd:%s' % (user[:20], pw[:20], cmd[:24]))


def handle_http(conn, ip, port):
    detail = 'connect'
    try:
        req = _recv(conn).decode('latin-1', 'replace')
        line = req.split('\r\n', 1)[0][:60]
        cred = ''
        for h in req.split('\r\n'):
            if h.lower().startswith('authorization:'):
                cred = ' auth:' + h.split(':', 1)[1].strip()[:30]
        if '\r\n\r\n' in req:
            body_in = req.split('\r\n\r\n', 1)[1]
            low = body_in.lower()
            if 'password' in low or 'user' in low:
                cred += ' creds:' + body_in.strip()[:40]
        page = (b'<!doctype html><title>Router Admin</title>'
                b'<h3>Administration Login</h3>'
                b'<form method=post>User <input name=username> '
                b'Pass <input name=password type=password> '
                b'<button>Sign in</button></form>')
        resp = (b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n'
                b'Content-Length: ' + str(len(page)).encode() +
                b'\r\nConnection: close\r\n\r\n' + page)
        conn.sendall(resp)
        detail = (line + cred).strip()
    except Exception:
        pass
    _log_hit('http', ip, port, detail)


HANDLERS = {'ssh': handle_ssh, 'http': handle_http, 'telnet': handle_telnet}


def _safe(handler, conn, addr, service):
    try:
        handler(conn, addr[0], addr[1])
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def serve(service, port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', port))
        s.listen(16)
        s.settimeout(1.0)
    except Exception:
        return
    handler = HANDLERS[service]
    while _run:
        try:
            conn, addr = s.accept()
        except socket.timeout:
            continue
        except Exception:
            break
        threading.Thread(target=_safe, args=(handler, conn, addr, service), daemon=True).start()
    try:
        s.close()
    except Exception:
        pass


def _stop(*_a):
    global _run
    _run = False


def main():
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        os.makedirs(LOOT_DIR, exist_ok=True)
        open(PIDFILE, 'w').write(str(os.getpid()))
    except Exception:
        pass
    _write_status()
    for svc, port in SERVICES:
        threading.Thread(target=serve, args=(svc, port), daemon=True).start()
    while _run:
        time.sleep(1.0)
    try:
        open(STATUS, 'w').write('STOPPED\n')
        os.remove(PIDFILE)
    except Exception:
        pass


if __name__ == '__main__':
    main()
