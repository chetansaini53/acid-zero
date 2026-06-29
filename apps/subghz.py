# Acid Zero plugin - "Sub-GHz": one combined sci-fi RF interface via the ESP32
# + CC1101 co-processor (USB serial).
#   MAIN  : preset (freq/mod) + live waveform graph + stats + SCAN/AUTO/RECORD/
#           REPLAY/SAVE. SCAN identifies the preset, AUTO does identify+capture,
#           RECORD captures at the preset, REPLAY plays it, SAVE -> name keyboard.
#   SAVED : browse saved signals -> replay (exact freq+mod+raw).
# Educational / own-lab use only.
import os, sys, glob, threading
for _p in ('/usr/local/bin', '/usr/local/lib/acid-apps', '/home/ella3'):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    from acid_subghz import SubGhz, PROFILES
except Exception as _e:
    SubGhz = None
    PROFILES = ['AM_DEFAULT', 'AM_WIDE', 'AM_NARROW', 'FM_FSK']
    _IMPORT_ERR = _e

META = {'name': 'Sub-GHz', 'icon': 'radio', 'color': (175, 125, 235)}

SAVE_DIR = '/home/ella3/acid_subghz_saved'
PRESETS = [315.0, 433.92, 868.0, 915.0]
KB = ['1234567890', 'QWERTYUIOP', 'ASDFGHJKL', 'ZXCVBNM']

_sg = None
_busy = False
_status = 'SCAN to identify, AUTO/RECORD to capture'
_view = 'main'                 # 'main' | 'saved' | 'savename'
_freq = 433.92
_prof = 'AM_DEFAULT'
_pulses = 0
_frame = []
_rec_frames = 0
_an_rssi = None
_saved = []
_name = ''
_spawn_lock = threading.Lock()


# ---------- serial ----------
def _ensure():
    global _sg, _status
    if SubGhz is None:
        _status = 'acid_subghz module missing'; return False
    if _sg is not None and _sg.connected:
        return True
    try:
        _sg = SubGhz(); _sg.connect(); return True
    except Exception as e:
        _sg = None; _status = 'ESP32 not found: %s' % str(e)[:20]; return False


def _set(ctx, s):
    global _status
    _status = s
    try: ctx.mark_dirty()
    except Exception: pass


# ---------- saved library ----------
def _refresh_saved():
    global _saved
    out = []
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        for p in sorted(glob.glob(os.path.join(SAVE_DIR, '*.sub'))):
            try:
                toks = open(p).read().split()
                if len(toks) < 2:
                    continue
                fr = float(toks[0])
                if len(toks) >= 3 and toks[1] in PROFILES:
                    mod = toks[1]; cnt = len(toks) - 2
                else:
                    mod = 'AM_DEFAULT'; cnt = len(toks) - 1
                out.append((p, os.path.basename(p)[:-4], fr, mod, cnt))
            except Exception:
                pass
    except Exception:
        pass
    _saved = out


def _save_current(ctx, name=None):
    if not _frame:
        _set(ctx, 'nothing to save - record first'); return
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        if name:
            base = ''.join(c for c in name if c.isalnum() or c in '_-')[:16] or 'sig'
        else:
            n = 1
            while os.path.exists(os.path.join(SAVE_DIR, 'sig_%03d.sub' % n)):
                n += 1
            base = 'sig_%03d' % n
        path = os.path.join(SAVE_DIR, base + '.sub')
        k = 1
        while os.path.exists(path):
            path = os.path.join(SAVE_DIR, '%s_%d.sub' % (base, k)); k += 1
        with open(path, 'w') as f:
            f.write('%.2f %s ' % (_freq, _prof) + ' '.join(map(str, _frame)))
        _refresh_saved()
        _set(ctx, 'saved %s (%.2f %s)' % (os.path.basename(path)[:-4], _freq, _prof))
    except Exception as e:
        _set(ctx, 'save err: %s' % str(e)[:22])


# ---------- workers ----------
def _w_analyze(ctx):
    """SCAN: identify the full preset (frequency + modulation)."""
    global _busy, _an_rssi, _freq, _prof
    try:
        if not _ensure():
            return
        _set(ctx, 'PRESS REMOTE - scanning...')
        pf, pr, _rows = _sg.analyze()
        _an_rssi = pr
        if pf and pr is not None and pr > -62:
            _freq = pf
            _sg.set_config(freq=_freq)
            g = (_sg.classify().get('guess') or '').upper()
            _prof = 'FM_FSK' if ('FSK' in g or 'FM' in g) else 'AM_NARROW'
            _sg.set_profile(_prof)
            _set(ctx, 'PRESET %.2f MHz  %s  @%d dBm' % (pf, _prof, pr))
        else:
            _set(ctx, 'no strong peak (best %s dBm)' % (pr,))
    except Exception as e:
        _set(ctx, 'scan err: %s' % str(e)[:22])
    finally:
        _busy = False; ctx.mark_dirty()


def _capture_store(ctx, label):
    _sg.set_config(freq=_freq)
    _sg.set_profile(_prof)
    _set(ctx, 'PRESS REMOTE - %s @ %.2f %s' % (label, _freq, _prof))
    vals = _sg.capture(8)
    nf = sum(1 for d in vals if d > 4000)
    frame = vals[:400]
    if frame:
        try:
            with open('/home/ella3/acid_sub_frame.txt', 'w') as f:
                f.write(' '.join(map(str, frame)))
        except OSError:
            pass
    return frame, nf


def _w_record(ctx):
    global _busy, _pulses, _frame, _rec_frames
    try:
        if not _ensure():
            return
        frame, nf = _capture_store(ctx, 'recording')
        if frame:
            _frame = frame; _pulses = len(frame); _rec_frames = nf
            _set(ctx, 'REC %.2f %s  %dp  %dfr' % (_freq, _prof, _pulses, nf))
        else:
            _set(ctx, 'no signal - SCAN first / change MOD')
    except Exception as e:
        _set(ctx, 'record err: %s' % str(e)[:24])
    finally:
        _busy = False; ctx.mark_dirty()


def _w_auto(ctx):
    """AUTO: identify (freq+mod) then capture in one go."""
    global _busy, _pulses, _frame, _rec_frames, _an_rssi, _freq, _prof
    try:
        if not _ensure():
            return
        _set(ctx, 'AUTO: press remote - finding freq')
        pf, pr, _rows = _sg.analyze()
        _an_rssi = pr
        if pf and pr is not None and pr > -62:
            _freq = pf
        _sg.set_config(freq=_freq)
        g = (_sg.classify().get('guess') or '').upper()
        _prof = 'FM_FSK' if ('FSK' in g or 'FM' in g) else 'AM_NARROW'
        _sg.set_profile(_prof)
        frame, nf = _capture_store(ctx, 'recording')
        if frame:
            _frame = frame; _pulses = len(frame); _rec_frames = nf
            _set(ctx, 'AUTO %.2f %s %dp %dfr' % (_freq, _prof, _pulses, nf))
        else:
            _set(ctx, 'AUTO: no signal - retry')
    except Exception as e:
        _set(ctx, 'auto err: %s' % str(e)[:24])
    finally:
        _busy = False; ctx.mark_dirty()


def _w_replay(ctx):
    global _busy
    try:
        if not _ensure():
            return
        if not _frame:
            _set(ctx, 'record/load something first'); return
        _sg.set_config(freq=_freq)
        _sg.set_profile(_prof)
        _set(ctx, 'TRANSMITTING @ %.2f %s...' % (_freq, _prof))
        _sg.load(_frame); _sg.replay(2)
        _set(ctx, 'Replayed %d pulses @ %.2f' % (len(_frame), _freq))
    except Exception as e:
        _set(ctx, 'replay err: %s' % str(e)[:24])
    finally:
        _busy = False; ctx.mark_dirty()


def _w_save(ctx, name):
    global _busy
    try:
        _save_current(ctx, name)
    finally:
        _busy = False; ctx.mark_dirty()


def _w_load_replay(ctx, path):
    global _busy, _freq, _frame, _pulses, _prof
    try:
        toks = open(path).read().split()
        if len(toks) < 2:
            _set(ctx, 'corrupt .sub file'); return
        _freq = float(toks[0])
        if len(toks) >= 3 and toks[1] in PROFILES:
            _prof = toks[1]; _frame = [int(x) for x in toks[2:]]
        else:
            _prof = 'AM_DEFAULT'; _frame = [int(x) for x in toks[1:]]
        _pulses = len(_frame)
        if not _ensure():
            return
        _sg.set_config(freq=_freq)
        _sg.set_profile(_prof)
        _set(ctx, 'TX %s @ %.2f %s' % (os.path.basename(path)[:-4], _freq, _prof))
        _sg.load(_frame); _sg.replay(2)
        _set(ctx, 'Replayed %s' % os.path.basename(path)[:-4])
    except Exception as e:
        _set(ctx, 'play err: %s' % str(e)[:24])
    finally:
        _busy = False; ctx.mark_dirty()


def _w_delete(ctx, path):
    global _busy
    try:
        try:
            os.remove(path)
        except Exception:
            pass
        _refresh_saved(); _set(ctx, 'deleted')
    finally:
        _busy = False; ctx.mark_dirty()


def _spawn(ctx, fn, *a):
    global _busy
    with _spawn_lock:          # atomic test-and-set: no double-spawn
        if _busy:
            return
        _busy = True
    threading.Thread(target=fn, args=(ctx,) + a, daemon=True).start()


# ---------- lifecycle ----------
def on_enter(ctx):
    global _view
    _view = 'main'
    def _bg():                          # all I/O off the render thread
        global _frame, _pulses
        if not _frame:
            try:
                f = [int(x) for x in open('/home/ella3/acid_sub_frame.txt').read().split() if x.lstrip('-').isdigit()]
                if f:
                    _frame = f; _pulses = len(f)
            except Exception:
                pass
        _refresh_saved(); _ensure()
        try: ctx.mark_dirty()
        except Exception: pass
    threading.Thread(target=_bg, daemon=True).start()
    ctx.mark_dirty()


# ---------- draw helpers ----------
def _btn(ctx, d, box, label, fill, fg, font=None):
    ctx.rr(d, box, fill=fill, r=8)
    ctx.ct(d, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, label, font or ctx.F_NM, fg)


def _draw_wave(d, ctx, box, frame):
    x0, y0, x1, y1 = box
    ctx.rr(d, box, fill=(8, 14, 22), outline=ctx.LINE, w=1, r=6)
    midy = (y0 + y1) // 2
    for gx in range(x0 + 40, x1 - 4, 56):          # sci-fi grid
        d.line([(gx, y0 + 4), (gx, y1 - 4)], fill=(20, 36, 32), width=1)
    d.line([(x0 + 4, midy), (x1 - 4, midy)], fill=(20, 36, 32), width=1)
    if not frame:
        ctx.ct(d, (x0 + x1) // 2, midy, 'no signal captured', ctx.F_SM, ctx.DIM)
        return
    N = min(len(frame), 220)
    total = sum(frame[:N]) or 1
    w = x1 - x0 - 10
    yhi = y0 + 10; ylo = y1 - 10
    x = x0 + 5; level = 1
    poly = [(x, ylo)]
    for i in range(N):
        seg = max(1, int(w * frame[i] / total))
        yy = yhi if level else ylo
        poly.append((x, yy)); poly.append((x + seg, yy))
        x += seg; level ^= 1
        if x >= x1 - 5:
            break
    for i in range(len(poly) - 1):
        d.line([poly[i], poly[i + 1]], fill=ctx.ACC, width=2)


# ---------- view: MAIN (combined) ----------
def _draw_main(d, ctx):
    ctx.topbar(d, 'SUB-GHZ')
    _btn(ctx, d, (362, 3, 472, 25), 'SAVED', (45, 52, 68), ctx.ACC, ctx.F_SM)
    # preset
    ctx.rr(d, (8, 32, 234, 62), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
    ctx.lt(d, 16, 40, 'FREQ  (tap)', ctx.F_TINY, ctx.DIM)
    ctx.ct(d, 121, 54, '%.2f MHz' % _freq, ctx.F_SM, ctx.ACC)
    ctx.rr(d, (240, 32, 472, 62), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
    ctx.lt(d, 248, 40, 'MOD  (tap)', ctx.F_TINY, ctx.DIM)
    ctx.ct(d, 356, 54, _prof, ctx.F_SM, (235, 180, 40))
    # waveform graph (center)
    _draw_wave(d, ctx, (8, 66, 472, 176), _frame)
    # stats
    ctx.ct(d, 240, 193, 'RSSI %s   |   %d pulses   |   %d frames' % (
        (_an_rssi if _an_rssi is not None else '--'), _pulses, _rec_frames),
        ctx.F_SM, ctx.FG if _pulses else ctx.DIM)
    # action buttons
    busy = _busy
    _btn(ctx, d, (8, 208, 98, 250), 'SCAN', (120, 90, 200) if not busy else (60, 50, 90), (255, 255, 255), ctx.F_SM)
    _btn(ctx, d, (102, 208, 192, 250), 'AUTO', (70, 130, 235) if not busy else (50, 70, 110), (255, 255, 255), ctx.F_SM)
    _btn(ctx, d, (196, 208, 286, 250), 'RECORD', (225, 70, 70) if not busy else (120, 60, 60), (255, 255, 255), ctx.F_SM)
    _btn(ctx, d, (290, 208, 380, 250), 'REPLAY', (23, 150, 86) if (_frame and not busy) else (60, 80, 70), (240, 255, 246), ctx.F_SM)
    _btn(ctx, d, (384, 208, 472, 250), 'SAVE', (225, 170, 40) if (_frame and not busy) else (90, 80, 45), (30, 25, 5), ctx.F_SM)
    # status
    ctx.rr(d, (8, 256, 472, 288), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=6)
    ctx.ct(d, 240, 272, _status[:48], ctx.F_SM, (235, 180, 40) if busy else ctx.FG)


def _touch_main(tx, ty, ctx):
    global _view, _freq, _prof, _name
    if ty <= 25 and tx >= 362 and ctx.debounce(0.3):
        _refresh_saved(); _view = 'saved'; ctx.mark_dirty(); return
    if 32 <= ty <= 62:
        if tx <= 234 and ctx.debounce(0.3):
            try: i = PRESETS.index(min(PRESETS, key=lambda p: abs(p - _freq)))
            except Exception: i = 0
            _freq = PRESETS[(i + 1) % len(PRESETS)]; ctx.mark_dirty()
        elif tx >= 240 and ctx.debounce(0.3):
            try: i = PROFILES.index(_prof)
            except Exception: i = 0
            _prof = PROFILES[(i + 1) % len(PROFILES)]; ctx.mark_dirty()
    elif 208 <= ty <= 250:
        if tx <= 98 and ctx.debounce(0.5): _spawn(ctx, _w_analyze); ctx.mark_dirty()
        elif tx <= 192 and ctx.debounce(0.5): _spawn(ctx, _w_auto); ctx.mark_dirty()
        elif tx <= 286 and ctx.debounce(0.5): _spawn(ctx, _w_record); ctx.mark_dirty()
        elif tx <= 380 and ctx.debounce(0.5): _spawn(ctx, _w_replay); ctx.mark_dirty()
        elif ctx.debounce(0.4):
            if _frame:
                _name = ''; _view = 'savename'; ctx.mark_dirty()
            else:
                _set(ctx, 'record something first')


# ---------- view: SAVED ----------
def _draw_saved(d, ctx):
    ctx.topbar(d, 'SAVED SIGNALS')
    _btn(ctx, d, (362, 3, 472, 25), 'MAIN', (45, 52, 68), ctx.ACC, ctx.F_SM)
    if not _saved:
        ctx.ct(d, 240, 140, 'no saved signals yet', ctx.F_NM, ctx.DIM)
        ctx.ct(d, 240, 164, 'capture on MAIN, then SAVE', ctx.F_SM, ctx.DIM)
        return
    y = 36
    for path, name, fr, mod, cnt in _saved[:8]:
        ctx.rr(d, (10, y, 420, y + 28), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
        ctx.lt(d, 16, y + 14, name[:14], ctx.F_SM, ctx.FG)
        ctx.lt(d, 150, y + 14, '%.2f' % fr, ctx.F_SM, ctx.ACC)
        ctx.lt(d, 230, y + 14, mod[:9], ctx.F_TINY, (235, 180, 40))
        ctx.lt(d, 350, y + 14, '%dp' % cnt, ctx.F_TINY, ctx.DIM)
        ctx.rr(d, (426, y, 470, y + 28), fill=(120, 40, 48), r=6)
        ctx.ct(d, 448, y + 14, 'X', ctx.F_SM, (255, 220, 220))
        y += 32
    ctx.ct(d, 240, ctx.H - 22, _status[:46], ctx.F_SM, (235, 180, 40) if _busy else ctx.DIM)
    ctx.lt(d, 14, ctx.H - 9, 'tap row = PLAY   |   X = delete', ctx.F_TINY, ctx.DIM)


def _touch_saved(tx, ty, ctx):
    global _view
    if ty <= 25 and tx >= 362 and ctx.debounce(0.3):
        _view = 'main'; ctx.mark_dirty(); return
    if 36 <= ty <= 292:
        idx = (ty - 36) // 32
        if 0 <= idx < len(_saved):
            path = _saved[idx][0]
            if tx >= 426:
                if ctx.debounce(0.4):
                    _spawn(ctx, _w_delete, path); ctx.mark_dirty()
            elif ctx.debounce(0.5):
                _spawn(ctx, _w_load_replay, path); ctx.mark_dirty()


# ---------- view: SAVE NAME (keyboard) ----------
def _draw_savename(d, ctx):
    ctx.topbar(d, 'SAVE AS')
    ctx.rr(d, (8, 34, 472, 70), fill=(8, 14, 22), outline=ctx.ACC, w=1, r=6)
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
                if len(_name) < 16:
                    _name += row[ci]
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
                _view = 'main'
                _spawn(ctx, _w_save, nm)
                ctx.mark_dirty()


# ---------- dispatch ----------
def draw(d, ctx):
    {'saved': _draw_saved, 'savename': _draw_savename}.get(_view, _draw_main)(d, ctx)


def handle_touch(tx, ty, ctx):
    {'saved': _touch_saved, 'savename': _touch_savename}.get(_view, _touch_main)(tx, ty, ctx)
