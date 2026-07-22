# Acid Zero - shared on-screen keyboard / single-field text editor for plugins.
# One implementation, reused by every plugin that needs text entry (Flasher AP
# creds, Bad USB AP creds, ...). 480x320, ADS7846 touch. Stateful singleton.
#
# Host contract:
#   on_enter(ctx):            acid_kbd.close()          # clear any stale state
#   open an editor:           acid_kbd.start('SSID', current_value)
#   draw() when editing:      acid_kbd.draw(d, ctx)
#   handle_touch when editing: r = acid_kbd.touch(tx, ty, ctx)
#                              if r == 'editing': return
#                              if isinstance(r, tuple):  value = r[1]   # ('ok', value)
#                              # r == 'cancel' or ('ok', value) -> host leaves the kb view
#
# NOTE: the launcher intercepts a top-left tap (ty<=40 & tx<=160) on ANY plugin
# screen and returns Home *before* the plugin sees it, so the 'cancel' branch is
# a safety net; the normal exits are OK (commit) or the global back (-> Home).
_LOW = ['1234567890', 'qwertyuiop', 'asdfghjkl', 'zxcvbnm']
_UP = ['1234567890', 'QWERTYUIOP', 'ASDFGHJKL', 'ZXCVBNM']
_SYM = ['1234567890', '!@#$%^&*()', '-_=+.,:;/', '?~|<>[]{}']

_label = ''
_buf = ''
_shift = False
_sym = False
_open = False
_maxlen = 63


def start(label, initial='', maxlen=63):
    """Open the editor. maxlen matches the field's real limit (SSID 32, WPA2 PW 63)."""
    global _label, _buf, _shift, _sym, _open, _maxlen
    _label = label or ''
    _buf = initial or ''
    _shift = False
    _sym = False
    _open = True
    _maxlen = maxlen


def close():
    global _open, _buf
    _open = False
    _buf = ''


def active():
    return _open


def _rows():
    return _SYM if _sym else (_UP if _shift else _LOW)


def _key(d, ctx, box, label, col=None):
    ctx.rr(d, box, fill=col or (45, 52, 68), outline=ctx.LINE, w=1, r=6)
    ctx.ct(d, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, label, ctx.F_SM, ctx.FG)


def draw(d, ctx):
    # Plain header (no '< back' - the launcher's top-left Home gesture still works,
    # but drawing a back arrow here would misleadingly promise return-to-field).
    ctx.rr(d, (0, 0, ctx.W, 28), fill=ctx.PANEL)
    ctx.ct(d, ctx.W // 2, 14, (_label + '   -   OK to save')[:36], ctx.F_TIT, ctx.FG)
    ctx.rr(d, (8, 34, 472, 66), fill=ctx.PANEL, outline=ctx.ACC, w=1, r=6)
    shown = (_buf + '_') if _buf else 'type a value...'
    shown = shown[-42:] if len(shown) > 42 else shown   # scroll to the caret for long values
    ctx.lt(d, 16, 51, shown, ctx.F_NM, ctx.FG if _buf else ctx.DIM)
    ry = 76
    for row in _rows():
        for ci, ch in enumerate(row):
            bx = 8 + ci * 46
            ctx.rr(d, (bx, ry, bx + 44, ry + 34), fill=ctx.TILE, outline=ctx.LINE, w=1, r=5)
            ctx.ct(d, bx + 22, ry + 17, ch, ctx.F_SM, ctx.FG)
        ry += 38
    _key(d, ctx, (8, ry, 96, ry + 34), 'DEL', (120, 70, 70))
    _key(d, ctx, (102, ry, 210, ry + 34), 'SPACE')
    _key(d, ctx, (216, ry, 300, ry + 34), 'abc' if (_shift or _sym) else 'ABC')
    _key(d, ctx, (306, ry, 388, ry + 34), '#@!' if not _sym else 'abc')
    _key(d, ctx, (394, ry, 472, ry + 34), 'OK', (30, 90, 60))


def touch(tx, ty, ctx):
    """-> 'editing' while typing; ('ok', value) on OK. (Exit-without-save = the
    launcher's top-left Home gesture; there is no in-widget cancel to mis-handle.)"""
    global _buf, _shift, _sym
    ry = 76
    for row in _rows():
        if ry <= ty <= ry + 34:
            ci = (tx - 8) // 46
            if 0 <= ci < len(row) and ctx.debounce(0.08):
                if len(_buf) < _maxlen:
                    _buf += row[ci]
                ctx.mark_dirty()
            return 'editing'
        ry += 38
    if ry <= ty <= ry + 34:
        if tx <= 96:
            if ctx.debounce(0.08):
                _buf = _buf[:-1]
                ctx.mark_dirty()
        elif tx <= 210:
            if ctx.debounce(0.08) and len(_buf) < _maxlen:
                _buf += ' '
                ctx.mark_dirty()
        elif tx <= 300:
            if ctx.debounce(0.2):
                _shift = not _shift
                _sym = False
                ctx.mark_dirty()
        elif tx <= 388:
            if ctx.debounce(0.2):
                _sym = not _sym
                ctx.mark_dirty()
        else:
            if ctx.debounce(0.3):
                v = _buf.strip()
                close()
                return ('ok', v)
    return 'editing'
