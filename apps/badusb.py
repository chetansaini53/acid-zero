# Acid Zero plugin - "Bad USB": WiFi-controlled HID injection via a Pico 2 W.
# Browses DuckyScript payloads (Flipper-compatible .txt in /home/ella3/acid_badusb/,
# same folder pattern as the IR app), shows the Pico link status, and runs a chosen
# payload on the TARGET the Pico is plugged into. The Pi never injects anything itself
# - it only sends the DuckyScript over WiFi to firmware/pico-badusb (acidducky.local:1337).
#
# Always-on AUTHORIZED-USE banner + an (i) educational Learn screen (what it is, why it's
# here, how to detect/defend). Educational / own-lab / authorized-device-only. See ETHICS.md.
import os, sys, glob, threading
for _p in ('/usr/local/bin', '/usr/local/lib/acid-apps', '/home/ella3'):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    from acid_badusb import BadUSB, BadUSBError
except Exception:
    BadUSB = None
    class BadUSBError(Exception):
        pass

META = {'name': 'Bad USB', 'icon': 'badusb', 'color': (210, 90, 90)}

_view = 'main'          # main | info
_scripts = []            # [(path, name), ...]
_sel = -1                 # selected script index
_page = 0
_PER_PAGE = 5
_online = None            # None = checking, True / False
_status = 'select a payload, then RUN'
_busy = False


def _set(ctx, s):
    global _status
    _status = s
    try: ctx.mark_dirty()
    except Exception: pass


def _refresh_scripts():
    global _scripts, _sel
    try:
        _scripts = BadUSB.list_scripts() if BadUSB else []
    except Exception:
        _scripts = []
    if _sel >= len(_scripts):
        _sel = -1


def _w_check(ctx):
    global _online
    try:
        _online = BadUSB().ping() if BadUSB else False
    except Exception:
        _online = False
    try: ctx.mark_dirty()
    except Exception: pass


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
        try: ctx.mark_dirty()
        except Exception: pass


def _spawn(fn, *a):
    threading.Thread(target=fn, args=a, daemon=True).start()


# ---------- lifecycle ----------
def on_enter(ctx):
    global _view, _online
    _view = 'main'
    _online = None
    _refresh_scripts()
    _spawn(_w_check, ctx)
    ctx.mark_dirty()


# ---------- view: MAIN ----------
def _pages():
    return max(1, (len(_scripts) + _PER_PAGE - 1) // _PER_PAGE)


def _draw_main(d, ctx):
    ctx.topbar(d, 'BAD USB')
    ctx.rr(d, (418, 4, 472, 24), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, 445, 14, '(i) info', ctx.F_TINY, ctx.ACC)

    # AUTHORIZED-USE banner (always on)
    ctx.rr(d, (6, 31, 474, 53), fill=(58, 22, 22), outline=(200, 70, 70), w=1, r=6)
    ctx.ct(d, 240, 42, '! AUTHORIZED DEVICES ONLY  -  educational / own-lab', ctx.F_SM, (255, 165, 165))

    # Pico link status
    if _online is None:
        c, txt = (235, 180, 40), 'Pico link: checking...'
    elif _online:
        c, txt = (30, 200, 121), 'Pico link: ONLINE  (acidducky.local:1337)'
    else:
        c, txt = (235, 80, 80), 'Pico link: OFFLINE - power / WiFi / plug into target'
    d.ellipse((14, 63, 24, 73), fill=c)
    ctx.lt(d, 32, 68, txt, ctx.F_SM, c)
    ctx.rr(d, (410, 60, 472, 78), outline=ctx.ACC, w=1, r=5)
    ctx.ct(d, 441, 69, 'recheck', ctx.F_TINY, ctx.ACC)

    # payload list
    if not _scripts:
        ctx.ct(d, 240, 140, 'no payloads yet', ctx.F_NM, ctx.DIM)
        ctx.ct(d, 240, 162, 'drop Flipper .txt DuckyScripts into', ctx.F_SM, ctx.DIM)
        ctx.ct(d, 240, 180, '/home/ella3/acid_badusb/', ctx.F_TINY, (150, 190, 240))
    else:
        y = 88
        start = _page * _PER_PAGE
        for i, (path, name) in enumerate(_scripts[start:start + _PER_PAGE]):
            idx = start + i
            selq = (idx == _sel)
            ctx.rr(d, (10, y, 470, y + 26), fill=(40, 55, 42) if selq else ctx.TILE,
                   outline=ctx.ACC if selq else ctx.LINE, w=1, r=6)
            ctx.lt(d, 18, y + 13, name[:42], ctx.F_SM, ctx.FG)
            if selq:
                ctx.ct(d, 450, y + 13, 'SEL', ctx.F_TINY, ctx.ACC)
            y += 28

    # page bar (only when more than one page)
    if len(_scripts) > _PER_PAGE:
        pg, tot = _page, _pages()
        ctx.ct(d, 60, 244, '< prev', ctx.F_SM, ctx.FG if pg > 0 else ctx.DIM)
        ctx.ct(d, 240, 244, '%d / %d' % (pg + 1, tot), ctx.F_SM, ctx.DIM)
        ctx.ct(d, 420, 244, 'next >', ctx.F_SM, ctx.FG if pg < tot - 1 else ctx.DIM)

    # RUN button
    can_run = (_sel >= 0 and _online and not _busy)
    ctx.rr(d, (10, 258, 470, 298), fill=(205, 60, 60) if can_run else (70, 45, 45), r=8)
    ctx.ct(d, 240, 278, 'RUNNING...' if _busy else 'RUN ON TARGET', ctx.F_NM, (255, 240, 240))

    ctx.ct(d, 240, 310, _status[:58], ctx.F_TINY, ctx.DIM)


def _touch_main(tx, ty, ctx):
    global _view, _sel, _page, _online, _busy
    if ty <= 24 and tx >= 418 and ctx.debounce(0.3):
        _view = 'info'; ctx.mark_dirty(); return
    if 60 <= ty <= 78 and tx >= 410 and ctx.debounce(0.5):
        _online = None; _spawn(_w_check, ctx); ctx.mark_dirty(); return
    # payload rows
    if 88 <= ty <= 88 + _PER_PAGE * 28 and _scripts:
        idx = _page * _PER_PAGE + (ty - 88) // 28
        if 0 <= idx < len(_scripts) and ctx.debounce(0.25):
            _sel = idx; _set(ctx, 'selected: %s' % _scripts[idx][1][:40]); return
    # page nav
    if len(_scripts) > _PER_PAGE and 234 <= ty <= 256:
        if tx <= 130 and _page > 0 and ctx.debounce(0.25):
            _page -= 1; ctx.mark_dirty(); return
        if tx >= 350 and _page < _pages() - 1 and ctx.debounce(0.25):
            _page += 1; ctx.mark_dirty(); return
    # RUN
    if 258 <= ty <= 298 and ctx.debounce(0.5):
        if _busy:
            return
        if _sel < 0:
            _set(ctx, 'select a payload first'); return
        if not _online:
            _set(ctx, 'Pico offline - recheck the link first'); return
        _busy = True
        path, name = _scripts[_sel]
        _spawn(_w_run, ctx, path, name); ctx.mark_dirty()


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
        'Understanding how it works is what lets you detect + block it.',
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
        _view = 'main'; ctx.mark_dirty()


# ---------- dispatch ----------
def draw(d, ctx):
    (_draw_info if _view == 'info' else _draw_main)(d, ctx)


def handle_touch(tx, ty, ctx):
    (_touch_info if _view == 'info' else _touch_main)(tx, ty, ctx)
