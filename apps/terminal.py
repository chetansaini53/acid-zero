# Acid Zero plugin - "Terminal": a single-screen on-device shell for the 3.5" panel.
#
# Layout (one screen, no view-switching):
#   - dark OUTPUT pane (top-left), with a narrow right rail: UP / DOWN scroll + HIST
#   - HIST opens a tap-to-load command HISTORY list (its own UP/DOWN)
#   - a tall multi-line INPUT field with its own UP/DOWN rail to review a 2+ line command
#   - bottom action row: SYNC (pull laptop clipboard) · RUN · CLR · COPY · KBD
#
# Runs in the launcher's context (root). The one control between "a LAN peer can plant a
# command" and "root code-exec" is the human tap, so RUN never executes a command the
# user could not fully see: a command that overflows the input field must be scrolled to
# its end (the button reads REVIEW until then) before it will run. Own-lab use only.
import os
import subprocess
import textwrap
import threading
import time
import tempfile

META = {'name': 'Terminal', 'icon': 'term', 'color': (60, 200, 130)}

CLIP = '/run/acid_clip.txt'
RUN_TIMEOUT = 25
WRAPW = 60                           # output wrap (chars) for the wider pane
MAXLINES = 3000
HIST_MAX = 80

# --- forced dark palette (independent of the launcher theme) ---
BG = (10, 12, 15); HDR = (20, 24, 30); OUT_BG = (6, 8, 11); PANEL = (24, 28, 35)
TXT = (232, 237, 242); SUBTXT = (135, 146, 158); PROMPT = (120, 230, 150)
KEY_BG = (34, 40, 50); KEY_LINE = (60, 70, 84); ACC = (95, 180, 255)
RUN_BG = (25, 150, 90); RUN_BUSY = (150, 60, 60); AMBER = (200, 140, 40)
DIMBTN = (20, 24, 30)

# geometry
_OX0, _OY0, _OX1, _OY1 = 4, 30, 384, 200          # output pane (wider; narrow right rail)
_OUT_TOP, _OUT_LH = 34, 12
_OUT_ROWS = (_OY1 - _OUT_TOP) // _OUT_LH           # 13
_IX0, _IY0, _IX1, _IY1 = 4, 204, 384, 266          # tall multi-line input field
_IN_TOP, _IN_LH, _IN_ROWS = 210, 16, 3
_HROW_H = 26
_HTOP = 44                                          # history list start (clear of the back-zone)
_HROWS = (266 - _HTOP) // _HROW_H                   # 8 history rows

# on-screen keyboard overlay: 3 pages x 3 rows x 10 plain chars
_TPAGES = {
    'abc': ['qwertyuiop', 'asdfghjkl-', 'zxcvbnm_./'],
    '123': ['1234567890', '!@#$%^&*()', '-_=+[]{}|\\'],
    'sym': [':;\'"`,.<>?', '?/\\|&$*()[', ']}{=+-~^%@'],
}

_cmd = ''
_tpage = 'abc'
_out = ['']; _out_raw = ''; _scroll = 0
_rc = None; _busy = False
_kbd = False
_hview = False; _history = []; _hscroll = 0
_iscroll = 0; _imax_seen = 0                       # input review scroll + high-water mark
_iwrap = ['']; _ilen = 1; _reviewed = True         # recomputed every draw
_gen = 0


# ---------------- lifecycle ----------------
def on_enter(ctx):
    global _kbd, _hview, _busy, _out, _out_raw, _scroll, _iscroll, _imax_seen, _hscroll, _gen
    _gen += 1
    _kbd = False; _hview = False; _busy = False
    _out = ['']; _out_raw = ''; _scroll = 0
    _iscroll = 0; _imax_seen = 0; _hscroll = 0
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


def _changed():
    """Any edit to _cmd resets the review scroll/high-water so a new command must be re-seen."""
    global _iscroll, _imax_seen
    _iscroll = 0; _imax_seen = 0


# ---------------- clipboard + run ----------------
def _sync():
    global _cmd
    try:
        with open(CLIP, encoding='utf-8') as f:
            _cmd += f.read()
    except Exception:
        pass
    _changed()


def _copy_out(ctx):
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(CLIP), prefix='.acidtmp')
        try: os.write(fd, _out_raw.encode('utf-8'))
        finally: os.close(fd)
        os.replace(tmp, CLIP)
    except Exception:
        pass


def _wrap(text, width):
    lines = []
    for ln in text.replace('\r', '').split('\n'):
        if not ln:
            lines.append(''); continue
        for seg in textwrap.wrap(ln.expandtabs(4), width=width,
                                 drop_whitespace=False, replace_whitespace=False):
            lines.append(seg)
            if len(lines) >= MAXLINES:
                lines.append('... [truncated at %d lines]' % MAXLINES); return lines
    return lines or ['']


def _pxwrap(d, text, font, maxpx):
    """Char-level wrap by pixel width (commands have long unbroken tokens; word-wrap overflows)."""
    lines = []
    for para in text.replace('\r', '').replace('\t', '    ').split('\n'):
        if para == '':
            lines.append(''); continue
        cur = ''
        for ch in para:
            if d.textlength(cur + ch, font=font) <= maxpx:
                cur += ch
            else:
                lines.append(cur); cur = ch
                if len(lines) >= 1500:
                    return lines
        lines.append(cur)
    return lines or ['']


def _cmd_env():
    env = dict(os.environ)
    env['HOME'] = '/root'; env['USER'] = 'root'
    env['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/root/.cargo/bin'
    env.setdefault('LANG', 'C.UTF-8'); env['TERM'] = 'dumb'
    return env


def _worker(cmd, ctx, gen):
    global _out, _out_raw, _scroll, _busy, _rc
    try:
        p = subprocess.run(['/bin/bash', '-c', cmd], env=_cmd_env(),
                           capture_output=True, text=True, timeout=RUN_TIMEOUT)
        raw = (p.stdout or '') + (p.stderr or ''); rc = p.returncode
    except subprocess.TimeoutExpired:
        raw = '[timed out after %ds]\n' % RUN_TIMEOUT; rc = 124
    except Exception as e:
        raw = '[failed to run] %s\n' % e; rc = -1
    if gen != _gen:
        return
    _out_raw = raw
    _out = _wrap(raw if raw.strip() else '[no output]   (exit %d)' % rc, WRAPW)
    _rc = rc; _scroll = 0; _busy = False
    try: ctx.mark_dirty()
    except Exception: pass


def _run(ctx):
    global _busy, _cmd, _history
    cmd = _cmd.strip()
    if not cmd or _busy:
        return
    if not _history or _history[0] != cmd:
        _history.insert(0, cmd); del _history[HIST_MAX:]
    _busy = True; g = _gen
    _cmd = ''; _changed()
    ctx.mark_dirty()
    threading.Thread(target=_worker, args=(cmd, ctx, g), daemon=True).start()


def _maybe_run(ctx):
    """Gate: overflowing commands must be scrolled to the end (REVIEW) before they run."""
    global _iscroll
    cmd = _cmd.strip()
    if not cmd or _busy:
        return
    if _reviewed:
        _run(ctx)
    else:
        _iscroll = max(0, _ilen - _IN_ROWS)      # jump to the end to reveal it
        ctx.mark_dirty()


# ---------------- draw helpers ----------------
def _crop(d, text, font, maxpx, tail=False):
    t = text.replace('\n', ' | ')
    if d.textlength(t, font=font) <= maxpx:
        return t
    if tail:
        while t and d.textlength('..' + t, font=font) > maxpx:
            t = t[1:]
        return '..' + t
    while t and d.textlength(t + '..', font=font) > maxpx:
        t = t[:-1]
    return t + '..'


def _update_review(d, ctx):
    global _iwrap, _ilen, _iscroll, _imax_seen, _reviewed
    _iwrap = _pxwrap(d, '$ ' + _cmd, ctx.F_SM, 366)
    _ilen = len(_iwrap)
    maxs = max(0, _ilen - _IN_ROWS)
    if _iscroll > maxs:
        _iscroll = maxs
    _imax_seen = max(_imax_seen, _iscroll + _IN_ROWS)
    _reviewed = (_ilen <= _IN_ROWS) or (_imax_seen >= _ilen)


# ---------------- draw: OUTPUT + right rail ----------------
def _draw_output(d, ctx):
    ctx.rr(d, (_OX0, _OY0, _OX1, _OY1), fill=OUT_BG, outline=KEY_LINE, w=1, r=6)
    y = _OUT_TOP
    for ln in _out[_scroll:_scroll + _OUT_ROWS]:
        ctx.lt(d, 10, y, ln, ctx.F_TINY, TXT); y += _OUT_LH
    if len(_out) > _OUT_ROWS:
        ctx.ct(d, (_OX0 + _OX1) // 2, _OY1 - 9,
               '%d-%d/%d' % (_scroll + 1, min(_scroll + _OUT_ROWS, len(_out)), len(_out)),
               ctx.F_TINY, SUBTXT)
    ctx.rr(d, (388, 30, 476, 72), fill=KEY_BG, outline=KEY_LINE, w=1, r=6);  ctx.ct(d, 432, 51, '^', ctx.F_BIG, ACC)
    ctx.rr(d, (388, 76, 476, 118), fill=KEY_BG, outline=KEY_LINE, w=1, r=6); ctx.ct(d, 432, 97, 'v', ctx.F_BIG, ACC)
    ctx.rr(d, (388, 122, 476, 200), fill=(40, 46, 58), outline=KEY_LINE, w=1, r=6)
    ctx.ct(d, 432, 154, 'HIST', ctx.F_SM, TXT); ctx.ct(d, 432, 172, '(%d)' % len(_history), ctx.F_TINY, SUBTXT)


# ---------------- draw: INPUT + review rail ----------------
def _draw_input(d, ctx):
    over = _ilen > _IN_ROWS
    warn = over and not _reviewed
    ctx.rr(d, (_IX0, _IY0, _IX1, _IY1), fill=(14, 17, 22),
           outline=AMBER if warn else KEY_LINE, w=1, r=6)
    y = _IN_TOP
    for i, ln in enumerate(_iwrap[_iscroll:_iscroll + _IN_ROWS]):
        gi = _iscroll + i
        cur = '_' if (gi == _ilen - 1 and int(time.time() * 2) % 2) else ''
        ctx.lt(d, 10, y, ln + cur, ctx.F_SM, PROMPT if gi == 0 else TXT); y += _IN_LH
    en = over
    ctx.rr(d, (388, 204, 476, 234), fill=KEY_BG if en else DIMBTN, outline=KEY_LINE, w=1, r=6)
    ctx.ct(d, 432, 219, '^', ctx.F_NM, ACC if en else SUBTXT)
    ctx.rr(d, (388, 238, 476, 266), fill=KEY_BG if en else DIMBTN, outline=KEY_LINE, w=1, r=6)
    ctx.ct(d, 432, 252, 'v', ctx.F_NM, ACC if en else SUBTXT)


def _draw_buttons(d, ctx):
    if _busy:
        run_l, run_f = 'RUNNING', RUN_BUSY
    elif _ilen > _IN_ROWS and not _reviewed:
        run_l, run_f = 'REVIEW', AMBER
    else:
        run_l, run_f = 'RUN', RUN_BG
    btns = [('SYNC', (45, 80, 120)), (run_l, run_f), ('CLR', (70, 60, 46)),
            ('COPY', (45, 70, 100)), ('KBD', (50, 56, 68))]
    x = 4
    for label, fill in btns:
        ctx.rr(d, (x, 270, x + 90, 314), fill=fill, r=6)
        ctx.ct(d, x + 45, 292, label, ctx.F_SM, (235, 242, 250)); x += 94


# ---------------- draw: KEYBOARD overlay (covers output+input) ----------------
def _draw_keyboard(d, ctx):
    ctx.rr(d, (4, 30, 476, 266), fill=PANEL, outline=KEY_LINE, w=1, r=6)
    ctx.rr(d, (8, 34, 472, 58), fill=(14, 17, 22), outline=KEY_LINE, w=1, r=5)
    ctx.lt(d, 14, 46, '$', ctx.F_NM, PROMPT)
    ctx.lt(d, 28, 46, _crop(d, _cmd + '_', ctx.F_NM, 430, tail=True), ctx.F_NM, TXT)
    ys = [64, 100, 136]
    for r, row in enumerate(_TPAGES[_tpage]):
        yk = ys[r]
        for c, ch in enumerate(row):
            x = 8 + c * 46
            ctx.rr(d, (x, yk, x + 42, yk + 30), fill=KEY_BG, outline=KEY_LINE, w=1, r=5)
            ctx.ct(d, x + 21, yk + 15, ch, ctx.F_SM, TXT)
    for x0, x1, label, pg in ((8, 118, 'ABC', 'abc'), (122, 232, '123', '123'), (236, 346, 'SYM', 'sym')):
        on = _tpage == pg
        ctx.rr(d, (x0, 170, x1, 200), fill=(30, 120, 210) if on else KEY_BG, outline=KEY_LINE, w=1, r=6)
        ctx.ct(d, (x0 + x1) // 2, 185, label, ctx.F_SM, (240, 248, 255) if on else TXT)
    ctx.rr(d, (350, 170, 468, 200), fill=KEY_BG, outline=KEY_LINE, w=1, r=6); ctx.ct(d, 409, 185, 'Bksp', ctx.F_SM, TXT)
    ctx.rr(d, (8, 204, 346, 234), fill=KEY_BG, outline=KEY_LINE, w=1, r=6);  ctx.ct(d, 177, 219, 'SPACE', ctx.F_SM, SUBTXT)
    ctx.rr(d, (350, 204, 468, 234), fill=(25, 150, 90), r=6); ctx.ct(d, 409, 219, 'HIDE', ctx.F_SM, (240, 255, 246))


# ---------------- draw: HISTORY ----------------
def _draw_history(d, ctx):
    d.rectangle((0, 0, ctx.W, 26), fill=HDR)
    ctx.lt(d, 8, 5, 'HISTORY', ctx.F_TIT, TXT)
    ctx.ct(d, 300, 12, 'tap a command to load it', ctx.F_TINY, SUBTXT)
    if not _history:
        ctx.ct(d, 240, 140, 'no commands yet - run something first', ctx.F_SM, SUBTXT)
    else:
        y = _HTOP
        for cmd in _history[_hscroll:_hscroll + _HROWS]:
            ctx.rr(d, (4, y, 476, y + 24), fill=(18, 22, 28), outline=KEY_LINE, w=1, r=5)
            ctx.lt(d, 14, y + 12, '$ ' + _crop(d, cmd, ctx.F_SM, 452), ctx.F_SM, TXT)
            y += _HROW_H
    ctx.rr(d, (4, 270, 156, 314), fill=KEY_BG, outline=KEY_LINE, w=1, r=6);  ctx.ct(d, 80, 292, '^ UP', ctx.F_SM, ACC)
    ctx.rr(d, (160, 270, 312, 314), fill=KEY_BG, outline=KEY_LINE, w=1, r=6); ctx.ct(d, 236, 292, 'v DOWN', ctx.F_SM, ACC)
    ctx.rr(d, (316, 270, 476, 314), fill=(70, 60, 46), r=6); ctx.ct(d, 396, 292, 'CLOSE', ctx.F_SM, (255, 235, 210))


def draw(d, ctx):
    d.rectangle((0, 0, ctx.W, ctx.H), fill=BG)
    _update_review(d, ctx)
    if _hview:
        _draw_history(d, ctx); return
    d.rectangle((0, 0, ctx.W, 26), fill=HDR)
    ctx.lt(d, 8, 5, 'TERMINAL', ctx.F_TIT, TXT)
    if _busy:
        ctx.lt(d, 150, 7, 'running...', ctx.F_SM, (240, 210, 120))
    elif _rc is not None:
        ctx.lt(d, 150, 7, 'exit %d' % _rc, ctx.F_SM, (120, 230, 150) if _rc == 0 else (240, 140, 130))
    ctx.ct(d, 432, 12, 'own-lab · root', ctx.F_TINY, SUBTXT)
    if _kbd:
        _draw_keyboard(d, ctx)
    else:
        _draw_output(d, ctx); _draw_input(d, ctx)
    _draw_buttons(d, ctx)


# ---------------- touch ----------------
def _touch_history(tx, ty, ctx):
    global _hview, _hscroll, _cmd
    if 270 <= ty <= 314:
        if tx <= 156 and ctx.debounce(0.12):
            _hscroll = max(0, _hscroll - _HROWS); ctx.mark_dirty(); return
        if tx <= 312 and ctx.debounce(0.12):
            _hscroll = min(max(0, len(_history) - _HROWS), _hscroll + _HROWS); ctx.mark_dirty(); return
        if ctx.debounce(0.25):
            _hview = False; ctx.mark_dirty(); return
        return
    if _HTOP <= ty <= _HTOP + _HROWS * _HROW_H:
        idx = _hscroll + (ty - _HTOP) // _HROW_H
        if 0 <= idx < len(_history) and ctx.debounce(0.2):
            _cmd = _history[idx]; _changed(); _hview = False; ctx.mark_dirty()


def _touch_keyboard(tx, ty, ctx):
    global _cmd, _tpage, _kbd
    ys = [64, 100, 136]
    for r, row in enumerate(_TPAGES[_tpage]):
        yk = ys[r]
        if yk <= ty <= yk + 30:
            c = (tx - 8) // 46
            if 0 <= c < len(row) and ctx.debounce(0.08):
                _cmd += row[c]; _changed(); ctx.mark_dirty()
            return
    if 170 <= ty <= 200:
        for x0, x1, pg in ((8, 118, 'abc'), (122, 232, '123'), (236, 346, 'sym')):
            if x0 <= tx <= x1 and ctx.debounce(0.2):
                _tpage = pg; ctx.mark_dirty(); return
        if tx >= 350 and ctx.debounce(0.08):
            _cmd = _cmd[:-1]; _changed(); ctx.mark_dirty(); return
        return
    if 204 <= ty <= 234:
        if tx <= 346 and ctx.debounce(0.08):
            _cmd += ' '; _changed(); ctx.mark_dirty(); return
        if tx >= 350 and ctx.debounce(0.2):
            _kbd = False; ctx.mark_dirty(); return


def handle_touch(tx, ty, ctx):
    global _cmd, _kbd, _scroll, _iscroll, _hview, _hscroll
    if _hview:
        _touch_history(tx, ty, ctx); return
    if 270 <= ty <= 314:                              # bottom action row
        i = (tx - 4) // 94
        if i == 0 and ctx.debounce(0.25): _sync(); ctx.mark_dirty(); return
        if i == 1 and ctx.debounce(0.3):  _maybe_run(ctx); return
        if i == 2 and ctx.debounce(0.2):  _cmd = ''; _changed(); ctx.mark_dirty(); return
        if i == 3 and ctx.debounce(0.3):  _copy_out(ctx); ctx.mark_dirty(); return
        if i == 4 and ctx.debounce(0.2):  _kbd = not _kbd; ctx.mark_dirty(); return
        return
    if _kbd:
        _touch_keyboard(tx, ty, ctx); return
    if tx >= 388 and 30 <= ty <= 200:                 # output right rail
        if ty <= 72 and ctx.debounce(0.12):
            _scroll = max(0, _scroll - (_OUT_ROWS - 2)); ctx.mark_dirty(); return
        if ty <= 118 and ctx.debounce(0.12):
            _scroll = min(max(0, len(_out) - _OUT_ROWS), _scroll + (_OUT_ROWS - 2)); ctx.mark_dirty(); return
        if ty >= 122 and ctx.debounce(0.25):
            _hview = True; _hscroll = 0; ctx.mark_dirty(); return
        return
    if tx >= 388 and 204 <= ty <= 266:                # input review rail
        if ty <= 234 and ctx.debounce(0.1):
            _iscroll = max(0, _iscroll - 2); ctx.mark_dirty(); return
        if ctx.debounce(0.1):
            _iscroll = min(max(0, _ilen - _IN_ROWS), _iscroll + 2); ctx.mark_dirty(); return
        return
    if tx <= 384 and 204 <= ty <= 266 and ctx.debounce(0.2):   # tap the input field -> keyboard
        _kbd = True; ctx.mark_dirty(); return
