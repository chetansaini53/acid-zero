# Acid Zero plugin - "Password Lab": offline password-strength + crack-time teacher.
#
# Type or PASTE a password -> charset entropy, a strength meter, and estimated crack
# time under real attacker models (throttled login -> bcrypt-GPU -> an MD5/NTLM Hashcat
# rig -> a cloud cluster), plus the specific weaknesses that make it fall to a wordlist
# attack regardless of length. GEN suggests a passphrase. 100% offline, pure-stdlib.
# Educational - shows WHY 'Password123' dies in an instant. Own-lab use only.
import math
import random
import re
import threading
import time

META = {'name': 'Password Lab', 'icon': 'key', 'color': (235, 180, 90)}

CLIP = '/run/acid_clip.txt'

# (label, guesses/sec) - realistic 2024-ish rates
MODELS = [('Online, throttled', 1e2), ('Offline, bcrypt-GPU', 1e4),
          ('Offline, MD5/NTLM rig', 1e11), ('Offline, cloud cluster', 1e13)]

COMMON = {'password', 'password1', 'password123', '123456', '12345678', '123456789', 'qwerty',
          'qwerty123', 'abc123', 'letmein', 'admin', 'admin123', 'welcome', 'iloveyou', 'monkey',
          'dragon', 'football', 'baseball', 'master', 'sunshine', 'princess', 'login', 'passw0rd',
          '000000', '111111', '1234', '12345', 'trustno1', 'superman', 'batman', 'shadow', 'ninja',
          'hello', 'whatever', 'access', 'flower', 'hottie', 'loveme', 'zaq12wsx', 'qazwsx'}
SEQ = ['qwerty', 'asdf', 'zxcv', 'qwertz', '1234', '2345', '3456', 'abcd', 'bcde', '0000', '1111', 'aaaa']
WORDS = ('atlas orbit maple cipher tundra ember willow quartz nomad pixel raven cobalt lunar delta '
         'onyx harbor vertex zephyr saffron thistle canyon meadow falcon jasper cedar mango violet '
         'copper sable amber flint garnet ivory basil clover dune fable glacier hazel indigo koala '
         'lotus mocha nectar opal pepper rune slate topaz umber vex wren xenon yarn zeal').split()

_pw = ''
_msg = ''
_kbd = False
_tpage = 'abc'
_KP = {'abc': ['qwertyuiop', 'asdfghjkl-', 'zxcvbnm+/='],
       '123': ['1234567890', '!@#$%^&*()', '-_=+[]{}|\\'],
       'sym': [':;\'"`,.<>?', '?/\\|&$*()[', ']}{=+-~^%@']}
_KY = [64, 100, 136]
_gen = 0


# ---------------- analysis ----------------
def _pool(pw):
    p = 0
    if re.search(r'[a-z]', pw): p += 26
    if re.search(r'[A-Z]', pw): p += 26
    if re.search(r'\d', pw): p += 10
    if re.search(r'[^A-Za-z0-9]', pw): p += 33
    return p


def _classes(pw):
    out = []
    if re.search(r'[a-z]', pw): out.append('lower')
    if re.search(r'[A-Z]', pw): out.append('UPPER')
    if re.search(r'\d', pw): out.append('digit')
    if re.search(r'[^A-Za-z0-9]', pw): out.append('sym')
    return out


def _weaknesses(pw):
    w = []
    low = pw.lower()
    if len(pw) < 8:
        w.append('under 8 characters')
    if len(_classes(pw)) <= 1:
        w.append('one character type only')
    if low in COMMON:
        w.append('in the top-common list')
    for s in SEQ:
        if s in low:
            w.append('sequence "%s"' % s); break
    if re.search(r'(.)\1\1', pw):
        w.append('3+ repeated characters')
    m = re.match(r'^([A-Za-z]+)([\d!@#$%^&*]+)$', pw)
    if m and len(m.group(1)) <= 12:
        w.append('word+digits pattern (wordlist bait)')
    return w


def _human(sec):
    if sec == float('inf') or sec > 4e17:
        return '> age of universe'
    if sec < 1:
        return 'instant'
    y = sec / 3.15e7
    if y >= 1e9:
        return '%.0e yr' % y
    if y >= 1:
        return '%.0f yr' % y
    d = sec / 86400
    if d >= 1:
        return '%.0f days' % d
    h = sec / 3600
    if h >= 1:
        return '%.0f hr' % h
    mnt = sec / 60
    if mnt >= 1:
        return '%.0f min' % mnt
    return '%.0f sec' % sec


def analyze(pw):
    pool = _pool(pw)
    bits = len(pw) * math.log2(pool) if pool and pw else 0.0
    weak = _weaknesses(pw)
    # score 0..4 from brute-force bits, capped hard if a wordlist weakness exists
    if bits < 28: score = 0
    elif bits < 40: score = 1
    elif bits < 60: score = 2
    elif bits < 90: score = 3
    else: score = 4
    wordlist_bait = ('in the top-common list' in weak
                     or 'word+digits pattern (wordlist bait)' in weak
                     or any('sequence' in x for x in weak))
    if wordlist_bait:
        score = min(score, 1)
    log10g = bits * math.log10(2) - math.log10(2) if bits else -9   # avg = space/2
    times = []
    for name, rate in MODELS:
        ls = log10g - math.log10(rate)
        sec = 10 ** ls if ls < 300 else float('inf')
        times.append((name, _human(sec) if not wordlist_bait else 'instant*'))
    return {'pool': pool, 'bits': bits, 'weak': weak, 'score': score,
            'times': times, 'bait': wordlist_bait, 'classes': _classes(pw)}


def _passphrase():
    ws = [random.choice(WORDS) for _ in range(4)]
    return '-'.join(ws), 4 * math.log2(len(WORDS))


# ---------------- lifecycle ----------------
def on_enter(ctx):
    global _kbd, _gen, _msg
    _kbd = False; _msg = ''
    _gen += 1
    threading.Thread(target=_tick, args=(ctx, _gen), daemon=True).start()
    ctx.mark_dirty()


def on_exit(ctx):
    global _gen
    _gen += 1


def _tick(ctx, gen):
    while gen == _gen:
        time.sleep(0.5)
        try: ctx.mark_dirty()
        except Exception: break


def _paste():
    global _pw
    try:
        with open(CLIP, encoding='utf-8') as f:
            _pw = (_pw + f.read().split('\n')[0]).strip()[:64]
    except Exception:
        pass


# ---------------- draw ----------------
BAR_COL = [(225, 70, 70), (235, 140, 60), (235, 200, 70), (120, 210, 120), (60, 200, 130)]
BAR_LBL = ['VERY WEAK', 'WEAK', 'FAIR', 'STRONG', 'VERY STRONG']


def _crop(d, ctx, txt, maxw, font, tail=False):
    txt = str(txt)
    if d.textlength(txt, font=font) <= maxw:
        return txt
    if tail:
        while txt and d.textlength('..' + txt, font=font) > maxw: txt = txt[1:]
        return '..' + txt
    while txt and d.textlength(txt + '..', font=font) > maxw: txt = txt[:-1]
    return txt + '..'


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


def _draw_analysis(d, ctx):
    a = analyze(_pw)
    sc = a['score']
    # strength bar
    ctx.rr(d, (4, 60, 476, 78), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=5)
    w = int((476 - 8) * (sc + 1) / 5)
    d.rounded_rectangle((6, 62, 6 + w, 76), radius=4, fill=BAR_COL[sc])
    ctx.ct(d, 6 + w // 2, 69, BAR_LBL[sc], ctx.F_SM, (16, 18, 24))   # sit on the filled bar, not the dark panel
    ctx.lt(d, 8, 92, '%.0f bits  ·  pool %d  ·  len %d  ·  %s' % (
        a['bits'], a['pool'], len(_pw), '+'.join(a['classes']) or '-'), ctx.F_TINY, ctx.DIM)
    # crack-time table
    ctx.lt(d, 8, 110, 'CRACK TIME  (avg, brute-force)', ctx.F_TINY, ctx.ACC)
    y = 126
    for name, t in a['times']:
        ctx.lt(d, 14, y, name, ctx.F_SM, ctx.FG)
        ctx.lt(d, 320, y, t, ctx.F_SM, (225, 90, 90) if t in ('instant', 'instant*') else
               ((235, 200, 80) if 'sec' in t or 'min' in t else (120, 210, 130)))
        y += 19
    # weaknesses / verdict
    if a['weak']:
        ctx.lt(d, 8, 206, 'WEAK SPOTS: ' + _crop(d, ctx, ', '.join(a['weak']), 460, ctx.F_TINY), ctx.F_TINY, (235, 130, 90))
        if a['bait']:
            ctx.lt(d, 8, 222, '* wordlist attack finds this INSTANTLY, whatever the length', ctx.F_TINY, (235, 90, 90))
    elif _pw:
        ctx.lt(d, 8, 206, 'no obvious weaknesses - brute-force times above apply', ctx.F_TINY, (120, 210, 130))
    else:
        ctx.lt(d, 8, 206, 'type or PASTE a password to analyse (offline, nothing leaves the device)', ctx.F_TINY, ctx.DIM)
    if _msg:
        ctx.lt(d, 8, 238, _crop(d, ctx, _msg, 460, ctx.F_TINY), ctx.F_TINY, (120, 200, 235))


def draw(d, ctx):
    d.rectangle((0, 0, ctx.W, ctx.H), fill=ctx.BG)
    d.rectangle((0, 0, ctx.W, 26), fill=ctx.BARBG); d.line([(0, 26), (ctx.W, 26)], fill=ctx.LINE)
    ctx.lt(d, 8, 13, 'PASSWORD LAB', ctx.F_TIT, ctx.FG)
    ctx.ct(d, 410, 13, 'offline  ·  educational', ctx.F_TINY, ctx.DIM)
    ctx.rr(d, (4, 30, 476, 54), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=5)
    cur = '_' if int(time.time() * 2) % 2 else ' '
    ctx.lt(d, 10, 42, 'pw', ctx.F_TINY, ctx.DIM)
    ctx.lt(d, 34, 42, _crop(d, ctx, (_pw + cur) if _pw else 'tap to type, or PASTE', 430, ctx.F_NM, tail=True),
           ctx.F_NM, ctx.FG if _pw else ctx.DIM)
    if _kbd:
        _draw_keyboard(d, ctx)
    else:
        _draw_analysis(d, ctx)
    ctx.rr(d, (4, 254, 117, 300), fill=(45, 80, 120), r=7); ctx.ct(d, 60, 277, 'PASTE', ctx.F_SM, (225, 240, 255))
    ctx.rr(d, (121, 254, 234, 300), fill=(70, 60, 46), r=7); ctx.ct(d, 177, 277, 'CLR', ctx.F_SM, (255, 235, 210))
    ctx.rr(d, (238, 254, 351, 300), fill=(40, 100, 80), r=7); ctx.ct(d, 294, 277, 'GEN PASS', ctx.F_SM, (225, 255, 240))
    ctx.rr(d, (355, 254, 476, 300), fill=(50, 56, 68), r=7); ctx.ct(d, 415, 277, 'HIDE KB' if _kbd else 'KEYBOARD', ctx.F_SM, ctx.ACC)


# ---------------- touch ----------------
def _touch_keyboard(tx, ty, ctx):
    global _pw, _tpage, _kbd
    for r, row in enumerate(_KP[_tpage]):
        y = _KY[r]
        if y <= ty <= y + 30:
            c = (tx - 8) // 46
            if 0 <= c < len(row) and ctx.debounce(0.07):
                _pw = (_pw + row[c])[:64]; ctx.mark_dirty()
            return
    if 172 <= ty <= 202:
        for x0, x1, pg in ((8, 118, 'abc'), (122, 232, '123'), (236, 346, 'sym')):
            if x0 <= tx <= x1 and ctx.debounce(0.2):
                _tpage = pg; ctx.mark_dirty(); return
        if tx >= 350 and ctx.debounce(0.07):
            _pw = _pw[:-1]; ctx.mark_dirty(); return
        return
    if 206 <= ty <= 236:
        if tx <= 346 and ctx.debounce(0.07): _pw = (_pw + ' ')[:64]; ctx.mark_dirty(); return
        if tx >= 350 and ctx.debounce(0.2): _kbd = False; ctx.mark_dirty(); return


def handle_touch(tx, ty, ctx):
    global _pw, _kbd, _msg
    if 254 <= ty <= 300:
        if tx <= 117 and ctx.debounce(0.25): _paste(); _msg = ''; ctx.mark_dirty(); return
        if tx <= 234 and ctx.debounce(0.25): _pw = ''; _msg = ''; ctx.mark_dirty(); return
        if tx <= 351 and ctx.debounce(0.25):
            ph, bits = _passphrase()
            _msg = 'try: %s  (~%.0f bits from this demo list; real diceware >=51)' % (ph, bits)
            ctx.mark_dirty(); return
        if ctx.debounce(0.2): _kbd = not _kbd; ctx.mark_dirty(); return
        return
    if 30 <= ty <= 54 and ctx.debounce(0.2):
        _kbd = True; ctx.mark_dirty(); return
    if _kbd:
        _touch_keyboard(tx, ty, ctx)
