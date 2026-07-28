# Acid Zero plugin - "TOTP Auth": an offline RFC 6238 authenticator for the panel.
#
# Add an account (paste/type its base32 secret, then name it) and the device shows the
# live 6-digit code with a countdown - like Google Authenticator, but fully offline and
# pure-stdlib (HMAC-SHA1, no pip, no network). Rename/delete from an account's detail.
# Theme-aware (matches the launcher's light/dark). Top-right HOME returns to the grid.
#
# Secrets are stored 0600 root-only in /etc/acid-totp.json. They are 2FA seeds - treat
# this as a demo/lab authenticator; do NOT enter high-value production secrets on a
# device you plan to image for release. The clean-image scrub MUST wipe this file first
# (see BUILD_CLEAN_IMAGE.md - it now removes /etc/acid-totp.json). Own-lab use only.
import base64
import hashlib
import hmac
import json
import os
import struct
import tempfile
import threading
import time

META = {'name': 'TOTP Auth', 'icon': 'totp', 'color': (235, 180, 60)}

STORE = '/etc/acid-totp.json'
PERIOD = 30
DIGITS = 6

# fixed semantic colours (readable on both themes); everything else comes from ctx
WARN = (235, 150, 70)
DANGER = (225, 80, 80)


def _code_col(ctx):
    return (18, 132, 78) if getattr(ctx, 'theme', 'dark') == 'light' else (120, 230, 150)


_view = 'list'          # list | add | rename | detail
_accounts = []          # [{'name':str,'secret':str}]
_sel = -1
_field = 'secret'
_buf = ''
_in_secret = ''
_err = ''; _err_t = 0.0
_scroll = 0
_del_arm = 0.0
_gen = 0

_ROWS = ['QWERTYUIOP', 'ASDFGHJKL', 'ZXCVBNM', '1234567890']
_ROW_Y = [74, 104, 134, 164]


# ---------------- TOTP core (RFC 6238, SHA1) ----------------
def _norm_b32(s):
    s = s.strip().replace(' ', '').replace('-', '').upper()
    return s + '=' * (-len(s) % 8)


def _valid_b32(s):
    try:
        return bool(s.strip()) and bool(base64.b32decode(_norm_b32(s), casefold=True))
    except Exception:
        return False


def _totp(secret, t=None):
    key = base64.b32decode(_norm_b32(secret), casefold=True)
    if t is None:
        t = time.time()
    h = hmac.new(key, struct.pack('>Q', int(t // PERIOD)), hashlib.sha1).digest()
    o = h[-1] & 0x0f
    code = (struct.unpack('>I', h[o:o + 4])[0] & 0x7fffffff) % (10 ** DIGITS)
    return str(code).zfill(DIGITS)


def _remaining(t=None):
    if t is None:
        t = time.time()
    return PERIOD - int(t % PERIOD)


def _fmt(code):
    return code[:3] + ' ' + code[3:]


def _code_of(acc):
    try:
        return _totp(acc['secret'])
    except Exception:
        return '------'


# ---------------- storage ----------------
def _load():
    global _accounts
    out = []
    try:
        with open(STORE, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            for a in data:                       # coerce name to str; require a string secret
                if isinstance(a, dict) and isinstance(a.get('secret'), str):
                    out.append({'name': str(a.get('name', '?')), 'secret': a['secret']})
    except Exception:
        out = []
    _accounts = out


def _save():
    """Atomic 0600 write. Returns True on success; unlinks the temp on any failure so a
    partial plaintext-secret file never lingers in /etc."""
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STORE), prefix='.acidtotp')
    except Exception:
        return False
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(json.dumps(_accounts).encode('utf-8'))
            f.flush(); os.fsync(f.fileno())      # durable before the rename
        os.chmod(tmp, 0o600)
        os.replace(tmp, STORE)
        return True
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        return False


def _flash(msg):
    global _err, _err_t
    _err = msg; _err_t = time.time()


# ---------------- lifecycle ----------------
def on_enter(ctx):
    global _view, _sel, _buf, _field, _in_secret, _scroll, _del_arm, _gen
    _load()
    _view = 'list'; _sel = -1; _buf = ''; _field = 'secret'; _in_secret = ''
    _scroll = 0; _del_arm = 0.0                  # never carry a delete-arm across sessions
    _gen += 1
    threading.Thread(target=_tick, args=(ctx, _gen), daemon=True).start()
    ctx.mark_dirty()


def on_exit(ctx):
    global _gen, _del_arm
    _gen += 1; _del_arm = 0.0


def _tick(ctx, gen):
    while gen == _gen:
        time.sleep(1)
        try: ctx.mark_dirty()
        except Exception: break


# ---------------- draw helpers ----------------
def _crop(d, ctx, txt, maxw, font):
    txt = str(txt)
    if d.textlength(txt, font=font) <= maxw:
        return txt
    while txt and d.textlength(txt + '..', font=font) > maxw:
        txt = txt[:-1]
    return txt + '..'


def _hdr(d, ctx, title):
    d.rectangle((0, 0, ctx.W, 28), fill=ctx.BARBG); d.line([(0, 28), (ctx.W, 28)], fill=ctx.LINE)
    ctx.lt(d, 10, 8, _crop(d, ctx, title, 320, ctx.F_TIT), ctx.F_TIT, ctx.FG)
    ctx.ct(d, 378, 14, '%d acct' % len(_accounts), ctx.F_TINY, ctx.DIM)
    ctx.rr(d, (414, 4, 474, 24), fill=ctx.TILE, outline=ctx.ACC, w=1, r=6)
    ctx.ct(d, 444, 14, 'HOME', ctx.F_SM, ctx.ACC)


def _countbar(d, ctx, box, rem):
    x0, y0, x1, y1 = box
    col = DANGER if rem <= 5 else (WARN if rem <= 10 else _code_col(ctx))
    ctx.rr(d, box, fill=ctx.BG, outline=ctx.LINE, w=1, r=4)
    w = int((x1 - x0 - 2) * rem / PERIOD)
    if w > 0:
        d.rounded_rectangle((x0 + 1, y0 + 1, x0 + 1 + w, y1 - 1), radius=3, fill=col)


# ---------------- view: LIST ----------------
_L_TOP = 44
_L_H = 52
_L_ROWS = 4


def _draw_list(d, ctx):
    d.rectangle((0, 0, ctx.W, ctx.H), fill=ctx.BG)
    _hdr(d, ctx, 'TOTP AUTH')
    if not _accounts:
        ctx.ct(d, 240, 150, 'No accounts yet', ctx.F_NM, ctx.DIM)
        ctx.ct(d, 240, 174, 'tap  + ADD ACCOUNT  below', ctx.F_SM, ctx.DIM)
    else:
        rem = _remaining()
        y = _L_TOP
        for acc in _accounts[_scroll:_scroll + _L_ROWS]:
            ctx.rr(d, (6, y, 474, y + _L_H - 4), fill=ctx.TILE, outline=ctx.LINE, w=1, r=8)
            ctx.lt(d, 16, y + 13, _crop(d, ctx, acc.get('name', '?'), 300, ctx.F_SM), ctx.F_SM, ctx.DIM)
            ctx.lt(d, 16, y + 33, _fmt(_code_of(acc)), ctx.F_BIG, _code_col(ctx))
            ctx.lt(d, 404, y + 16, '%2ds' % rem, ctx.F_NM, ctx.FG)
            _countbar(d, ctx, (330, y + 30, 464, y + 40), rem)
            y += _L_H
    ctx.rr(d, (6, 266, 300, 308), fill=(30, 120, 78), r=8)
    ctx.ct(d, 153, 287, '+ ADD ACCOUNT', ctx.F_NM, (230, 255, 236))
    more = len(_accounts) > _L_ROWS
    ctx.rr(d, (306, 266, 388, 308), fill=ctx.TILE if more else ctx.BG, outline=ctx.LINE, w=1, r=8)
    ctx.ct(d, 347, 287, '^', ctx.F_BIG, ctx.ACC if more else ctx.DIM)
    ctx.rr(d, (392, 266, 474, 308), fill=ctx.TILE if more else ctx.BG, outline=ctx.LINE, w=1, r=8)
    ctx.ct(d, 433, 287, 'v', ctx.F_BIG, ctx.ACC if more else ctx.DIM)


def _touch_list(tx, ty, ctx):
    global _view, _sel, _scroll, _field, _buf, _in_secret, _del_arm
    if 266 <= ty <= 308:
        if tx <= 300 and ctx.debounce(0.3):
            _view = 'add'; _field = 'secret'; _buf = ''; _in_secret = ''; ctx.mark_dirty(); return
        if tx <= 388 and ctx.debounce(0.15):
            _scroll = max(0, _scroll - 1); ctx.mark_dirty(); return
        if ctx.debounce(0.15):
            _scroll = min(max(0, len(_accounts) - _L_ROWS), _scroll + 1); ctx.mark_dirty(); return
        return
    if _accounts and _L_TOP <= ty < _L_TOP + _L_ROWS * _L_H:
        idx = _scroll + (ty - _L_TOP) // _L_H
        if 0 <= idx < len(_accounts) and ctx.debounce(0.25):
            _sel = idx; _view = 'detail'; _del_arm = 0.0; ctx.mark_dirty()   # fresh context, no armed delete


# ---------------- view: DETAIL ----------------
def _draw_detail(d, ctx):
    d.rectangle((0, 0, ctx.W, ctx.H), fill=ctx.BG)
    acc = _accounts[_sel] if 0 <= _sel < len(_accounts) else {'name': '?', 'secret': ''}
    _hdr(d, ctx, _crop(d, ctx, acc.get('name', '?'), 300, ctx.F_TIT))
    rem = _remaining()
    ctx.rr(d, (30, 54, 450, 150), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=12)
    ctx.ct(d, 240, 96, _fmt(_code_of(acc)), ctx.F_BIG, _code_col(ctx))
    ctx.ct(d, 240, 128, 'refreshes in %ds' % rem, ctx.F_SM, ctx.DIM)
    _countbar(d, ctx, (40, 138, 440, 146), rem)
    armed = time.time() - _del_arm < 3
    ctx.rr(d, (20, 200, 150, 250), fill=(45, 90, 150), r=8); ctx.ct(d, 85, 225, 'RENAME', ctx.F_NM, (225, 238, 255))
    ctx.rr(d, (175, 200, 305, 250), fill=(150, 55, 55) if armed else (90, 55, 55), r=8)
    ctx.ct(d, 240, 225, 'CONFIRM?' if armed else 'DELETE', ctx.F_NM, (255, 222, 222))
    ctx.rr(d, (330, 200, 460, 250), fill=ctx.TILE, outline=ctx.LINE, w=1, r=8); ctx.ct(d, 395, 225, '< BACK', ctx.F_NM, ctx.ACC)
    ctx.ct(d, 240, 288, 'code generated offline on-device', ctx.F_TINY, ctx.DIM)


def _touch_detail(tx, ty, ctx):
    global _view, _buf, _del_arm, _accounts, _sel, _scroll
    if 200 <= ty <= 250:
        if tx <= 150 and ctx.debounce(0.3):                             # RENAME
            _buf = _accounts[_sel].get('name', '') if 0 <= _sel < len(_accounts) else ''
            _view = 'rename'; _del_arm = 0.0; ctx.mark_dirty(); return
        if 175 <= tx <= 305 and ctx.debounce(0.3):                      # DELETE (tight bounds)
            if time.time() - _del_arm < 3:
                if 0 <= _sel < len(_accounts):
                    del _accounts[_sel]
                    if not _save(): _flash('save failed - may reappear on reboot')
                _sel = -1; _scroll = min(_scroll, max(0, len(_accounts) - _L_ROWS))
                _view = 'list'; _del_arm = 0.0
            else:
                _del_arm = time.time()
            ctx.mark_dirty(); return
        if tx >= 330 and ctx.debounce(0.3):                             # < BACK (to list)
            _view = 'list'; _del_arm = 0.0; ctx.mark_dirty(); return


# ---------------- view: ADD / RENAME (keyboard) ----------------
def _draw_input(d, ctx):
    d.rectangle((0, 0, ctx.W, ctx.H), fill=ctx.BG)
    if _view == 'rename':
        title, act = 'RENAME ACCOUNT', 'SAVE'
    elif _field == 'secret':
        title, act = 'ADD  -  SECRET KEY', 'NEXT >'
    else:
        title, act = 'ADD  -  ACCOUNT NAME', 'SAVE'
    _hdr(d, ctx, title)
    ctx.rr(d, (6, 42, 474, 70), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=6)
    show = _buf + ('_' if int(time.time() * 2) % 2 else '')
    ctx.lt(d, 14, 56, _crop(d, ctx, show or 'type here...', 452, ctx.F_NM), ctx.F_NM,
           ctx.FG if _buf else ctx.DIM)
    for r, row in enumerate(_ROWS):
        y = _ROW_Y[r]
        for c, ch in enumerate(row):
            x = 2 + c * 48
            ctx.rr(d, (x, y, x + 44, y + 26), fill=ctx.TILE, outline=ctx.LINE, w=1, r=5)
            ctx.ct(d, x + 22, y + 13, ch, ctx.F_SM, ctx.FG)
    ctx.rr(d, (2, 194, 300, 222), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6); ctx.ct(d, 151, 208, 'SPACE', ctx.F_SM, ctx.DIM)
    ctx.rr(d, (306, 194, 478, 222), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6); ctx.ct(d, 392, 208, 'BKSP', ctx.F_SM, ctx.FG)
    ctx.rr(d, (6, 228, 158, 262), fill=(110, 75, 45), r=7); ctx.ct(d, 82, 245, 'CANCEL', ctx.F_NM, (255, 232, 214))
    ctx.rr(d, (322, 228, 474, 262), fill=(30, 120, 78), r=7); ctx.ct(d, 398, 245, act, ctx.F_NM, (230, 255, 236))
    if _err and time.time() - _err_t < 4:
        ctx.ct(d, 240, 278, _err, ctx.F_SM, DANGER)
    elif _field == 'secret' and _view == 'add':
        ctx.ct(d, 240, 278, 'paste the base32 secret (letters A-Z and 2-7)', ctx.F_TINY, ctx.DIM)


def _touch_input(tx, ty, ctx):
    global _buf, _field, _in_secret, _view, _accounts
    for r, row in enumerate(_ROWS):
        y = _ROW_Y[r]
        if y <= ty <= y + 26:
            c = (tx - 2) // 48
            if 0 <= c < len(row) and ctx.debounce(0.07):
                _buf += row[c]; ctx.mark_dirty()
            return
    if 194 <= ty <= 222:
        if tx <= 300 and ctx.debounce(0.07): _buf += ' '; ctx.mark_dirty(); return
        if ctx.debounce(0.07): _buf = _buf[:-1]; ctx.mark_dirty(); return
        return
    if 228 <= ty <= 262:
        if tx <= 158 and ctx.debounce(0.3):                             # CANCEL
            _view = 'list'; _buf = ''; ctx.mark_dirty(); return
        if tx >= 322 and ctx.debounce(0.3):                             # NEXT / SAVE
            _commit(ctx); return


def _commit(ctx):
    global _field, _in_secret, _buf, _view, _accounts
    if _view == 'rename':
        if 0 <= _sel < len(_accounts):
            old = _accounts[_sel].get('name')
            _accounts[_sel]['name'] = _buf.strip() or 'unnamed'
            if not _save():
                _accounts[_sel]['name'] = old; _flash('save failed - name NOT changed'); ctx.mark_dirty(); return
        _view = 'detail'; _buf = ''; ctx.mark_dirty(); return
    if _field == 'secret':
        if not _valid_b32(_buf):
            _flash('invalid secret - base32 only (A-Z, 2-7)'); ctx.mark_dirty(); return
        _in_secret = _norm_b32(_buf); _field = 'name'; _buf = ''; ctx.mark_dirty(); return
    _accounts.append({'name': _buf.strip() or 'account %d' % (len(_accounts) + 1), 'secret': _in_secret})
    if not _save():
        _accounts.pop(); _flash('save failed - secret NOT stored'); ctx.mark_dirty(); return
    _in_secret = ''; _buf = ''; _view = 'list'; ctx.mark_dirty()


# ---------------- dispatch ----------------
def draw(d, ctx):
    {'add': _draw_input, 'rename': _draw_input,
     'detail': _draw_detail}.get(_view, _draw_list)(d, ctx)


def handle_touch(tx, ty, ctx):
    global _gen
    if ty <= 26 and tx >= 410 and ctx.debounce(0.3):     # HOME (top-right) -> dashboard
        _gen += 1                                        # stop our tick like on_exit
        ctx.back(); return
    {'add': _touch_input, 'rename': _touch_input,
     'detail': _touch_detail}.get(_view, _touch_list)(tx, ty, ctx)
