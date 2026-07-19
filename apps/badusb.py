# Acid Zero plugin - "Bad USB": WiFi-controlled HID injection via a Pico 2 W.
# The Pico hosts its OWN access point (AcidZero-Duck); this app joins it on a
# dedicated spare adapter (wlan2) via CONNECT, then sends Flipper-compatible
# DuckyScript payloads (/home/ella3/acid_badusb/*.txt) to the Pico at
# 192.168.4.1:1337. The Pi's main uplink (wlan1) keeps SSH + internet the whole
# time. Self-contained - works anywhere, no per-location WiFi creds needed.
#
# Always-on AUTHORIZED-USE banner + an (i) educational Learn screen (what it is,
# why it's here, how to detect/defend). Educational / own-lab / authorized-device
# only. See ETHICS.md.
import os, sys, threading
for _p in ('/usr/local/bin', '/usr/local/lib/acid-apps', '/home/ella3'):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    from acid_badusb import (BadUSB, BadUSBError, link_connect, link_disconnect,
                             link_active, AP_SSID, HOST)
except Exception:
    BadUSB = None
    AP_SSID = 'AcidZero-Duck'
    HOST = '192.168.4.1'

    class BadUSBError(Exception):
        pass

    def link_connect():
        return False, 'client module missing'

    def link_disconnect():
        return True, ''

    def link_active():
        return False

META = {'name': 'Bad USB', 'icon': 'badusb', 'color': (210, 90, 90)}

_view = 'main'          # main | info
_scripts = []            # [(path, name), ...]
_sel = -1                 # selected script index
_page = 0
_PER_PAGE = 4
_link = 'idle'            # idle | connecting | online | offline | disconnecting
_status = 'tap CONNECT to reach the Pico'
_busy = False


def _set(ctx, s):
    global _status
    _status = s
    try:
        ctx.mark_dirty()
    except Exception:
        pass


def _refresh_scripts():
    global _scripts, _sel
    try:
        _scripts = BadUSB.list_scripts() if BadUSB else []
    except Exception:
        _scripts = []
    if _sel >= len(_scripts):
        _sel = -1


def _spawn(fn, *a):
    threading.Thread(target=fn, args=a, daemon=True).start()


# ---------- workers (off the UI thread) ----------
def _w_probe(ctx):
    global _link
    if not BadUSB:
        _link = 'idle'
    elif link_active():
        try:
            online = BadUSB().ping()
        except Exception:
            online = False
        _link = 'online' if online else 'offline'
    else:
        _link = 'idle'
    try:
        ctx.mark_dirty()
    except Exception:
        pass


def _w_connect(ctx):
    global _link
    _link = 'connecting'
    _set(ctx, 'joining %s ...' % AP_SSID)
    ok, msg = link_connect() if BadUSB else (False, 'client missing')
    if not ok:
        _link = 'idle'
        _set(ctx, msg[:52])
        return
    online = False
    try:
        online = BadUSB().ping()
    except Exception:
        online = False
    _link = 'online' if online else 'offline'
    _set(ctx, 'ONLINE - ready' if online else 'joined AP but Pico silent - is it powered?')


def _w_disconnect(ctx):
    global _link
    _link = 'disconnecting'
    _set(ctx, 'releasing wlan2 ...')
    try:
        link_disconnect()
    except Exception:
        pass
    _link = 'idle'
    _set(ctx, 'disconnected - SSH stayed on wlan1')


def _w_run(ctx, path, name):
    global _busy
    try:
        _set(ctx, 'sending "%s" -> target...' % name)
        r = BadUSB().run_script(path)
        _set(ctx, (r or 'sent')[:52])
    except Exception as e:
        _set(ctx, 'ERR: %s' % str(e)[:46])
    finally:
        _busy = False
        try:
            ctx.mark_dirty()
        except Exception:
            pass


# ---------- lifecycle ----------
def on_enter(ctx):
    global _view
    _view = 'main'
    _refresh_scripts()
    _spawn(_w_probe, ctx)
    ctx.mark_dirty()


# ---------- view: MAIN ----------
def _pages():
    return max(1, (len(_scripts) + _PER_PAGE - 1) // _PER_PAGE)


def _draw_main(d, ctx):
    ctx.topbar(d, 'BAD USB')
    ctx.rr(d, (418, 4, 472, 24), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, 445, 14, '(i) info', ctx.F_TINY, ctx.ACC)

    # AUTHORIZED-USE banner (always on)
    ctx.rr(d, (6, 31, 474, 51), fill=(58, 22, 22), outline=(200, 70, 70), w=1, r=6)
    ctx.ct(d, 240, 41, '! AUTHORIZED DEVICES ONLY  -  educational / own-lab', ctx.F_SM, (255, 165, 165))

    # link status line
    if _link == 'online':
        c, txt = (30, 200, 121), 'LINK: ONLINE  -  Pico @ %s' % HOST
    elif _link == 'connecting':
        c, txt = (235, 180, 40), 'LINK: connecting to %s ...' % AP_SSID
    elif _link == 'disconnecting':
        c, txt = (235, 180, 40), 'LINK: disconnecting ...'
    elif _link == 'offline':
        c, txt = (235, 80, 80), 'LINK: joined AP but Pico not answering'
    else:
        c, txt = (150, 160, 170), 'LINK: not connected  -  tap CONNECT'
    d.ellipse((12, 60, 22, 70), fill=c)
    ctx.lt(d, 30, 65, txt[:52], ctx.F_SM, c)

    # CONNECT / DISCONNECT
    busy = _link in ('connecting', 'disconnecting')
    conn_on = _link in ('idle', 'offline') and not busy
    ctx.rr(d, (10, 78, 234, 100), fill=(30, 90, 60) if conn_on else (40, 48, 44),
           outline=ctx.ACC if conn_on else ctx.LINE, w=1, r=6)
    ctx.ct(d, 122, 89, 'CONNECT', ctx.F_SM, ctx.FG if conn_on else ctx.DIM)
    disc_on = _link in ('online', 'offline') and not busy
    ctx.rr(d, (246, 78, 470, 100), fill=(90, 45, 45) if disc_on else (40, 44, 44),
           outline=(200, 90, 90) if disc_on else ctx.LINE, w=1, r=6)
    ctx.ct(d, 358, 89, 'DISCONNECT', ctx.F_SM, ctx.FG if disc_on else ctx.DIM)

    # payload list
    if not _scripts:
        ctx.ct(d, 240, 150, 'no payloads yet', ctx.F_NM, ctx.DIM)
        ctx.ct(d, 240, 172, 'drop Flipper .txt DuckyScripts into', ctx.F_SM, ctx.DIM)
        ctx.ct(d, 240, 190, '/home/ella3/acid_badusb/', ctx.F_TINY, (150, 190, 240))
    else:
        y = 106
        start = _page * _PER_PAGE
        for i, (path, name) in enumerate(_scripts[start:start + _PER_PAGE]):
            idx = start + i
            selq = (idx == _sel)
            ctx.rr(d, (10, y, 470, y + 24), fill=(40, 55, 42) if selq else ctx.TILE,
                   outline=ctx.ACC if selq else ctx.LINE, w=1, r=6)
            ctx.lt(d, 18, y + 12, name[:44], ctx.F_SM, ctx.FG)
            if selq:
                ctx.ct(d, 450, y + 12, 'SEL', ctx.F_TINY, ctx.ACC)
            y += 27

    # page bar
    if len(_scripts) > _PER_PAGE:
        pg, tot = _page, _pages()
        ctx.ct(d, 60, 228, '< prev', ctx.F_SM, ctx.FG if pg > 0 else ctx.DIM)
        ctx.ct(d, 240, 228, '%d / %d' % (pg + 1, tot), ctx.F_SM, ctx.DIM)
        ctx.ct(d, 420, 228, 'next >', ctx.F_SM, ctx.FG if pg < tot - 1 else ctx.DIM)

    # RUN button
    can_run = (_sel >= 0 and _link == 'online' and not _busy)
    ctx.rr(d, (10, 256, 470, 298), fill=(205, 60, 60) if can_run else (70, 45, 45), r=8)
    ctx.ct(d, 240, 277, 'RUNNING...' if _busy else 'RUN ON TARGET', ctx.F_NM, (255, 240, 240))

    ctx.ct(d, 240, 310, _status[:58], ctx.F_TINY, ctx.DIM)


def _touch_main(tx, ty, ctx):
    global _view, _sel, _page, _busy
    if ty <= 24 and tx >= 418 and ctx.debounce(0.3):
        _view = 'info'
        ctx.mark_dirty()
        return
    busy = _link in ('connecting', 'disconnecting')
    # CONNECT / DISCONNECT row
    if 78 <= ty <= 100 and not busy:
        if tx <= 234 and _link in ('idle', 'offline') and ctx.debounce(0.5):
            _spawn(_w_connect, ctx)
            return
        if tx >= 246 and _link in ('online', 'offline') and ctx.debounce(0.5):
            _spawn(_w_disconnect, ctx)
            return
    # payload rows
    if 106 <= ty <= 106 + _PER_PAGE * 27 and _scripts:
        idx = _page * _PER_PAGE + (ty - 106) // 27
        if 0 <= idx < len(_scripts) and ctx.debounce(0.25):
            _sel = idx
            _set(ctx, 'selected: %s' % _scripts[idx][1][:40])
            return
    # page nav
    if len(_scripts) > _PER_PAGE and 220 <= ty <= 240:
        if tx <= 130 and _page > 0 and ctx.debounce(0.25):
            _page -= 1
            ctx.mark_dirty()
            return
        if tx >= 350 and _page < _pages() - 1 and ctx.debounce(0.25):
            _page += 1
            ctx.mark_dirty()
            return
    # RUN
    if 256 <= ty <= 298 and ctx.debounce(0.5):
        if _busy:
            return
        if _sel < 0:
            _set(ctx, 'select a payload first')
            return
        if _link != 'online':
            _set(ctx, 'CONNECT to the Pico AP first')
            return
        _busy = True
        path, name = _scripts[_sel]
        _spawn(_w_run, ctx, path, name)
        ctx.mark_dirty()


# ---------- view: INFO (educational Learn) ----------
_INFO = [
    ('WHAT IS THIS?', (150, 200, 255), [
        'A USB device (here: a Pico 2 W) that pretends to be a',
        'keyboard and auto-types a scripted payload into the',
        'machine it is plugged into - far faster than a human.',
        'This is "HID injection" (the Rubber Ducky / Flipper attack).',
    ]),
    ('WHY IS IT HERE? (educational)', (120, 220, 150), [
        'To LEARN the attack so you can DEFEND against it. An OS',
        'trusts keyboards, so HID injection slips past many controls.',
        'The Pico hosts its own WiFi AP - no target network needed.',
    ]),
    ('HOW TO DETECT / DEFEND', (235, 180, 40), [
        '- USB device-control policy: approve/deny new HID devices',
        '- watch for rapid scripted keystrokes / unexpected launches',
        '- lock the screen when away; disable or whitelist USB ports',
        '- never plug in unknown USB drives or "found" cables',
    ]),
    ('THE RULE', (255, 120, 120), [
        'Use ONLY on machines you OWN or are explicitly AUTHORIZED',
        'to test. Unauthorized keystroke injection is illegal.',
    ]),
]


def _draw_info(d, ctx):
    ctx.topbar(d, 'BAD USB - LEARN')
    ctx.rr(d, (418, 4, 472, 24), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, 445, 14, 'back', ctx.F_TINY, ctx.ACC)
    y = 34
    for head, hc, body in _INFO:
        ctx.lt(d, 12, y + 8, head, ctx.F_SM, hc)
        y += 20
        for ln in body:
            ctx.lt(d, 20, y + 7, ln, ctx.F_TINY, ctx.FG)
            y += 15
        y += 4


def _touch_info(tx, ty, ctx):
    global _view
    if ty <= 24 and tx >= 418 and ctx.debounce(0.3):
        _view = 'main'
        ctx.mark_dirty()


# ---------- dispatch ----------
def draw(d, ctx):
    (_draw_info if _view == 'info' else _draw_main)(d, ctx)


def handle_touch(tx, ty, ctx):
    (_touch_info if _view == 'info' else _touch_main)(tx, ty, ctx)
