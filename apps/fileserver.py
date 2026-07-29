# Acid Zero plugin - "File Server": on-demand root file manager over its own WPA2 AP.
#
# START -> the Pi stands up its own WPA2 AP (SSH-safe adapter via wifiroles) + an HTTPS root
# file manager, and shows the AP SSID/password, the web URL(s), and an ephemeral web login on
# THIS screen. Join the AP (or use it on home wifi), open the URL, accept the self-signed cert,
# log in, browse/download/upload/delete anywhere. STOP tears it all down + wipes the creds.
#
# This grants root-equivalent remote access ON PURPOSE - hence the warning banner, ephemeral
# creds, brute-force lockout, and auto-teardown. Off-by-default, never in the released image.
# Own-lab / educational use only.
import sys
import threading
import time

for _p in ('/usr/local/bin', '/usr/local/lib/acid-apps'):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    import acid_fileap
except Exception:
    acid_fileap = None

META = {'name': 'File Server', 'icon': 'net', 'color': (90, 180, 235)}

_msg = ''
_msg_t = 0.0
_busy = False


def _flash(m):
    global _msg, _msg_t
    _msg = m; _msg_t = time.time()


def _bg(fn):
    global _busy
    if _busy:
        return
    _busy = True

    def run():
        global _busy
        try:
            fn()
        finally:
            _busy = False
    threading.Thread(target=run, daemon=True).start()


def _do_start(ctx):
    if acid_fileap is None:
        _flash('control module missing'); ctx.mark_dirty(); return
    ok, m = acid_fileap.start()
    _flash(m)
    ctx.mark_dirty()


def _do_stop(ctx):
    if acid_fileap is not None:
        acid_fileap.stop()
    _flash('stopping - AP down, creds wiped')
    ctx.mark_dirty()


def on_enter(ctx):
    ctx.mark_dirty()


def _running():
    return acid_fileap is not None and acid_fileap.is_running()


# ---------------- draw ----------------
def draw(d, ctx):
    d.rectangle((0, 0, ctx.W, ctx.H), fill=ctx.BG)
    d.rectangle((0, 0, ctx.W, 26), fill=ctx.BARBG); d.line([(0, 26), (ctx.W, 26)], fill=ctx.LINE)
    ctx.lt(d, 8, 13, 'FILE SERVER', ctx.F_TIT, ctx.FG)
    run = _running()
    ctx.ct(d, 430, 13, 'LIVE' if run else 'off', ctx.F_TINY, (90, 220, 130) if run else ctx.DIM)
    if run:
        _draw_running(d, ctx)
    else:
        _draw_stopped(d, ctx)
    if _msg and time.time() - _msg_t < 6:
        ctx.ct(d, 240, ctx.H - 8, _msg[:60], ctx.F_TINY, ctx.ACC)


def _draw_stopped(d, ctx):
    ctx.rr(d, (10, 34, ctx.W - 10, 96), fill=(70, 20, 20), outline=(235, 80, 80), w=2, r=10)
    ctx.ct(d, 240, 52, 'WARNING - ROOT FILESYSTEM over WiFi', ctx.F_NM, (255, 200, 200))
    ctx.ct(d, 240, 72, 'browse / download / upload / DELETE anywhere as root.', ctx.F_TINY, (255, 220, 220))
    ctx.ct(d, 240, 86, 'ephemeral creds + brute-force lock + auto-stop. Own device only.', ctx.F_TINY, (255, 220, 220))
    ctx.rr(d, (120, 128, 360, 186), fill=(25, 150, 90) if not _busy else (70, 80, 60), r=12)
    ctx.ct(d, 240, 157, 'starting...' if _busy else 'START SERVER', ctx.F_NM, (235, 255, 242))
    ctx.ct(d, 240, 214, 'Pi makes its OWN WPA2 AP on a spare adapter (SSH stays up).', ctx.F_TINY, ctx.DIM)
    ctx.ct(d, 240, 230, 'AP creds + web URL + login will show here once it is up.', ctx.F_TINY, ctx.DIM)
    ctx.ct(d, 240, 252, 'auto-stops after 15 min idle  ·  hard cap 2 h  ·  50 fails = lock', ctx.F_TINY, ctx.DIM)


def _kv(d, ctx, x, y, k, v, vcol=None):
    ctx.lt(d, x, y, k, ctx.F_TINY, ctx.DIM)
    ctx.lt(d, x + 52, y, v, ctx.F_NM, vcol or ctx.FG)


def _draw_running(d, ctx):
    c = acid_fileap.creds() if acid_fileap else {}
    s = acid_fileap.status() if acid_fileap else {}
    port = c.get('port', 8443)
    ctx.rr(d, (8, 32, ctx.W - 8, 92), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=8)
    ctx.lt(d, 16, 44, '1) JOIN THIS WPA2 AP', ctx.F_TINY, ctx.ACC)
    _kv(d, ctx, 16, 62, 'SSID', c.get('ap_ssid', '-'), (150, 240, 175))
    _kv(d, ctx, 16, 80, 'PASS', c.get('ap_psk', '-'), (150, 240, 175))
    ctx.rr(d, (8, 98, ctx.W - 8, 150), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=8)
    ctx.lt(d, 16, 110, '2) OPEN (accept the cert)', ctx.F_TINY, ctx.ACC)
    ctx.lt(d, 16, 128, 'https://10.13.37.1:%s' % port, ctx.F_NM, (150, 200, 240))
    hip = s.get('home_ip')
    if hip:
        ctx.lt(d, 250, 128, 'https://%s:%s' % (hip, port), ctx.F_SM, (150, 200, 240))
    ctx.rr(d, (8, 156, ctx.W - 8, 208), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=8)
    ctx.lt(d, 16, 168, '3) LOG IN', ctx.F_TINY, ctx.ACC)
    _kv(d, ctx, 16, 186, 'user', c.get('web_user', '-'), (245, 215, 140))
    _kv(d, ctx, 250, 186, 'pass', c.get('web_pass', '-'), (245, 215, 140))
    ctx.rr(d, (120, 220, 360, 268), fill=(180, 55, 55), r=12)
    ctx.ct(d, 240, 244, 'STOP  &  WIPE', ctx.F_NM, (255, 235, 235))


# ---------------- touch ----------------
def handle_touch(tx, ty, ctx):
    if _running():
        if 220 <= ty <= 268 and 120 <= tx <= 360 and ctx.debounce(0.4):
            _bg(lambda: _do_stop(ctx))
    else:
        if 128 <= ty <= 186 and 120 <= tx <= 360 and ctx.debounce(0.5):
            _flash('starting AP + server...')
            ctx.mark_dirty()
            _bg(lambda: _do_start(ctx))
