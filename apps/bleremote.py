# Acid Zero plugin - "BT Remote": a small 2-column folder of Bluetooth-HID tools.
# First tool = Bluetooth Remote (media keys): the Pi advertises as a BLE HID
# peripheral ("Acid Zero Remote"); you pair it from your phone/tablet/PC's own
# Bluetooth settings (the host connects to the Pi - that's how HID works, the Pi
# does not scan for the host), then drive play/pause/vol/next/prev/mute from the
# touchscreen. DISCONNECT stops the remote and returns to the folder.
#
# Backend = acid_blehid.py (BLE HID GATT daemon) run as a child process; commands
# go over its stdin, connection state comes back via /run/acid_blehid.json.
# Educational / own-lab use only.
import json, os, subprocess, sys, threading, time
for _p in ('/usr/local/bin', '/usr/local/lib/acid-apps'):
    if _p not in sys.path:
        sys.path.insert(0, _p)

META = {'name': 'BT Remote', 'icon': 'bt', 'color': (60, 130, 235)}

DAEMON = '/usr/local/bin/acid_blehid.py'
STATE = '/run/acid_blehid.json'

# 2-column folder entries: (name, view).
APPS = [('Bluetooth Remote', 'remote'), ('BT Keyboard', 'keyboard')]

# media pad: (label, cmd, box)
PAD = [
    ('|<<', 'prev', (10, 92, 160, 152)), ('> ||', 'playpause', (165, 92, 315, 152)),
    ('>>|', 'next', (320, 92, 470, 152)),
    ('VOL-', 'voldown', (10, 160, 160, 220)), ('MUTE', 'mute', (165, 160, 315, 220)),
    ('VOL+', 'volup', (320, 160, 470, 220)),
]

_view = 'folder'          # folder | remote
_proc = None
_status = 'starting remote...'
_gen = 0                  # tick generation (marquee/status refresh)
_lock = threading.Lock()


# ---------------- daemon control ----------------
def _running():
    return _proc is not None and _proc.poll() is None


def _start(ctx):
    global _proc, _status
    with _lock:
        if _running():
            return
        try:
            _proc = subprocess.Popen(['/usr/bin/python3', DAEMON],
                                     stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=open('/tmp/acid_blehid.log', 'w'))  # daemon diag log
            _status = 'advertising - pair "Acid Zero Remote" from your device'
        except Exception as e:
            _proc = None
            _status = 'start failed: %s' % str(e)[:26]
    ctx.mark_dirty()


def _send(cmd):
    with _lock:
        if _running():
            try:
                _proc.stdin.write((cmd + '\n').encode()); _proc.stdin.flush()
            except Exception:
                pass


def _stop():
    global _proc
    with _lock:
        p = _proc; _proc = None
    if p and p.poll() is None:
        try:
            p.stdin.write(b'quit\n'); p.stdin.flush()
        except Exception:
            pass
        try:
            p.wait(timeout=2)
        except Exception:
            try: p.terminate()
            except Exception: pass
    try:
        os.remove(STATE)
    except Exception:
        pass


def _conn_state():
    """-> (connected, central_name)."""
    try:
        with open(STATE) as f:
            j = json.load(f)
        return bool(j.get('connected')), str(j.get('central', ''))
    except Exception:
        return False, ''


def _pair_code():
    try:
        with open('/run/acid_blehid.pair') as f:
            return f.read().strip()[:6]
    except Exception:
        return ''


# ---------------- lifecycle ----------------
def _tick(ctx, gen):
    while gen == _gen and _view in ('remote', 'keyboard'):
        time.sleep(0.8)
        try: ctx.mark_dirty()
        except Exception: break


def on_enter(ctx):
    global _view
    _view = 'folder'
    ctx.mark_dirty()


def on_exit(ctx):
    global _gen
    _gen += 1
    _stop()


# ---------------- draw helpers ----------------
def _crop(d, ctx, txt, maxw, font):
    try:
        if d.textlength(txt, font=font) <= maxw:
            return txt
        while txt and d.textlength(txt + '..', font=font) > maxw:
            txt = txt[:-1]
        return txt + '..'
    except Exception:
        return txt[:20]


def _bticon(d, cx, cy, col):
    # simple Bluetooth rune
    d.line([(cx, cy - 9), (cx, cy + 9)], fill=col, width=2)
    d.line([(cx, cy - 9), (cx + 6, cy - 4)], fill=col, width=2)
    d.line([(cx + 6, cy - 4), (cx - 6, cy + 4)], fill=col, width=2)
    d.line([(cx, cy + 9), (cx + 6, cy + 4)], fill=col, width=2)
    d.line([(cx + 6, cy + 4), (cx - 6, cy - 4)], fill=col, width=2)


def _btn(ctx, d, box, label, fill, fg, font=None):
    ctx.rr(d, box, fill=fill, r=8)
    ctx.ct(d, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, label, font or ctx.F_NM, fg)


# ---------------- view: FOLDER (2-column grid) ----------------
def _draw_folder(d, ctx):
    d.rectangle((0, 0, ctx.W, 28), fill=ctx.BARBG); d.line([(0, 28), (ctx.W, 28)], fill=ctx.LINE)
    ctx.rr(d, (6, 4, 92, 24), outline=ctx.ACC, w=1, r=5); ctx.ct(d, 49, 15, '< back', ctx.F_SM, ctx.ACC)
    ctx.ct(d, 260, 14, 'BT REMOTE', ctx.F_TIT, ctx.FG)
    cols = [(10, 234), (246, 470)]
    y = 40
    for i, (name, view) in enumerate(APPS):
        cx0, cx1 = cols[i % 2]
        ctx.rr(d, (cx0, y, cx1, y + 46), fill=ctx.TILE, outline=ctx.LINE, w=1, r=10)
        _bticon(d, cx0 + 24, y + 23, META['color'])
        ctx.lt(d, cx0 + 46, y + 23, _crop(d, ctx, name, cx1 - cx0 - 58, ctx.F_SM), ctx.F_SM, ctx.FG)
        if i % 2 == 1:
            y += 52
    ctx.ct(d, 240, ctx.H - 10, 'tap a tool to open  ·  own devices only', ctx.F_TINY, ctx.DIM)


def _touch_folder(tx, ty, ctx):
    global _view, _gen
    cols = [(10, 234), (246, 470)]
    y = 40
    for i, (name, view) in enumerate(APPS):
        cx0, cx1 = cols[i % 2]
        if y <= ty <= y + 46 and cx0 <= tx <= cx1 and ctx.debounce(0.3):
            _view = view; _gen += 1
            threading.Thread(target=lambda g=_gen: _tick(ctx, g), daemon=True).start()
            _start(ctx); ctx.mark_dirty(); return
        if i % 2 == 1:
            y += 52


# ---------------- view: REMOTE (media keys) ----------------
def _draw_remote(d, ctx):
    ctx.topbar(d, 'BLUETOOTH REMOTE')
    _btn(ctx, d, (386, 3, 472, 25), 'FOLDER', (45, 52, 68), ctx.ACC, ctx.F_SM)
    connected, central = _conn_state()
    # status strip
    ctx.rr(d, (8, 32, 472, 84), fill=ctx.PANEL, outline=(60, 200, 110) if connected else ctx.LINE, w=1, r=8)
    dot = (60, 200, 110) if connected else (235, 180, 40)
    d.ellipse((20, 50, 34, 64), fill=dot)
    if connected:
        ctx.lt(d, 44, 50, 'CONNECTED', ctx.F_NM, (60, 200, 110))
        ctx.lt(d, 44, 70, _crop(d, ctx, (central or 'a device') + '  -  media keys live', 410, ctx.F_TINY), ctx.F_TINY, ctx.DIM)
    else:
        code = _pair_code()
        if code:
            ctx.lt(d, 44, 49, 'PAIRING CODE  ' + code, ctx.F_NM, (90, 180, 255))
            ctx.lt(d, 44, 70, 'confirm on your device - it should show the SAME code', ctx.F_TINY, ctx.DIM)
        else:
            ctx.lt(d, 44, 50, 'ADVERTISING as "Acid Zero Remote"', ctx.F_SM, (235, 180, 40))
            ctx.lt(d, 44, 70, _crop(d, ctx, 'open Bluetooth on your device -> pair "Acid Zero Remote"', 410, ctx.F_TINY), ctx.F_TINY, ctx.DIM)
    # media pad
    for label, cmd, box in PAD:
        big = cmd == 'playpause'
        fill = (30, 120, 210) if (connected and big) else (46, 54, 70) if connected else (34, 38, 48)
        fg = (240, 248, 255) if connected else ctx.DIM
        _btn(ctx, d, box, label, fill, fg, ctx.F_BIG if big else ctx.F_NM)
    _btn(ctx, d, (10, 240, 470, 288), 'DISCONNECT & STOP', (200, 60, 60), (255, 235, 235), ctx.F_NM)


def _touch_remote(tx, ty, ctx):
    global _view, _gen
    if ty <= 25 and tx >= 386 and ctx.debounce(0.3):        # FOLDER (keep remote running)
        _view = 'folder'; ctx.mark_dirty(); return
    if 240 <= ty <= 288 and ctx.debounce(0.4):              # DISCONNECT & STOP
        _gen += 1; _stop(); _view = 'folder'; ctx.mark_dirty(); return
    for label, cmd, box in PAD:
        x0, y0, x1, y1 = box
        if x0 <= tx <= x1 and y0 <= ty <= y1 and ctx.debounce(0.18):
            _send(cmd); ctx.mark_dirty(); return


# ---------------- view: KEYBOARD (full BLE keyboard) ----------------
# HID Keyboard/Keypad usage codes. Modifier byte bits: Ctrl 1, Shift 2, Alt 4, Win 8.
_MODS = [('CTRL', 0x01), ('SHIFT', 0x02), ('ALT', 0x04), ('WIN', 0x08)]
_kmod = 0          # armed sticky-modifier byte; one-shot (clears after a key)
_caps = False      # Caps Lock: persistent, auto-shifts a-z (no per-key Shift)
_CAPS = 57         # HID usage 0x39 - also our Caps-toggle sentinel in _SPECIAL
_kpage = 'abc'
_PAGES = {
    'abc': [
        [('q', 20), ('w', 26), ('e', 8), ('r', 21), ('t', 23), ('y', 28), ('u', 24), ('i', 12), ('o', 18), ('p', 19)],
        [('a', 4), ('s', 22), ('d', 7), ('f', 9), ('g', 10), ('h', 11), ('j', 13), ('k', 14), ('l', 15), (';', 51)],
        [('z', 29), ('x', 27), ('c', 6), ('v', 25), ('b', 5), ('n', 17), ('m', 16), (',', 54), ('.', 55), ('/', 56)],
    ],
    '123': [
        [('1', 30), ('2', 31), ('3', 32), ('4', 33), ('5', 34), ('6', 35), ('7', 36), ('8', 37), ('9', 38), ('0', 39)],
        [('-', 45), ('=', 46), ('[', 47), (']', 48), ('\\', 49), ('`', 53), ("'", 52), (';', 51), (',', 54), ('.', 55)],
        [('/', 56), ('F1', 58), ('F2', 59), ('F3', 60), ('F4', 61), ('F5', 62), ('F6', 63), ('F7', 64), ('F8', 65), ('F9', 66)],
    ],
    'num': [
        [('7', 95), ('8', 96), ('9', 97), ('/', 84), ('*', 85), ('Hom', 74), ('Up', 82), ('PgU', 75), ('Ins', 73), ('Del', 76)],
        [('4', 92), ('5', 93), ('6', 94), ('-', 86), ('+', 87), ('Lft', 80), ('Dn', 81), ('Rgt', 79), ('End', 77), ('PgD', 78)],
        [('1', 89), ('2', 90), ('3', 91), ('0', 98), ('.', 99), ('Num', 83), ('F10', 67), ('F11', 68), ('F12', 69), ('KEn', 88)],
    ],
}
_TABS = [('ABC', 'abc'), ('123', '123'), ('NUM', 'num')]
_SPECIAL = [('Esc', 41), ('Tab', 43), ('Caps', _CAPS)]   # Caps = local lock toggle (see _touch)
_ARROWS = [('<', 80), ('v', 81), ('^', 82), ('>', 79)]


def _kb_send(code):
    global _kmod
    mod = _kmod | (0x02 if _caps and 4 <= code <= 29 else 0)   # Caps Lock shifts letters a-z only
    _send('k %d %d' % (mod, code))
    _kmod = 0          # sticky modifiers are one-shot; Caps Lock persists until toggled off


def _draw_keyboard(d, ctx):
    ctx.topbar(d, 'BT KEYBOARD')
    connected, _ = _conn_state()
    d.ellipse((360, 9, 372, 21), fill=(60, 200, 110) if connected else (235, 180, 40))
    _btn(ctx, d, (386, 3, 472, 25), 'FOLDER', (45, 52, 68), ctx.ACC, ctx.F_SM)
    mx = 2
    for label, bit in _MODS:                       # sticky modifier row (ty>=42 clears the home-zone)
        on = bool(_kmod & bit)
        ctx.rr(d, (mx, 42, mx + 90, 64), fill=(30, 120, 210) if on else (46, 54, 70), r=6)
        ctx.ct(d, mx + 45, 53, label, ctx.F_SM, (240, 248, 255) if on else ctx.FG); mx += 94
    ctx.rr(d, (mx, 42, 478, 64), fill=(150, 45, 45), r=6); ctx.ct(d, (mx + 478) // 2, 53, 'C-A-DEL', ctx.F_SM, (255, 230, 230))
    ys = [68, 104, 140]
    for r, row in enumerate(_PAGES[_kpage]):        # 3 key rows of 10
        y = ys[r]
        for c, (label, code) in enumerate(row):
            x = 2 + c * 48
            disp = label.upper() if (_caps and len(label) == 1 and 'a' <= label <= 'z') else label
            ctx.rr(d, (x, y, x + 44, y + 32), fill=ctx.TILE, outline=ctx.LINE, w=1, r=5)
            ctx.ct(d, x + 22, y + 16, disp, ctx.F_SM if len(disp) <= 2 else ctx.F_TINY, ctx.FG)
    bx = 2
    for label, pg in _TABS:                         # page tabs
        on = _kpage == pg
        ctx.rr(d, (bx, 176, bx + 74, 206), fill=(30, 120, 210) if on else (46, 54, 70), r=6)
        ctx.ct(d, bx + 37, 191, label, ctx.F_SM, (240, 248, 255) if on else ctx.FG); bx += 78
    for label, code in _SPECIAL:                    # Esc, Tab, Caps(lock toggle)
        capson = code == _CAPS and _caps
        ctx.rr(d, (bx, 176, bx + 74, 206), fill=(30, 120, 210) if capson else ctx.PANEL,
               outline=ctx.LINE, w=1, r=6)
        ctx.ct(d, bx + 37, 191, label, ctx.F_SM, (240, 248, 255) if capson else ctx.FG); bx += 78
    ctx.rr(d, (2, 210, 120, 242), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=6); ctx.ct(d, 61, 226, 'Bksp', ctx.F_SM, ctx.FG)
    ctx.rr(d, (124, 210, 356, 242), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6); ctx.ct(d, 240, 226, 'SPACE', ctx.F_SM, ctx.DIM)
    ctx.rr(d, (360, 210, 478, 242), fill=(25, 150, 90), r=6); ctx.ct(d, 419, 226, 'Enter', ctx.F_SM, (240, 255, 246))
    ax = 2
    for label, code in _ARROWS:                     # arrow cluster
        ctx.rr(d, (ax, 246, ax + 116, 280), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
        ctx.ct(d, ax + 58, 263, label, ctx.F_BIG, ctx.ACC); ax += 119
    ctx.ct(d, 240, 300, ('tap a modifier then a key  ·  keys go to the paired device'
                         if connected else 'not connected - pair from Bluetooth Remote first'),
           ctx.F_TINY, ctx.DIM if connected else (235, 120, 120))


def _touch_keyboard(tx, ty, ctx):
    global _view, _kmod, _kpage, _caps
    if ty <= 25 and tx >= 386 and ctx.debounce(0.3):
        _view = 'folder'; ctx.mark_dirty(); return
    if 42 <= ty <= 64:                              # modifier row (fully below the home-zone)
        mx = 2
        for label, bit in _MODS:
            if mx <= tx <= mx + 90 and ctx.debounce(0.15):
                _kmod ^= bit; ctx.mark_dirty(); return
            mx += 94
        if tx >= mx and ctx.debounce(0.3):
            _send('k 5 76'); ctx.mark_dirty(); return       # Ctrl+Alt+Del
        return
    ys = [68, 104, 140]
    for r, row in enumerate(_PAGES[_kpage]):
        y = ys[r]
        if y <= ty <= y + 32:
            c = (tx - 2) // 48
            if 0 <= c < len(row) and ctx.debounce(0.1):
                _kb_send(row[c][1]); ctx.mark_dirty()
            return
    if 176 <= ty <= 206:
        cx = 2
        for label, pg in _TABS:
            if cx <= tx <= cx + 74 and ctx.debounce(0.2):
                _kpage = pg; ctx.mark_dirty(); return
            cx += 78
        for label, code in _SPECIAL:
            if cx <= tx <= cx + 74 and ctx.debounce(0.1):
                if code == _CAPS:
                    _caps = not _caps          # persistent Caps Lock, not a keystroke
                else:
                    _kb_send(code)
                ctx.mark_dirty(); return
            cx += 78
        return
    if 210 <= ty <= 242:
        if tx <= 120 and ctx.debounce(0.1): _kb_send(42)      # Bksp
        elif tx <= 356 and ctx.debounce(0.1): _kb_send(44)    # Space
        elif ctx.debounce(0.1): _kb_send(40)                  # Enter
        ctx.mark_dirty(); return
    if 246 <= ty <= 280:
        ax = 2
        for label, code in _ARROWS:
            if ax <= tx <= ax + 116 and ctx.debounce(0.1):
                _kb_send(code); ctx.mark_dirty(); return
            ax += 119


# ---------------- dispatch ----------------
def draw(d, ctx):
    {'remote': _draw_remote, 'keyboard': _draw_keyboard}.get(_view, _draw_folder)(d, ctx)


def handle_touch(tx, ty, ctx):
    {'remote': _touch_remote, 'keyboard': _touch_keyboard}.get(_view, _touch_folder)(tx, ty, ctx)
