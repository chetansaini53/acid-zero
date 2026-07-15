# Acid Zero plugin - "IR Remote": capture / replay / save / universal-remote
# presets, via the ESP32 co-processor (IRremoteESP8266 on GPIO13 TX / GPIO14 RX).
# Saves in Flipper .ir format -> full interop with Flipper remote databases.
# Educational / own-lab use only.
import os, sys, glob, threading
for _p in ('/usr/local/bin', '/usr/local/lib/acid-apps', '/home/ella3'):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    from acid_ir import AcidIR
except Exception:
    AcidIR = None
try:
    import ir_proto as proto
except Exception:
    proto = None

META = {'name': 'IR Remote', 'icon': 'ir', 'color': (235, 140, 90)}

SAVE_DIR = '/home/ella3/acid_ir_saved'
KB = ['1234567890', 'QWERTYUIOP', 'ASDFGHJKL', 'ZXCVBNM']

_ir = None
_busy = False
_status = 'RECORD a remote, or use PRESETS'
_view = 'main'                 # 'main' | 'saved' | 'presets' | 'savename'
_last = None                   # last captured/loaded signal dict (Flipper-shaped)
_wave = []                     # pulse list for the graph
_saved = []                    # [(path, idx, name, label, sig), ...]
_name = ''
_spawn_lock = threading.Lock()


def _set(ctx, s):
    global _status
    _status = s
    try: ctx.mark_dirty()
    except Exception: pass


def _ensure():
    global _ir, _status
    if AcidIR is None:
        _status = 'acid_ir module missing'; return False
    if _ir is not None and _ir.connected:
        return True
    try:
        _ir = AcidIR(); _ir.connect()
        # base CC1101 firmware answers PING but not IR_INFO -> warn if IR fw missing
        if 'IR_INFO' not in _ir.info():
            _status = 'flash the IR firmware first'
        return True
    except Exception as e:
        _ir = None; _status = 'ESP32 IR not found: %s' % str(e)[:18]; return False


def _label(sig):
    if sig.get('type') == 'parsed':
        return '%s a=%X c=%X' % (sig.get('protocol', '?'), sig.get('address', 0), sig.get('command', 0))
    return 'RAW %d edges' % len(sig.get('data', []))


# ---------- saved library (.ir files, incl. Flipper) ----------
def _refresh_saved():
    global _saved
    out = []
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        for p in sorted(glob.glob(os.path.join(SAVE_DIR, '*.ir'))):
            try:
                sigs = proto.parse_ir(open(p).read()) if proto else []
                for i, s in enumerate(sigs):
                    out.append((p, i, s.get('name', '?')[:14], _label(s), s))
            except Exception:
                pass
    except Exception:
        pass
    _saved = out


def _save_last(ctx, name=None):
    if not _last:
        _set(ctx, 'nothing to save - record first'); return
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        base = ''.join(c for c in (name or '') if c.isalnum() or c in '_-')[:16] or 'ir'
        path = os.path.join(SAVE_DIR, base + '.ir')
        k = 1
        while os.path.exists(path):
            path = os.path.join(SAVE_DIR, '%s_%d.ir' % (base, k)); k += 1
        sig = dict(_last); sig['name'] = base
        with open(path, 'w') as f:
            f.write(proto.dump_ir([sig]))
        _refresh_saved()
        _set(ctx, 'saved %s.ir (Flipper format)' % base)
    except Exception as e:
        _set(ctx, 'save err: %s' % str(e)[:22])


# ---------- workers ----------
def _w_record(ctx):
    global _busy, _last, _wave
    try:
        if not _ensure():
            return
        _set(ctx, 'POINT REMOTE + PRESS a button...')
        sig = _ir.capture(8)
        if sig and sig.get('data'):
            _last = {'name': 'captured', 'type': 'raw',
                     'frequency': sig.get('freq', 38000), 'data': sig['data']}
            if sig.get('protocol'):
                _last.update({'type': 'parsed', 'protocol': sig['protocol'],
                              'address': sig['address'], 'command': sig['command']})
            _wave = sig['data']
            _set(ctx, 'GOT: %s' % _label(_last))
        else:
            _set(ctx, 'no IR signal - point closer, retry')
    except Exception as e:
        _set(ctx, 'record err: %s' % str(e)[:24])
    finally:
        _busy = False; ctx.mark_dirty()


def _w_replay(ctx):
    global _busy
    try:
        if not _ensure():
            return
        if not _last:
            _set(ctx, 'record/select something first'); return
        _tx(ctx, _last)
    finally:
        _busy = False; ctx.mark_dirty()


def _tx(ctx, sig):
    """Convert any signal -> raw -> transmit (the one reliable TX path)."""
    if proto is None:
        _set(ctx, 'ir_proto missing'); return
    res = proto.signal_to_raw(sig)
    if not res:
        _set(ctx, 'cannot encode %s' % (sig.get('protocol') or '?')); return
    freq, raw = res
    if not raw:
        _set(ctx, 'empty signal'); return
    _set(ctx, 'TRANSMITTING %s...' % _label(sig))
    _ir.send_raw(freq, raw, reps=2)
    _set(ctx, 'sent %s' % _label(sig))


def _w_save(ctx, name):
    global _busy
    try:
        _save_last(ctx, name)
    finally:
        _busy = False; ctx.mark_dirty()


def _w_tx_signal(ctx, sig):
    global _busy, _last, _wave
    try:
        if not _ensure():
            return
        _last = dict(sig)
        r = proto.signal_to_raw(sig) if proto else None
        _wave = r[1] if r else sig.get('data', [])
        _tx(ctx, sig)
    finally:
        _busy = False; ctx.mark_dirty()


def _w_delete(ctx, path):
    global _busy
    try:
        try: os.remove(path)
        except Exception: pass
        _refresh_saved(); _set(ctx, 'deleted')
    finally:
        _busy = False; ctx.mark_dirty()


def _spawn(ctx, fn, *a):
    global _busy
    with _spawn_lock:
        if _busy:
            return
        _busy = True
    threading.Thread(target=fn, args=(ctx,) + a, daemon=True).start()


# ---------- lifecycle ----------
def on_enter(ctx):
    global _view
    _view = 'main'
    threading.Thread(target=lambda: (_refresh_saved(), _ensure(), ctx.mark_dirty()),
                     daemon=True).start()
    ctx.mark_dirty()


def on_exit(ctx):
    """Release the shared ESP32 serial port so Sub-GHz can claim it cleanly."""
    global _ir
    try:
        if _ir is not None:
            _ir.close()
    except Exception:
        pass
    _ir = None


# ---------- draw helpers ----------
def _btn(ctx, d, box, label, fill, fg, font=None):
    ctx.rr(d, box, fill=fill, r=8)
    ctx.ct(d, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, label, font or ctx.F_NM, fg)


def _draw_wave(d, ctx, box, data):
    x0, y0, x1, y1 = box
    ctx.rr(d, box, fill=(20, 12, 8), outline=ctx.LINE, w=1, r=6)
    yhi, ylo = y0 + 16, y1 - 12
    if not data:
        ctx.ct(d, (x0 + x1) // 2, (y0 + y1) // 2, 'no IR signal - RECORD', ctx.F_SM, ctx.DIM)
        return
    srt = sorted(p for p in data if p > 30)
    unit = srt[len(srt) // 6] if srt else 560
    ppx = 3.0 / max(unit, 1)
    gap_px = 14
    xL, xR = x0 + 7, x1 - 7
    ctx.lt(d, x0 + 9, y0 + 5, '%.1f ms   %d edges' % (sum(data) / 1000.0, len(data)),
           ctx.F_TINY, (235, 170, 110))
    x, level, prev = xL, 1, ylo        # IR raw starts with a MARK (carrier on)
    for dur in data:
        is_gap = (level == 0 and dur >= unit * 8)
        seg = gap_px if is_gap else max(1, int(dur * ppx))
        if x + seg > xR:
            break
        yy = yhi if level else ylo
        d.line([(x, prev), (x, yy)], fill=(245, 150, 70), width=2)
        d.line([(x, yy), (x + seg, yy)], fill=(90, 70, 60) if is_gap else (245, 150, 70), width=2)
        prev = yy; x += seg; level ^= 1
    d.line([(x, prev), (x, ylo)], fill=(245, 150, 70), width=1)


# ---------- view: MAIN ----------
def _draw_main(d, ctx):
    ctx.topbar(d, 'IR REMOTE')
    _btn(ctx, d, (286, 3, 366, 25), 'PRESETS', (60, 45, 35), (245, 180, 120), ctx.F_SM)
    _btn(ctx, d, (370, 3, 472, 25), 'SAVED', (45, 52, 68), ctx.ACC, ctx.F_SM)
    _draw_wave(d, ctx, (8, 34, 472, 150), _wave)
    # info strip
    ctx.rr(d, (8, 156, 472, 186), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
    if _last:
        ctx.ct(d, 240, 165, _label(_last), ctx.F_SM, (245, 180, 120))
        ctx.ct(d, 240, 177, ('%s' % _last.get('name', 'signal'))[:44], ctx.F_TINY, ctx.DIM)
    else:
        ctx.ct(d, 240, 171, 'RECORD a remote  ·  or open PRESETS / SAVED', ctx.F_SM, ctx.DIM)
    busy = _busy
    _btn(ctx, d, (8, 194, 158, 240), 'RECORD', (225, 70, 70) if not busy else (120, 60, 60), (255, 255, 255))
    _btn(ctx, d, (162, 194, 316, 240), 'REPLAY', (23, 150, 86) if (_last and not busy) else (60, 80, 70), (240, 255, 246))
    _btn(ctx, d, (320, 194, 472, 240), 'SAVE', (225, 170, 40) if (_last and not busy) else (90, 80, 45), (30, 25, 5))
    ctx.rr(d, (8, 248, 472, 284), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=6)
    ctx.ct(d, 240, 266, _status[:48], ctx.F_SM, (235, 170, 40) if busy else ctx.FG)


def _touch_main(tx, ty, ctx):
    global _view, _name
    if ty <= 25 and 286 <= tx <= 366 and ctx.debounce(0.3):
        _view = 'presets'; ctx.mark_dirty(); return
    if ty <= 25 and tx >= 370 and ctx.debounce(0.3):
        _refresh_saved(); _view = 'saved'; ctx.mark_dirty(); return
    if 194 <= ty <= 240:
        if tx <= 158 and ctx.debounce(0.5): _spawn(ctx, _w_record); ctx.mark_dirty()
        elif tx <= 316 and ctx.debounce(0.5): _spawn(ctx, _w_replay); ctx.mark_dirty()
        elif ctx.debounce(0.4):
            if _last: _name = ''; _view = 'savename'; ctx.mark_dirty()
            else: _set(ctx, 'record something first')


# ---------- view: SAVED ----------
def _draw_list(d, ctx, title, rows, tx_hint):
    ctx.topbar(d, title)
    _btn(ctx, d, (370, 3, 472, 25), 'MAIN', (45, 52, 68), ctx.ACC, ctx.F_SM)
    if not rows:
        ctx.ct(d, 240, 140, 'nothing here yet', ctx.F_NM, ctx.DIM); return
    y = 36
    for r in rows[:8]:
        ctx.rr(d, (10, y, 420, y + 28), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
        ctx.lt(d, 16, y + 14, r[0][:16], ctx.F_SM, ctx.FG)
        ctx.lt(d, 210, y + 14, r[1][:22], ctx.F_TINY, (245, 180, 120))
        if r[2]:
            ctx.rr(d, (426, y, 470, y + 28), fill=(120, 40, 48), r=6)
            ctx.ct(d, 448, y + 14, 'X', ctx.F_SM, (255, 220, 220))
        y += 32
    ctx.lt(d, 14, ctx.H - 9, tx_hint, ctx.F_TINY, ctx.DIM)


def _draw_saved(d, ctx):
    _draw_list(d, ctx, 'SAVED IR', [(n, lbl, True) for (_p, _i, n, lbl, _s) in _saved],
               'tap = TRANSMIT   |   X = delete')


def _touch_saved(tx, ty, ctx):
    global _view
    if ty <= 25 and tx >= 370 and ctx.debounce(0.3):
        _view = 'main'; ctx.mark_dirty(); return
    if 36 <= ty <= 292:
        idx = (ty - 36) // 32
        if 0 <= idx < len(_saved[:8]):
            path, i, name, lbl, sig = _saved[idx]
            if tx >= 426 and ctx.debounce(0.4):
                _spawn(ctx, _w_delete, path); ctx.mark_dirty()
            elif tx < 420 and ctx.debounce(0.5):
                _spawn(ctx, _w_tx_signal, sig); ctx.mark_dirty()


# ---------- view: PRESETS ----------
def _draw_presets(d, ctx):
    rows = [(p['name'], _label(p), False) for p in (proto.PRESETS if proto else [])]
    _draw_list(d, ctx, 'UNIVERSAL PRESETS', rows, 'tap = TRANSMIT (own devices only)')


def _touch_presets(tx, ty, ctx):
    global _view
    if ty <= 25 and tx >= 370 and ctx.debounce(0.3):
        _view = 'main'; ctx.mark_dirty(); return
    if 36 <= ty <= 292 and proto:
        idx = (ty - 36) // 32
        if 0 <= idx < len(proto.PRESETS[:8]) and ctx.debounce(0.5):
            _spawn(ctx, _w_tx_signal, dict(proto.PRESETS[idx])); ctx.mark_dirty()


# ---------- view: SAVE NAME (keyboard) ----------
def _draw_savename(d, ctx):
    ctx.topbar(d, 'SAVE AS (.ir)')
    ctx.rr(d, (8, 34, 472, 70), fill=(20, 12, 8), outline=ctx.ACC, w=1, r=6)
    ctx.lt(d, 16, 52, (_name + '_') if _name else 'type a name...', ctx.F_NM, ctx.FG if _name else ctx.DIM)
    ry = 78
    for row in KB:
        for ci, ch in enumerate(row):
            bx = 8 + ci * 46
            ctx.rr(d, (bx, ry, bx + 44, ry + 34), fill=ctx.TILE, outline=ctx.LINE, w=1, r=5)
            ctx.ct(d, bx + 22, ry + 17, ch, ctx.F_SM, ctx.FG)
        ry += 38
    _btn(ctx, d, (8, ry, 110, ry + 34), 'DEL', (120, 70, 70), (255, 230, 230), ctx.F_SM)
    _btn(ctx, d, (116, ry, 250, ry + 34), 'SPACE', (45, 52, 68), ctx.FG, ctx.F_SM)
    _btn(ctx, d, (256, ry, 358, ry + 34), 'CANCEL', (90, 80, 45), (30, 25, 5), ctx.F_SM)
    _btn(ctx, d, (364, ry, 472, ry + 34), 'OK', (23, 150, 86), (240, 255, 246), ctx.F_SM)


def _touch_savename(tx, ty, ctx):
    global _name, _view
    ry = 78
    for row in KB:
        if ry <= ty <= ry + 34:
            ci = (tx - 8) // 46
            if 0 <= ci < len(row) and ctx.debounce(0.12):
                if len(_name) < 16: _name += row[ci]
                ctx.mark_dirty()
            return
        ry += 38
    if ry <= ty <= ry + 34:
        if tx <= 110:
            if ctx.debounce(0.12): _name = _name[:-1]; ctx.mark_dirty()
        elif tx <= 250:
            if ctx.debounce(0.12) and len(_name) < 16: _name += '_'; ctx.mark_dirty()
        elif tx <= 358:
            if ctx.debounce(0.3): _view = 'main'; ctx.mark_dirty()
        else:
            if ctx.debounce(0.3):
                nm = _name.strip() or None
                _view = 'main'; _spawn(ctx, _w_save, nm); ctx.mark_dirty()


# ---------- dispatch ----------
def draw(d, ctx):
    {'saved': _draw_saved, 'presets': _draw_presets,
     'savename': _draw_savename}.get(_view, _draw_main)(d, ctx)


def handle_touch(tx, ty, ctx):
    {'saved': _touch_saved, 'presets': _touch_presets,
     'savename': _touch_savename}.get(_view, _touch_main)(tx, ty, ctx)
