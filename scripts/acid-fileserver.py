#!/usr/bin/env python3
"""
Acid Zero - HTTPS root file manager (the on-device Web File Server).

Serves a full-filesystem browse / download / upload / delete UI over ephemeral self-signed
TLS on 0.0.0.0:PORT, gated by the ephemeral creds in /run/acid_fileap/creds.json. This grants
root-equivalent remote access ON PURPOSE (owner tool) - so the whole design is fail-closed:

  * TLS only (a root-login cookie must never cross the LAN in cleartext).
  * Ephemeral random user+pass (shown on the TFT); constant-time compare, no user enumeration.
  * Layered brute-force defence: 0.75s per-attempt delay + per-IP backoff + a GLOBAL counter
    (defeats AP-subnet IP spoofing) + fail-CLOSED (50 total fails -> the whole service dies).
  * Server-side revocable sessions (HttpOnly; Secure; SameSite=Strict) with idle + absolute TTL.
  * CSRF header required on every mutating request.
  * Streamed up/download (no OOM on 1 GB RAM); atomic uploads; a delete denylist so one mis-tap
    can't brick the running Pi.
  * Inactivity + hard-lifetime watchdog -> auto teardown. Own-lab / educational use only.
"""
import hmac
import html
import http.server
import json
import os
import secrets
import shutil
import socketserver
import ssl
import tempfile
import threading
import time
import urllib.parse

DIR = '/run/acid_fileap'
CREDS = DIR + '/creds.json'
STOP = DIR + '/stop'
CERT = DIR + '/tls.crt'
KEY = DIR + '/tls.key'
PORT = 8443

MAX_UPLOAD = 2 * 1024 ** 3            # 2 GiB
SESS_IDLE = 600                       # session idle TTL (s)
SESS_MAX = 3600                       # session absolute cap (s)
INACTIVITY = 900                      # no authed request for this long -> teardown
HARD_LIFE = 7200                      # absolute service lifetime (s)
PROTECT = {'/', '/dev', '/proc', '/sys', '/boot', '/run', '/etc', '/bin', '/sbin',
           '/usr', '/lib', '/lib64', '/var', DIR}   # never DELETE these (or an ancestor of one)

_start = time.time()
_last_auth = time.time()
_sessions = {}                        # sid -> {created,last_seen,ip,csrf}
_gfails = []                          # global fail timestamps
_ipfails = {}                         # ip -> [timestamps]
_iplock = {}                          # ip -> (until_ts, level)
_total_fails = 0
_lock = threading.Lock()
_login_lock = threading.Lock()          # one login evaluated at a time (so the 0.75s throttle rate-limits)
_login_sem = threading.Semaphore(8)     # cap concurrent login handlers (thread-exhaustion guard)


def _creds():
    with open(CREDS) as f:
        return json.load(f)


def _die():
    try:
        open(STOP, 'w').write('1')     # signal the AP script's loop -> full teardown + wipe
    except Exception:
        pass
    os._exit(0)


def _ct(a, b):
    return hmac.compare_digest(str(a), str(b))


# ---------------- auth / brute-force ----------------
def _check_login(user, pw, ip):
    global _total_fails
    if not _login_sem.acquire(blocking=False):
        return 'locked'                       # too many concurrent logins -> shed (defeats a parallel burst)
    try:
        with _login_lock:                     # evaluate one at a time: the throttle + counters can't be raced
            now = time.time()
            with _lock:
                lk = _iplock.get(ip)
                if lk and now < lk[0]:
                    return 'locked'
                _gfails[:] = [t for t in _gfails if now - t < 60]
                if len(_gfails) >= 20:
                    return 'locked'
            try:
                c = _creds()
            except Exception:
                return 'fail'
            ok = bool(_ct(c.get('web_user', ''), user) & _ct(c.get('web_pass', ''), pw))  # both sides, no short-circuit
            time.sleep(0.75)                                                              # per-attempt throttle
            with _lock:
                if ok:
                    _ipfails.pop(ip, None); _iplock.pop(ip, None)
                    return 'ok'
                _total_fails += 1
                _gfails.append(now)
                f = _ipfails.setdefault(ip, [])
                f.append(now)
                f[:] = [t for t in f if now - t < 60]
                if len(f) >= 5:
                    lvl = _iplock.get(ip, (0, 0))[1] + 1
                    _iplock[ip] = (now + min(60 * (2 ** (lvl - 1)), 900), lvl)
                if _total_fails >= 50:
                    _die()                                                                # fail-closed
            return 'fail'
    finally:
        _login_sem.release()


def _new_session(ip):
    sid = secrets.token_urlsafe(24)
    with _lock:
        _sessions[sid] = {'created': time.time(), 'last_seen': time.time(),
                          'ip': ip, 'csrf': secrets.token_urlsafe(16)}
    return sid


def _session(sid):
    global _last_auth
    with _lock:
        s = _sessions.get(sid)
        if not s:
            return None
        now = time.time()
        if now - s['last_seen'] > SESS_IDLE or now - s['created'] > SESS_MAX:
            _sessions.pop(sid, None)
            return None
        s['last_seen'] = now
        _last_auth = now
        return s


# ---------------- path + fs helpers ----------------
def _clean(p):
    p = urllib.parse.unquote(p or '/')
    if '\x00' in p:
        return None
    p = os.path.normpath(p)
    return p if p.startswith('/') else '/' + p


def _human(n):
    for u in ('B', 'K', 'M', 'G', 'T'):
        if n < 1024 or u == 'T':
            return '%.0f%s' % (n, u) if u == 'B' else '%.1f%s' % (n, u)
        n /= 1024.0


def _listing(path):
    rows = []
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    isdir = e.is_dir(follow_symlinks=False)
                    sz = 0 if isdir else e.stat(follow_symlinks=False).st_size
                except Exception:
                    isdir, sz = False, 0
                rows.append((e.name, isdir, sz))
    except Exception as ex:
        return None, str(ex)
    rows.sort(key=lambda x: (not x[1], x[0].lower()))
    return rows, None


# ---------------- HTML ----------------
CSS = ('body{margin:0;font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:#0f141b;color:#e6edf6}'
       '.wrap{max-width:900px;margin:0 auto;padding:16px}'
       'a{color:#7cc0ff;text-decoration:none}a:hover{text-decoration:underline}'
       '.bar{background:#161d27;border:1px solid #2a3543;border-radius:10px;padding:10px 14px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center}'
       'table{width:100%;border-collapse:collapse;background:#131a23;border:1px solid #2a3543;border-radius:10px;overflow:hidden}'
       'th,td{padding:8px 12px;text-align:left;border-bottom:1px solid #202a36;font-size:13px}'
       'th{background:#182029;color:#8aa0b8;text-transform:uppercase;font-size:11px}'
       'tr:last-child td{border-bottom:0}.d{color:#ffd479}.sz{color:#8aa0b8;text-align:right}'
       '.btn{background:#233040;border:1px solid #33465a;color:#cfe2f5;border-radius:6px;padding:3px 9px;cursor:pointer;font-size:12px}'
       '.del{background:#3a2226;border-color:#5a2f36;color:#ffb3b3}'
       'input[type=file]{color:#8aa0b8}.warn{color:#ff9a9a;font-size:12px}'
       '.login{max-width:320px;margin:80px auto}.login input{width:100%;padding:9px;margin:6px 0;background:#0c1119;border:1px solid #2a3543;border-radius:7px;color:#e6edf6;box-sizing:border-box}'
       '.login button{width:100%;padding:10px;background:#1f6feb;border:0;border-radius:7px;color:#fff;font-weight:600;cursor:pointer}')


def _login_page(msg=''):
    m = '<p class="warn">%s</p>' % html.escape(msg) if msg else ''
    return ('<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">'
            '<title>Acid Zero File Server</title><style>%s</style><div class=login>'
            '<h2>Acid Zero &middot; File Server</h2><p class=warn>root filesystem access &mdash; own device only</p>'
            '%s<form method=post action=/login>'
            '<input name=user placeholder=user autocomplete=off autofocus>'
            '<input name=pass type=password placeholder=password autocomplete=off>'
            '<button>Log in</button></form>'
            '<p style="color:#5f7186;font-size:11px;margin-top:14px">creds shown on the device screen &middot; ephemeral</p>'
            '</div>') % (CSS, m)


def _browse_page(path, rows, csrf):
    parts = [p for p in path.split('/') if p]
    crumb = '<a href="/b?p=/">/</a>'
    acc = ''
    for p in parts:
        acc += '/' + p
        crumb += ' <a href="/b?p=%s">%s</a>' % (urllib.parse.quote(acc), html.escape(p))
    up = os.path.dirname(path.rstrip('/')) or '/'
    body = ''
    for name, isdir, sz in rows:
        full = urllib.parse.quote((path.rstrip('/') + '/' + name))
        en = html.escape(name)
        if isdir:
            body += ('<tr><td>&#128193; <a href="/b?p=%s">%s/</a></td><td class=sz></td>'
                     '<td><button class="btn del" onclick="del(\'%s\')">delete</button></td></tr>' % (full, en, full))
        else:
            body += ('<tr><td>&#128196; %s</td><td class=sz>%s</td>'
                     '<td><a class=btn href="/dl?p=%s">download</a> '
                     '<button class="btn del" onclick="del(\'%s\')">delete</button></td></tr>' % (en, _human(sz), full, full))
    js = ('<script>const CSRF="%s";'
          'function del(p){if(!confirm("Delete "+decodeURIComponent(p)+" ?"))return;'
          'fetch("/rm?p="+p+"&confirm=1",{method:"POST",headers:{"X-Acid-CSRF":CSRF}}).then(r=>location.reload())}'
          'function up(f){for(const file of f.files){fetch("/up?p=%s/"+encodeURIComponent(file.name),'
          '{method:"PUT",headers:{"X-Acid-CSRF":CSRF},body:file}).then(r=>r.ok?location.reload():alert("upload failed "+r.status))}}'
          '</script>') % (html.escape(csrf), urllib.parse.quote(path.rstrip('/')))
    return ('<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">'
            '<title>%s</title><style>%s</style><div class=wrap>'
            '<div class=bar><div>%s</div><div><a href=/logout>logout</a></div></div>'
            '<div class=bar><label>upload here: <input type=file multiple onchange="up(this)"></label></div>'
            '<table><tr><th>name</th><th class=sz>size</th><th>actions</th></tr>%s</table>'
            '<p class=warn style="margin-top:10px">full root access &middot; deletes are permanent</p>%s</div>'
            ) % (html.escape(path), CSS, crumb, body, js)


# ---------------- HTTP handler ----------------
class H(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    timeout = 30
    server_version = 'acid'

    def log_message(self, *a):
        pass

    def _ip(self):
        return self.client_address[0]

    def _sid(self):
        for c in (self.headers.get('Cookie') or '').split(';'):
            k, _, v = c.strip().partition('=')
            if k == 'sid':
                return v
        return ''

    def _send(self, code, body=b'', ctype='text/html; charset=utf-8', extra=None):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _auth(self):
        return _session(self._sid())

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        s = self._auth()
        if u.path in ('/', '/login') and not s:
            return self._send(200, _login_page())
        if not s:
            return self._send(200, _login_page('please log in'))
        if u.path in ('/', '/b'):
            path = _clean(q.get('p', ['/'])[0])
            if path is None or not os.path.isdir(path):
                path = '/'
            rows, err = _listing(path)
            if err is not None:
                return self._send(200, _browse_page(path, [], s['csrf']))
            return self._send(200, _browse_page(path, rows, s['csrf']))
        if u.path == '/dl':
            return self._download(_clean(q.get('p', [''])[0]))
        if u.path == '/logout':
            with _lock:
                _sessions.pop(self._sid(), None)
            return self._send(200, _login_page('logged out'),
                              extra=[('Set-Cookie', 'sid=; Path=/; Max-Age=0')])
        return self._send(404, 'not found')

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == '/login':
            n = min(int(self.headers.get('Content-Length', 0) or 0), 4096)
            data = urllib.parse.parse_qs(self.rfile.read(n).decode('utf-8', 'replace'))
            user = data.get('user', [''])[0]
            pw = data.get('pass', [''])[0]
            r = _check_login(user, pw, self._ip())
            if r == 'ok':
                sid = _new_session(self._ip())
                return self._send(302, '', extra=[('Location', '/b?p=/'),
                                  ('Set-Cookie', 'sid=%s; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=%d' % (sid, SESS_IDLE))])
            if r == 'locked':
                return self._send(429, _login_page('too many attempts - locked, wait'))
            return self._send(200, _login_page('wrong user or password'))
        s = self._auth()
        if not s:
            return self._send(403, 'forbidden')
        if not _ct(self.headers.get('X-Acid-CSRF', ''), s['csrf']):     # CSRF gate on mutations
            return self._send(403, 'csrf')
        q = urllib.parse.parse_qs(u.query)
        if u.path == '/rm':
            return self._delete(_clean(q.get('p', [''])[0]), q.get('confirm', ['0'])[0] == '1')
        return self._send(404, 'not found')

    def do_PUT(self):
        u = urllib.parse.urlparse(self.path)
        s = self._auth()
        if not s:
            return self._send(403, 'forbidden')
        if not _ct(self.headers.get('X-Acid-CSRF', ''), s['csrf']):
            return self._send(403, 'csrf')
        if u.path != '/up':
            return self._send(404, 'not found')
        q = urllib.parse.parse_qs(u.query)
        return self._upload(_clean(q.get('p', [''])[0]))

    # ---- file ops ----
    def _download(self, path):
        if not path or not os.path.isfile(path):
            return self._send(404, 'not a file')
        try:
            sz = os.path.getsize(path)
            f = open(path, 'rb')
        except Exception as e:
            return self._send(403, 'open failed: %s' % html.escape(str(e)))
        # /proc & /sys report size 0 but yield content; a file may also grow after stat. Send
        # Content-Length only when authoritative, else close-delimit the body (no keep-alive desync).
        known = sz > 0 and not path.startswith(('/proc/', '/sys/'))
        fn = os.path.basename(path).replace('"', '_').replace('\r', '_').replace('\n', '_')
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Disposition', 'attachment; filename="%s"' % fn)
        if known:
            self.send_header('Content-Length', str(sz))
        else:
            self.send_header('Connection', 'close')
            self.close_connection = True
        self.end_headers()
        try:
            if known:
                remain = sz                          # never write more than promised (TOCTOU if it grew)
                while remain > 0:
                    chunk = f.read(min(65536, remain))
                    if not chunk:
                        break
                    self.wfile.write(chunk); remain -= len(chunk)
            else:
                shutil.copyfileobj(f, self.wfile, 65536)
        except Exception:
            pass
        finally:
            f.close()

    def _upload(self, path):
        if not path:
            return self._send(400, 'bad path')
        d = os.path.dirname(path)
        if not os.path.isdir(d):
            return self._send(400, 'target dir missing')
        try:
            n = int(self.headers.get('Content-Length', -1))
        except ValueError:
            n = -1
        if n < 0 or n > MAX_UPLOAD:
            return self._send(413, 'too large / no length')
        try:
            st = os.statvfs(d)
            if st.f_bavail * st.f_frsize < n + (16 * 1024 * 1024):
                return self._send(507, 'not enough space')
        except Exception:
            pass
        fd, tmp = tempfile.mkstemp(dir=d, prefix='.acidup')
        try:
            left = n
            with os.fdopen(fd, 'wb') as out:
                while left > 0:
                    chunk = self.rfile.read(min(65536, left))
                    if not chunk:
                        break
                    out.write(chunk)
                    left -= len(chunk)
            if left != 0:
                raise IOError('short upload')
            os.replace(tmp, path)                    # atomic; never truncates an in-use file
            return self._send(200, 'ok')
        except Exception as e:
            try: os.unlink(tmp)
            except OSError: pass
            return self._send(500, 'upload failed: %s' % html.escape(str(e)))

    def _delete(self, path, confirm):
        if not path:
            return self._send(400, 'bad path')
        rp = os.path.realpath(path)                       # resolve symlinks - a string denylist is bypassable
        # refuse if rp IS a protected dir, is an ANCESTOR of one (rmtree would take it), or is inside DIR
        if (rp == '/' or rp in PROTECT or rp == DIR or rp.startswith(DIR + '/')
                or any(p == rp or p.startswith(rp.rstrip('/') + '/') for p in PROTECT)):
            return self._send(400, 'refused (protected system path)')
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                if not confirm:
                    return self._send(400, 'need confirm for a directory')
                shutil.rmtree(rp)
            else:
                os.remove(path)
            return self._send(200, 'ok')
        except Exception as e:
            return self._send(500, 'delete failed: %s' % html.escape(str(e)))


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _watchdog(srv):
    while True:
        time.sleep(20)
        now = time.time()
        with _lock:
            for k in [k for k, v in _sessions.items()
                      if now - v['last_seen'] > SESS_IDLE or now - v['created'] > SESS_MAX]:
                _sessions.pop(k, None)
            live = len(_sessions)
        if now - _start > HARD_LIFE:
            _die()
        if live == 0 and now - _last_auth > INACTIVITY:
            _die()                                   # nobody using it -> tear down (fail-closed)


def main():
    if not (os.path.exists(CERT) and os.path.exists(KEY) and os.path.exists(CREDS)):
        return
    srv = _Server(('0.0.0.0', PORT), H)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT, KEY)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=_watchdog, args=(srv,), daemon=True).start()
    srv.serve_forever()


if __name__ == '__main__':
    main()
