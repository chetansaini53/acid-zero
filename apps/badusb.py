# Acid Zero plugin - "Bad USB": WiFi-controlled HID injection via a Pico 2 W.
# The Pico hosts its OWN access point (AcidZero-Duck); this app joins it on a
# dedicated spare adapter (wlan2) via CONNECT, then sends Flipper-compatible
# DuckyScript payloads to the Pico at 192.168.4.1:1337. The Pi's main uplink
# (wlan1) keeps SSH + internet the whole time. Self-contained - works anywhere.
#
# Payloads live in /home/ella3/acid_badusb/ and are browsed as nested FOLDERS,
# one directory at a time (same lazy model as the IR app - a pasted-in payload
# pack can be thousands of files deep, so only the open folder is ever scanned).
#
# Always-on AUTHORIZED-USE banner + an (i) educational Learn screen. Educational
# / own-lab / authorized-device only. See ETHICS.md.
import os, sys, threading
for _p in ('/usr/local/bin', '/usr/local/lib/acid-apps', '/home/ella3'):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    from acid_badusb import (BadUSB, BadUSBError, link_connect, link_disconnect,
                             link_active, ap_creds, AP_SSID, HOST)
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

    def ap_creds():
        return AP_SSID, 'acidzero1337'

try:
    import acid_apcreds as C          # shared creds store (validate + save)
except Exception:
    C = None
try:
    import acid_kbd                   # shared on-screen keyboard
except Exception:
    acid_kbd = None

META = {'name': 'Bad USB', 'icon': 'badusb', 'color': (210, 90, 90)}

SCRIPTS_DIR = '/home/ella3/acid_badusb'    # drop Flipper .txt DuckyScripts (and folders) here

_view = 'main'          # main | info | creds | kb
_browse_rel = ''         # current folder, relative to SCRIPTS_DIR ('' = root)
_browse_entries = []      # [(is_dir, abs_path, name, count), ...] of the CURRENT folder only
_browse_page = 0
_PER_PAGE = 4
_sel_path = None          # selected .txt payload (abs path) - persists across nav
_sel_name = ''
_link = 'idle'            # idle | connecting | online | offline | disconnecting
_status = 'CONNECT, then pick a payload'
_busy = False
_ap_ssid = 'AcidZero-Duck'   # live Pico AP creds (shared with the Flasher)
_ap_psk = 'acidzero1337'
_kb_target = ''           # 'ssid' | 'psk'  (which creds field the keyboard edits)


def _set(ctx, s):
    global _status
    _status = s
    try:
        ctx.mark_dirty()
    except Exception:
        pass


def _spawn(fn, *a):
    threading.Thread(target=fn, args=a, daemon=True).start()


# ---------- lazy folder browser (same model as the IR app) ----------
def _rel_join(rel, name):
    return (rel + '/' + name) if rel else name


def _rel_up(rel):
    return rel.rsplit('/', 1)[0] if '/' in rel else ''


def _browse_abs(rel):
    return os.path.join(SCRIPTS_DIR, *rel.split('/')) if rel else SCRIPTS_DIR


def _refresh_browse():
    """Scan ONE directory (the open folder) - never the whole tree, so a huge
    payload pack never freezes the UI."""
    global _browse_entries
    out = []
    try:
        os.makedirs(SCRIPTS_DIR, exist_ok=True)
        base = _browse_abs(_browse_rel)
        with os.scandir(base) as it:
            items = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
        for e in items:
            try:
                if e.is_dir():
                    with os.scandir(e.path) as sub:
                        n = sum(1 for _ in sub)
                    out.append((True, e.path, e.name, n))
                elif e.name.lower().endswith('.txt'):
                    out.append((False, e.path, e.name[:-4], 0))
            except Exception:
                pass
    except Exception:
        pass
    _browse_entries = out


def _paged(count, page, per_page):
    total = max(1, (count + per_page - 1) // per_page)
    page = min(max(page, 0), total - 1)
    return page, total, page * per_page


def _draw_page_bar(d, ctx, y, page, total):
    ctx.rr(d, (10, y, 130, y + 22), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
    ctx.ct(d, 70, y + 11, '< PREV', ctx.F_SM, ctx.FG if page > 0 else ctx.DIM)
    ctx.ct(d, 240, y + 11, '%d / %d' % (page + 1, total), ctx.F_SM, ctx.FG)
    ctx.rr(d, (350, y, 470, y + 22), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
    ctx.ct(d, 410, y + 11, 'NEXT >', ctx.F_SM, ctx.FG if page < total - 1 else ctx.DIM)


def _touch_page_bar(tx, page, total, ctx):
    if tx <= 130 and page > 0 and ctx.debounce(0.25):
        return page - 1
    if tx >= 350 and page < total - 1 and ctx.debounce(0.25):
        return page + 1
    return None


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
    _set(ctx, 'joining %s ...' % _ap_ssid)
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
    global _view, _browse_rel, _browse_page, _ap_ssid, _ap_psk
    _view = 'main'
    _browse_rel = ''
    _browse_page = 0
    try:
        _ap_ssid, _ap_psk = ap_creds()    # what CONNECT will join (Flasher-shared)
    except Exception:
        pass
    if acid_kbd:
        acid_kbd.close()
    _refresh_browse()
    _spawn(_w_probe, ctx)
    ctx.mark_dirty()


# ---------- view: MAIN ----------
def _draw_main(d, ctx):
    ctx.topbar(d, 'BAD USB')
    ctx.rr(d, (344, 4, 410, 24), outline=(150, 190, 240), w=1, r=8)
    ctx.ct(d, 377, 14, 'AP creds', ctx.F_TINY, (150, 190, 240))
    ctx.rr(d, (418, 4, 472, 24), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, 445, 14, '(i) info', ctx.F_TINY, ctx.ACC)

    # AUTHORIZED-USE banner (always on)
    ctx.rr(d, (6, 30, 474, 48), fill=(58, 22, 22), outline=(200, 70, 70), w=1, r=6)
    ctx.ct(d, 240, 39, '! AUTHORIZED DEVICES ONLY - educational / own-lab', ctx.F_SM, (255, 165, 165))

    # link status line
    if _link == 'online':
        c, txt = (30, 200, 121), 'LINK: ONLINE  -  Pico @ %s' % HOST
    elif _link == 'connecting':
        c, txt = (235, 180, 40), 'LINK: connecting to %s ...' % _ap_ssid
    elif _link == 'disconnecting':
        c, txt = (235, 180, 40), 'LINK: disconnecting ...'
    elif _link == 'offline':
        c, txt = (235, 80, 80), 'LINK: joined AP but Pico not answering'
    else:
        c, txt = (150, 160, 170), 'LINK: not connected  -  tap CONNECT'
    d.ellipse((12, 55, 21, 64), fill=c)
    ctx.lt(d, 28, 60, txt[:54], ctx.F_TINY, c)

    # CONNECT / DISCONNECT
    busy = _link in ('connecting', 'disconnecting')
    conn_on = _link in ('idle', 'offline') and not busy
    ctx.rr(d, (10, 70, 234, 90), fill=(30, 90, 60) if conn_on else (40, 48, 44),
           outline=ctx.ACC if conn_on else ctx.LINE, w=1, r=6)
    ctx.ct(d, 122, 80, 'CONNECT', ctx.F_SM, ctx.FG if conn_on else ctx.DIM)
    disc_on = _link in ('online', 'offline') and not busy
    ctx.rr(d, (246, 70, 470, 90), fill=(90, 45, 45) if disc_on else (40, 44, 44),
           outline=(200, 90, 90) if disc_on else ctx.LINE, w=1, r=6)
    ctx.ct(d, 358, 80, 'DISCONNECT', ctx.F_SM, ctx.FG if disc_on else ctx.DIM)

    # browser: path bar + UP
    nested = bool(_browse_rel)
    path_txt = ('/payloads/' + _browse_rel) if nested else '/payloads/'
    ctx.rr(d, (10, 95, 360, 115), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=6)
    ctx.lt(d, 18, 105, path_txt[:34], ctx.F_TINY, (150, 190, 240))
    ctx.rr(d, (366, 95, 470, 115), fill=(45, 52, 68) if nested else (34, 38, 40), r=6)
    ctx.ct(d, 418, 105, 'UP', ctx.F_SM, ctx.ACC if nested else ctx.DIM)

    # entries (folders first, then .txt payloads)
    LIST_TOP, ROW_H = 119, 27
    if not _browse_entries:
        ctx.ct(d, 240, 165, 'empty folder', ctx.F_NM, ctx.DIM)
        ctx.ct(d, 240, 186, 'drop Flipper .txt DuckyScripts (+ folders) into', ctx.F_SM, ctx.DIM)
        ctx.ct(d, 240, 202, '/home/ella3/acid_badusb/', ctx.F_TINY, (150, 190, 240))
    else:
        page, total, start = _paged(len(_browse_entries), _browse_page, _PER_PAGE)
        y = LIST_TOP
        for is_dir, path, name, n in _browse_entries[start:start + _PER_PAGE]:
            if is_dir:
                ctx.rr(d, (10, y, 470, y + 24), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
                ctx.rr(d, (16, y + 7, 28, y + 18), fill=(90, 140, 225), r=4)
                ctx.lt(d, 36, y + 12, name[:34], ctx.F_SM, ctx.FG)
                ctx.lt(d, 398, y + 12, '%d item%s' % (n, '' if n == 1 else 's'), ctx.F_TINY, (150, 190, 240))
            elif path == _sel_path:
                # SELECTED: light background so the name stays readable
                ctx.rr(d, (10, y, 470, y + 24), fill=(202, 227, 212), outline=(110, 205, 150), w=1, r=6)
                ctx.lt(d, 18, y + 12, name[:40], ctx.F_SM, (16, 44, 28))
                ctx.ct(d, 448, y + 12, 'SEL', ctx.F_TINY, (18, 95, 55))
            else:
                ctx.rr(d, (10, y, 470, y + 24), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
                ctx.lt(d, 18, y + 12, name[:44], ctx.F_SM, ctx.FG)
            y += ROW_H
        if total > 1:
            _draw_page_bar(d, ctx, LIST_TOP + _PER_PAGE * ROW_H + 2, page, total)

    # RUN button
    can_run = (_sel_path and _link == 'online' and not _busy)
    ctx.rr(d, (10, 256, 470, 298), fill=(205, 60, 60) if can_run else (70, 45, 45), r=8)
    ctx.ct(d, 240, 277, 'RUNNING...' if _busy else 'RUN ON TARGET', ctx.F_NM, (255, 240, 240))
    ctx.ct(d, 240, 310, _status[:58], ctx.F_TINY, ctx.DIM)


def _touch_main(tx, ty, ctx):
    global _view, _browse_rel, _browse_page, _sel_path, _sel_name, _busy
    if ty <= 24 and tx >= 418 and ctx.debounce(0.3):
        _view = 'info'
        ctx.mark_dirty()
        return
    if ty <= 24 and 344 <= tx <= 410 and ctx.debounce(0.3):
        _view = 'creds'
        ctx.mark_dirty()
        return
    busy = _link in ('connecting', 'disconnecting')
    # CONNECT / DISCONNECT
    if 70 <= ty <= 90 and not busy:
        if tx <= 234 and _link in ('idle', 'offline') and ctx.debounce(0.5):
            _spawn(_w_connect, ctx)
            return
        if tx >= 246 and _link in ('online', 'offline') and ctx.debounce(0.5):
            _spawn(_w_disconnect, ctx)
            return
    # UP (exit directory)
    if 95 <= ty <= 115 and tx >= 366 and _browse_rel and ctx.debounce(0.3):
        _browse_rel = _rel_up(_browse_rel)
        _browse_page = 0
        _refresh_browse()
        ctx.mark_dirty()
        return
    # entries
    LIST_TOP, ROW_H = 119, 27
    if _browse_entries:
        page, total, start = _paged(len(_browse_entries), _browse_page, _PER_PAGE)
        bar_y = LIST_TOP + _PER_PAGE * ROW_H + 2
        if total > 1 and bar_y <= ty <= bar_y + 22:
            newp = _touch_page_bar(tx, page, total, ctx)
            if newp is not None:
                _browse_page = newp
                ctx.mark_dirty()
            return
        if LIST_TOP <= ty <= LIST_TOP + _PER_PAGE * ROW_H:
            idx = start + (ty - LIST_TOP) // ROW_H
            if start <= idx < min(start + _PER_PAGE, len(_browse_entries)):
                is_dir, path, name, n = _browse_entries[idx]
                if is_dir and ctx.debounce(0.3):
                    _browse_rel = _rel_join(_browse_rel, name)   # enter directory
                    _browse_page = 0
                    _refresh_browse()
                    ctx.mark_dirty()
                elif not is_dir and ctx.debounce(0.25):
                    _sel_path = path
                    _sel_name = name
                    _set(ctx, 'selected: %s' % name[:38])
                return
    # RUN
    if 256 <= ty <= 298 and ctx.debounce(0.5):
        if _busy:
            return
        if not _sel_path:
            _set(ctx, 'select a payload first')
            return
        if _link != 'online':
            _set(ctx, 'CONNECT to the Pico AP first')
            return
        _busy = True
        _spawn(_w_run, ctx, _sel_path, _sel_name)
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


# ---------- view: PICO AP CREDS (manual entry; shared with the Flasher) ----------
def _draw_creds(d, ctx):
    ctx.topbar(d, 'PICO AP CREDS')
    ctx.rr(d, (8, 32, 472, 80), fill=(22, 34, 52), outline=(70, 110, 170), w=1, r=6)
    ctx.lt(d, 16, 47, "The Pico's own WiFi AP - this is what CONNECT joins.", ctx.F_TINY, (170, 200, 240))
    ctx.lt(d, 16, 64, 'Set them to match what you flashed (shared with Flasher).', ctx.F_TINY, (150, 175, 210))
    ctx.lt(d, 20, 105, 'SSID', ctx.F_SM, ctx.DIM)
    ctx.rr(d, (92, 92, 420, 118), fill=ctx.PANEL, outline=ctx.ACC, w=1, r=6)
    ctx.lt(d, 102, 105, _ap_ssid[:34], ctx.F_NM, ctx.FG)
    ctx.lt(d, 20, 151, 'PW', ctx.F_SM, ctx.DIM)
    ctx.rr(d, (92, 138, 420, 164), fill=ctx.PANEL, outline=ctx.ACC, w=1, r=6)
    ctx.lt(d, 102, 151, _ap_psk[:34], ctx.F_NM, ctx.FG)
    ctx.ct(d, 240, 194, 'tap a field to edit - saved instantly for the next CONNECT', ctx.F_TINY, ctx.DIM)
    ctx.ct(d, 240, 214, 'WPA2 password must be 8-63 characters', ctx.F_TINY, ctx.DIM)
    ctx.rr(d, (176, 262, 304, 296), fill=(30, 90, 60), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, 240, 279, 'DONE', ctx.F_NM, ctx.FG)
    ctx.ct(d, 240, 312, _status[:58], ctx.F_TINY, ctx.DIM)


def _touch_creds(tx, ty, ctx):
    global _view, _kb_target
    if 92 <= ty <= 118 and 92 <= tx <= 420 and ctx.debounce(0.3):
        if acid_kbd:
            _kb_target = 'ssid'; acid_kbd.start('SSID', _ap_ssid, maxlen=32); _view = 'kb'
        ctx.mark_dirty(); return
    if 138 <= ty <= 164 and 92 <= tx <= 420 and ctx.debounce(0.3):
        if acid_kbd:
            _kb_target = 'psk'; acid_kbd.start('PASSWORD', _ap_psk, maxlen=63); _view = 'kb'
        ctx.mark_dirty(); return
    if 262 <= ty <= 296 and 176 <= tx <= 304 and ctx.debounce(0.3):
        _view = 'main'; ctx.mark_dirty()


def _kb_commit(value, ctx):
    """Apply an edited SSID/PW: validate, persist to the shared store, update display."""
    global _ap_ssid, _ap_psk
    if _kb_target == 'ssid':
        ns, np = (value or 'AcidZero-Duck'), _ap_psk
    else:
        ns, np = _ap_ssid, (value or 'acidzero1337')
    if C:
        okv, why = C.validate(ns, np)
        if not okv:
            _set(ctx, why)                 # reject; keep the old values
            return
        C.save(ns, np)
        _ap_ssid, _ap_psk = ns, np
        # If the link is already up it still uses the OLD profile until a reconnect.
        if _link in ('online', 'offline'):
            _set(ctx, 'saved - DISCONNECT then CONNECT to apply')
        else:
            _set(ctx, 'saved - CONNECT will use these')
    else:
        _ap_ssid, _ap_psk = ns, np
        _set(ctx, 'set (store unavailable - CONNECT uses defaults)')


# ---------- dispatch ----------
def draw(d, ctx):
    if _view == 'kb' and acid_kbd:
        acid_kbd.draw(d, ctx)
    elif _view == 'creds':
        _draw_creds(d, ctx)
    elif _view == 'info':
        _draw_info(d, ctx)
    else:
        _draw_main(d, ctx)


def handle_touch(tx, ty, ctx):
    global _view
    if _view == 'kb':
        if not acid_kbd:
            _view = 'creds'; ctx.mark_dirty(); return
        r = acid_kbd.touch(tx, ty, ctx)
        if r == 'editing':
            return
        if isinstance(r, tuple) and r[0] == 'ok':
            _kb_commit(r[1], ctx)
        _view = 'creds'; ctx.mark_dirty()
        return
    if _view == 'creds':
        _touch_creds(tx, ty, ctx)
        return
    if _view == 'info':
        _touch_info(tx, ty, ctx)
        return
    _touch_main(tx, ty, ctx)
