# Acid Zero plugin - "CyberChef": an offline encode / hash / entropy multitool.
#
# Paste text (from the LAN clipboard bridge or the on-screen keyboard), tap an
# operation, read the result, COPY it back. Base64 / Hex / URL / ROT13 / Binary /
# Reverse + MD5 / SHA1 / SHA256 + Shannon-entropy - all pure-stdlib, 100% offline.
# A "CyberChef-lite" for CTFs and quick security work; pairs with the TOTP tool.
# Own-lab / educational use only.
import base64
import codecs
import hashlib
import math
import os
import tempfile
import threading
import time
import urllib.parse
from collections import Counter

META = {'name': 'CyberChef', 'icon': 'flask', 'color': (90, 200, 180)}

CLIP = '/run/acid_clip.txt'


# ---------------- transforms (all take/return str) ----------------
def _b64e(s): return base64.b64encode(s.encode()).decode()
def _b64d(s):
    t = ''.join(s.split())                            # drop whitespace/newlines
    try: return base64.b64decode(t + '=' * (-len(t) % 4), validate=True).decode('utf-8', 'replace')
    except Exception: return '[invalid base64]'       # validate=True rejects non-alphabet chars
def _hexe(s): return s.encode().hex()
def _hexd(s):
    try: return bytes.fromhex(s.strip().replace(' ', '')).decode('utf-8', 'replace')
    except Exception: return '[invalid hex]'
def _urle(s): return urllib.parse.quote(s)
def _urld(s): return urllib.parse.unquote(s)
def _rot13(s): return codecs.encode(s, 'rot_13')
def _rev(s): return s[::-1]
def _bin(s): return ' '.join(format(b, '08b') for b in s.encode())
def _md5(s): return hashlib.md5(s.encode()).hexdigest()
def _sha1(s): return hashlib.sha1(s.encode()).hexdigest()
def _sha256(s): return hashlib.sha256(s.encode()).hexdigest()
def _entropy(s):
    if not s: return '0.00 bits/char'
    n = len(s); c = Counter(s)
    h = abs(-sum((v / n) * math.log2(v / n) for v in c.values()))   # abs kills -0.0 on uniform input
    return '%.2f bits/char   (%.1f bits total)' % (h, h * n)


OPS = [('B64 ENC', _b64e), ('B64 DEC', _b64d), ('HEX ENC', _hexe),
       ('HEX DEC', _hexd), ('URL ENC', _urle), ('URL DEC', _urld),
       ('ROT13', _rot13), ('REVERSE', _rev), ('BINARY', _bin),
       ('MD5', _md5), ('SHA256', _sha256), ('ENTROPY', _entropy),
       ('SHA1', _sha1)]

# on-screen keyboard pages (base64/hex-friendly)
_KP = {'abc': ['qwertyuiop', 'asdfghjkl-', 'zxcvbnm+/='],
       '123': ['1234567890', '!@#$%^&*()', '-_=+[]{}|\\'],
       'sym': [':;\'"`,.<>?', '?/\\|&$*()[', ']}{=+-~^%@']}
_KY = [64, 100, 136]

_in = ''
_out = ''
_opname = ''
_kbd = False
_tpage = 'abc'
_flash = ''
_flash_t = 0.0
_gen = 0


def on_enter(ctx):
    global _kbd, _gen
    _kbd = False
    _gen += 1
    threading.Thread(target=_tick, args=(ctx, _gen), daemon=True).start()
    ctx.mark_dirty()


def on_exit(ctx):
    global _gen
    _gen += 1


def _tick(ctx, gen):
    while gen == _gen:
        time.sleep(0.5)
        try: ctx.mark_dirty()          # cursor blink / flash timeout
        except Exception: break


def _flashmsg(m):
    global _flash, _flash_t
    _flash = m; _flash_t = time.time()


def _paste():
    global _in
    try:
        with open(CLIP, encoding='utf-8') as f:
            _in += f.read()
    except Exception:
        pass


def _copy(ctx):
    if not _out:
        _flashmsg('nothing to copy'); return
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(CLIP), prefix='.acidcc')
        try: os.write(fd, _out.encode('utf-8'))
        finally: os.close(fd)
        os.replace(tmp, CLIP)
        _flashmsg('output -> clipboard bridge')
    except Exception:
        _flashmsg('copy failed')


def _run_op(idx, ctx):
    global _out, _opname
    if not (0 <= idx < len(OPS)):
        return
    name, fn = OPS[idx]
    try:
        _out = fn(_in)
    except Exception as e:
        _out = '[error] %s' % e
    _opname = name
    ctx.mark_dirty()


# ---------------- draw ----------------
def _crop(d, ctx, txt, maxw, font, tail=False):
    txt = str(txt)
    if d.textlength(txt, font=font) <= maxw:
        return txt
    if tail:
        while txt and d.textlength('..' + txt, font=font) > maxw: txt = txt[1:]
        return '..' + txt
    while txt and d.textlength(txt + '..', font=font) > maxw: txt = txt[:-1]
    return txt + '..'


def _wraplines(d, txt, font, maxpx, maxlines):
    lines, cur = [], ''
    for ch in str(txt):
        if d.textlength(cur + ch, font=font) <= maxpx:
            cur += ch
        else:
            lines.append(cur); cur = ch
            if len(lines) >= maxlines:
                return lines[:maxlines - 1] + [lines[-1][:-2] + '..']
    lines.append(cur)
    return lines


def _btn(d, ctx, box, label, fill, fg):
    ctx.rr(d, box, fill=fill, r=7)
    ctx.ct(d, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, label, ctx.F_SM, fg)


def _draw_keyboard(d, ctx):
    ctx.rr(d, (4, 58, 476, 250), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=6)
    for r, row in enumerate(_KP[_tpage]):
        y = _KY[r]
        for c, ch in enumerate(row):
            x = 8 + c * 46
            ctx.rr(d, (x, y, x + 42, y + 30), fill=ctx.TILE, outline=ctx.LINE, w=1, r=5)
            ctx.ct(d, x + 21, y + 15, ch, ctx.F_SM, ctx.FG)
    for x0, x1, lab, pg in ((8, 118, 'ABC', 'abc'), (122, 232, '123', '123'), (236, 346, 'SYM', 'sym')):
        on = _tpage == pg
        ctx.rr(d, (x0, 172, x1, 202), fill=(30, 120, 210) if on else ctx.TILE, outline=ctx.LINE, w=1, r=6)
        ctx.ct(d, (x0 + x1) // 2, 187, lab, ctx.F_SM, (240, 248, 255) if on else ctx.FG)
    ctx.rr(d, (350, 172, 468, 202), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6); ctx.ct(d, 409, 187, 'Bksp', ctx.F_SM, ctx.FG)
    ctx.rr(d, (8, 206, 346, 236), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6); ctx.ct(d, 177, 221, 'SPACE', ctx.F_SM, ctx.DIM)
    ctx.rr(d, (350, 206, 468, 236), fill=(25, 150, 90), r=6); ctx.ct(d, 409, 221, 'DONE', ctx.F_SM, (240, 255, 246))


def _draw_ops(d, ctx):
    xs = [4, 162, 320]
    ys = [58, 92, 126, 160]
    for i, (label, _fn) in enumerate(OPS[:12]):
        x0 = xs[i % 3]; y0 = ys[i // 3]
        ctx.rr(d, (x0, y0, x0 + 152, y0 + 30), fill=ctx.TILE, outline=ctx.LINE, w=1, r=7)
        ctx.ct(d, x0 + 76, y0 + 15, label, ctx.F_SM, ctx.ACC)


def draw(d, ctx):
    d.rectangle((0, 0, ctx.W, ctx.H), fill=ctx.BG)
    d.rectangle((0, 0, ctx.W, 26), fill=ctx.BARBG); d.line([(0, 26), (ctx.W, 26)], fill=ctx.LINE)
    ctx.lt(d, 8, 13, 'CYBERCHEF', ctx.F_TIT, ctx.FG)
    ctx.ct(d, 400, 13, 'offline encode / hash', ctx.F_TINY, ctx.DIM)
    # input line
    ctx.rr(d, (4, 30, 476, 54), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=5)
    cur = '_' if int(time.time() * 2) % 2 else ' '
    ctx.lt(d, 10, 42, 'in', ctx.F_TINY, ctx.DIM)
    ctx.lt(d, 30, 42, _crop(d, ctx, (_in + cur) if _in else 'tap to type, or PASTE below', 438, ctx.F_SM, tail=True),
           ctx.F_SM, ctx.FG if _in else ctx.DIM)
    if _kbd:
        _draw_keyboard(d, ctx)                        # keyboard owns 58-250; no output box under it
    else:
        _draw_ops(d, ctx)
        ctx.rr(d, (4, 198, 476, 250), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=5)
        ctx.lt(d, 10, 210, ('out  ' + _opname) if _opname else 'out', ctx.F_TINY, ctx.DIM)
        if _out:
            y = 224
            for ln in _wraplines(d, _out, ctx.F_TINY, 458, 2):
                ctx.lt(d, 10, y, ln, ctx.F_TINY, (120, 230, 150)); y += 12
    # actions
    _btn(d, ctx, (4, 254, 117, 300), 'PASTE', (45, 80, 120), (225, 240, 255))
    _btn(d, ctx, (121, 254, 234, 300), 'COPY', (45, 70, 100), (225, 240, 255))
    _btn(d, ctx, (238, 254, 351, 300), 'CLR', (70, 60, 46), (255, 235, 210))
    _btn(d, ctx, (355, 254, 476, 300), 'HIDE KB' if _kbd else 'KEYBOARD', (50, 56, 68), ctx.ACC)
    if _flash and time.time() - _flash_t < 3:
        ctx.ct(d, 240, 310, _flash, ctx.F_TINY, ctx.ACC)


# ---------------- touch ----------------
def _touch_keyboard(tx, ty, ctx):
    global _in, _tpage, _kbd
    for r, row in enumerate(_KP[_tpage]):
        y = _KY[r]
        if y <= ty <= y + 30:
            c = (tx - 8) // 46
            if 0 <= c < len(row) and ctx.debounce(0.07):
                _in += row[c]; ctx.mark_dirty()
            return
    if 172 <= ty <= 202:
        for x0, x1, pg in ((8, 118, 'abc'), (122, 232, '123'), (236, 346, 'sym')):
            if x0 <= tx <= x1 and ctx.debounce(0.2):
                _tpage = pg; ctx.mark_dirty(); return
        if tx >= 350 and ctx.debounce(0.07):
            _in = _in[:-1]; ctx.mark_dirty(); return
        return
    if 206 <= ty <= 236:
        if tx <= 346 and ctx.debounce(0.07): _in += ' '; ctx.mark_dirty(); return
        if tx >= 350 and ctx.debounce(0.2): _kbd = False; ctx.mark_dirty(); return


def handle_touch(tx, ty, ctx):
    global _in, _out, _opname, _kbd
    if 254 <= ty <= 300:                              # action row (always live)
        if tx <= 117 and ctx.debounce(0.25): _paste(); ctx.mark_dirty(); return
        if tx <= 234 and ctx.debounce(0.25): _copy(ctx); ctx.mark_dirty(); return
        if tx <= 351 and ctx.debounce(0.25): _in = ''; _out = ''; _opname = ''; ctx.mark_dirty(); return
        if ctx.debounce(0.2): _kbd = not _kbd; ctx.mark_dirty(); return
        return
    if 30 <= ty <= 54 and ctx.debounce(0.2):          # tap input -> keyboard
        _kbd = True; ctx.mark_dirty(); return
    if _kbd:
        _touch_keyboard(tx, ty, ctx); return
    xs = [4, 162, 320]; ys = [58, 92, 126, 160]        # ops grid
    for i in range(min(12, len(OPS))):
        x0 = xs[i % 3]; y0 = ys[i // 3]
        if x0 <= tx <= x0 + 152 and y0 <= ty <= y0 + 30 and ctx.debounce(0.15):
            _run_op(i, ctx); return
