# Acid Zero plugin - "IR Remote": capture / replay / presets, via the ESP32
# co-processor (IRremoteESP8266 on GPIO13 TX / GPIO14 RX). Saves in Flipper
# .ir format -> full interop with Flipper remote databases.
#
# Flipper-style hierarchy: REMOTES (each a .ir file with a name, e.g. "Living
# Room TV") each containing multiple named BUTTONS (Power, Vol+, ...), each
# with a play/replay action. Not a flat list of individual signals.
#
# SAVE_DIR is browsed as nested FOLDERS, one directory at a time (like
# Flipper's own Infrared app / SD card layout, e.g. TVs/Samsung.ir) - a
# pasted-in Flipper community database is thousands of files deep, so the
# browser only ever scans the currently-open folder, never the whole tree.
#
# Educational / own-lab use only.
import os, sys, threading
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
_status = 'RECORD a remote, or use REMOTES'
_view = 'main'          # main | browse | remote | presets | savename
_last = None             # last captured/loaded signal dict (Flipper-shaped)
_wave = []                # pulse list for the graph

_browse_rel = ''             # current folder, relative to SAVE_DIR ('' = root), '/' separated
_browse_mode = 'view'          # 'view' (REMOTES - open to play) | 'pick' (SAVE - open to attach)
_browse_entries = []            # [(is_dir, abs_path, name, count), ...] of the CURRENT folder only
_browse_page = 0
_BROWSE_PER_PAGE = 7             # rows/page (no header button eating space)
_PICK_ROOT_PER_PAGE = 6           # rows/page at pick-mode root (the "+ NEW REMOTE" button eats space)
_remote_path = None         # currently open remote's file
_remote_name = ''            # currently open remote's display name
_remote_buttons = []          # [(idx, name, label, sig), ...] - buttons inside the open remote

_save_ctx = None    # ('new_remote',) | ('add_button', path) - what savename is naming
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


def _sanitize(name):
    return ''.join(c for c in (name or '') if c.isalnum() or c in '_-')[:16]


def _unique_path(base):
    path = os.path.join(SAVE_DIR, base + '.ir')
    k = 1
    while os.path.exists(path):
        path = os.path.join(SAVE_DIR, '%s_%d.ir' % (base, k)); k += 1
    return path


def _rel_join(rel, name):
    return (rel + '/' + name) if rel else name


def _rel_up(rel):
    return rel.rsplit('/', 1)[0] if '/' in rel else ''


def _browse_abs(rel):
    return os.path.join(SAVE_DIR, *rel.split('/')) if rel else SAVE_DIR


# ---------- remotes (.ir files, each holding multiple named buttons) ----------
def _refresh_browse():
    """Scans ONE directory (the currently-open browse folder) - never the
    whole tree. A pasted-in Flipper community DB is ~2000 files deep; eagerly
    parsing all of them took ~4s on a Pi 3B+, which read as a UI freeze."""
    global _browse_entries
    out = []
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        base = _browse_abs(_browse_rel)
        with os.scandir(base) as it:
            items = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
        for e in items:
            try:
                if e.is_dir():
                    with os.scandir(e.path) as sub:
                        n = sum(1 for _ in sub)
                    out.append((True, e.path, e.name, n))
                elif e.name.endswith('.ir'):
                    out.append((False, e.path, e.name[:-3], len(_load_sigs(e.path))))
            except Exception:
                pass
    except Exception:
        pass
    _browse_entries = out


def _refresh_remote_buttons():
    global _remote_buttons
    out = []
    if _remote_path:
        try:
            for i, s in enumerate(_load_sigs(_remote_path)):
                out.append((i, s.get('name', '?')[:14], _label(s), s))
        except Exception:
            pass
    _remote_buttons = out


def _load_sigs(path):
    if not proto or not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return proto.parse_ir(f.read())
    except Exception:
        return []


def _create_remote(ctx, name):
    """New remote file; if a signal is already captured (_last), it becomes
    the remote's first named button (same name as the remote, kept simple)."""
    global _remote_path, _remote_name
    if proto is None:
        _set(ctx, 'ir_proto missing'); return
    base = _sanitize(name) or 'remote'
    path = _unique_path(base)
    sigs = []
    if _last:
        sig = dict(_last); sig['name'] = base
        sigs.append(sig)
    with open(path, 'w') as f:
        f.write(proto.dump_ir(sigs))
    _remote_path = path; _remote_name = base
    _refresh_browse(); _refresh_remote_buttons()
    _set(ctx, 'created "%s" (%d button%s)' % (base, len(sigs), '' if len(sigs) == 1 else 's'))


def _add_button(ctx, path, btn_name):
    """Append _last as a new named button into an existing remote file."""
    if proto is None:
        _set(ctx, 'ir_proto missing'); return
    if not _last:
        _set(ctx, 'nothing captured - RECORD first'); return
    sigs = _load_sigs(path)
    sig = dict(_last); sig['name'] = _sanitize(btn_name) or 'btn'
    sigs.append(sig)
    with open(path, 'w') as f:
        f.write(proto.dump_ir(sigs))
    _refresh_browse()
    if _remote_path == path:
        _refresh_remote_buttons()
    _set(ctx, 'added "%s"' % sig['name'])


def _delete_remote(path):
    try: os.remove(path)
    except Exception: pass
    _refresh_browse()


def _delete_button(path, idx):
    sigs = _load_sigs(path)
    if 0 <= idx < len(sigs):
        del sigs[idx]
        try:
            with open(path, 'w') as f:
                f.write(proto.dump_ir(sigs))
        except Exception:
            pass
    _refresh_browse()
    if _remote_path == path:
        _refresh_remote_buttons()


# ---------- workers ----------
def _w_record(ctx):
    global _busy, _last, _wave
    try:
        if not _ensure():
            return
        _set(ctx, 'POINT REMOTE + PRESS a button...')
        sig = _ir.capture(8)
        if sig and sig.get('data'):
            # Sub-GHz-style: ALWAYS keep the raw pulse train as the default - it
            # replays for ANY signal, including AC remotes the decoder reports as
            # UNKNOWN. Only upgrade to 'parsed' when signal_to_raw() can actually
            # re-encode that protocol; a 'parsed UNKNOWN' would make replay fail
            # with "cannot encode" (the exact AC-remote bug).
            _last = {'name': 'captured', 'type': 'raw',
                     'frequency': sig.get('freq', 38000), 'data': sig['data']}
            if sig.get('protocol'):
                cand = {'name': 'captured', 'type': 'parsed', 'protocol': sig['protocol'],
                        'address': sig.get('address', 0), 'command': sig.get('command', 0)}
                if proto and proto.signal_to_raw(cand):   # only if cleanly encodable
                    _last = cand
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


def _w_create_remote(ctx, name):
    global _busy, _view, _last, _wave
    try:
        _create_remote(ctx, name)
        _last = None; _wave = []   # consumed - clears the "pending capture" state
        _view = 'remote'
    finally:
        _busy = False; ctx.mark_dirty()


def _w_add_button(ctx, path, name):
    global _busy, _view, _last, _wave, _remote_path, _remote_name
    try:
        _add_button(ctx, path, name)
        _last = None; _wave = []   # consumed - clears the "pending capture" state
        # always land INSIDE the target remote (consistent whether we got here
        # from browsing -> open -> +RECORD, or MAIN -> SAVE -> pick an existing one)
        _remote_path = path
        _remote_name = os.path.basename(path)[:-3]
        _refresh_remote_buttons()
        _view = 'remote'
    finally:
        _busy = False; ctx.mark_dirty()


def _w_delete_remote(ctx, path):
    global _busy
    try:
        _delete_remote(path); _set(ctx, 'remote deleted')
    finally:
        _busy = False; ctx.mark_dirty()


def _w_delete_button(ctx, path, idx):
    global _busy
    try:
        _delete_button(path, idx); _set(ctx, 'button deleted')
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
    threading.Thread(target=lambda: (_ensure(), ctx.mark_dirty()), daemon=True).start()
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


def _play_icon(d, cx, cy, r, color):
    d.polygon([(cx - r * 0.6, cy - r), (cx - r * 0.6, cy + r), (cx + r, cy)], fill=color)


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


# ---------- view: MAIN (capture) ----------
def _draw_main(d, ctx):
    ctx.topbar(d, 'IR REMOTE')
    _btn(ctx, d, (286, 3, 366, 25), 'PRESETS', (60, 45, 35), (245, 180, 120), ctx.F_SM)
    _btn(ctx, d, (370, 3, 472, 25), 'REMOTES', (45, 52, 68), ctx.ACC, ctx.F_SM)
    _draw_wave(d, ctx, (8, 34, 472, 150), _wave)
    ctx.rr(d, (8, 156, 472, 186), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
    if _last:
        ctx.ct(d, 240, 165, _label(_last), ctx.F_SM, (245, 180, 120))
        ctx.ct(d, 240, 177, ('%s' % _last.get('name', 'signal'))[:44], ctx.F_TINY, ctx.DIM)
    else:
        ctx.ct(d, 240, 171, 'RECORD a button  ·  or open REMOTES / PRESETS', ctx.F_SM, ctx.DIM)
    busy = _busy
    _btn(ctx, d, (8, 194, 158, 240), 'RECORD', (225, 70, 70) if not busy else (120, 60, 60), (255, 255, 255))
    _btn(ctx, d, (162, 194, 316, 240), 'REPLAY', (23, 150, 86) if (_last and not busy) else (60, 80, 70), (240, 255, 246))
    _btn(ctx, d, (320, 194, 472, 240), 'SAVE', (225, 170, 40) if (_last and not busy) else (90, 80, 45), (30, 25, 5))
    ctx.rr(d, (8, 248, 472, 284), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=6)
    ctx.ct(d, 240, 266, _status[:48], ctx.F_SM, (235, 170, 40) if busy else ctx.FG)


def _touch_main(tx, ty, ctx):
    global _view, _name, _save_ctx, _browse_mode, _browse_rel, _browse_page
    if ty <= 25 and 286 <= tx <= 366 and ctx.debounce(0.3):
        _view = 'presets'; ctx.mark_dirty(); return
    if ty <= 25 and tx >= 370 and ctx.debounce(0.3):
        _browse_mode = 'view'; _browse_rel = ''; _browse_page = 0
        _refresh_browse(); _view = 'browse'; ctx.mark_dirty(); return
    if 194 <= ty <= 240:
        if tx <= 158 and ctx.debounce(0.5): _spawn(ctx, _w_record); ctx.mark_dirty()
        elif tx <= 316 and ctx.debounce(0.5): _spawn(ctx, _w_replay); ctx.mark_dirty()
        elif ctx.debounce(0.4):
            if not _last:
                _set(ctx, 'record something first'); return
            _browse_mode = 'pick'; _browse_rel = ''; _browse_page = 0
            try:
                with os.scandir(SAVE_DIR) as it:
                    has_any = next(it, None) is not None
            except Exception:
                has_any = False
            if has_any:
                _refresh_browse(); _view = 'browse'; ctx.mark_dirty()
            else:
                _name = ''; _save_ctx = ('new_remote',); _view = 'savename'; ctx.mark_dirty()


def _paged(count, page, per_page):
    total = max(1, (count + per_page - 1) // per_page)
    page = min(max(page, 0), total - 1)
    return page, total, page * per_page


def _draw_page_bar(d, ctx, y, page, total):
    ctx.rr(d, (10, y, 130, y + 28), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
    ctx.ct(d, 70, y + 14, '< PREV', ctx.F_SM, ctx.FG if page > 0 else ctx.DIM)
    ctx.ct(d, 240, y + 14, '%d / %d' % (page + 1, total), ctx.F_SM, ctx.FG)
    ctx.rr(d, (350, y, 470, y + 28), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
    ctx.ct(d, 410, y + 14, 'NEXT >', ctx.F_SM, ctx.FG if page < total - 1 else ctx.DIM)


def _touch_page_bar(tx, page, total, ctx):
    """Returns the new page index, or None if the tap wasn't on PREV/NEXT."""
    if tx <= 130 and page > 0 and ctx.debounce(0.25):
        return page - 1
    if tx >= 350 and page < total - 1 and ctx.debounce(0.25):
        return page + 1
    return None


# ---------- view: BROWSE (lazy folder browser - REMOTES / SAVE-TO-REMOTE) ----------
def _draw_browse(d, ctx):
    nested = bool(_browse_rel)
    at_pick_root = (_browse_mode == 'pick' and not nested)
    title = (_browse_rel.rsplit('/', 1)[-1].upper() if nested else
             ('SAVE TO REMOTE' if _browse_mode == 'pick' else 'REMOTES'))
    ctx.topbar(d, title[:20])
    corner = 'UP' if nested else ('CANCEL' if _browse_mode == 'pick' else 'MAIN')
    _btn(ctx, d, (370, 3, 472, 25), corner, (45, 52, 68), ctx.ACC, ctx.F_SM)

    list_top = 34
    if at_pick_root:
        _btn(ctx, d, (10, 34, 470, 62), '+ NEW REMOTE', (23, 150, 86), (240, 255, 246))
        list_top = 70

    per_page = _PICK_ROOT_PER_PAGE if at_pick_root else _BROWSE_PER_PAGE
    if not _browse_entries:
        ctx.ct(d, 240, (list_top + 258) // 2, 'empty folder', ctx.F_NM, ctx.DIM)
        return
    page, total, start = _paged(len(_browse_entries), _browse_page, per_page)
    y = list_top
    for is_dir, path, name, n in _browse_entries[start:start + per_page]:
        box_right = 470 if (is_dir or _browse_mode != 'view') else 420
        ctx.rr(d, (10, y, box_right, y + 28), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
        if is_dir:
            ctx.rr(d, (16, y + 8, 28, y + 20), fill=(90, 140, 225), r=4)
            ctx.lt(d, 36, y + 14, name[:20], ctx.F_SM, ctx.FG)
            ctx.lt(d, 300, y + 14, '%d item%s' % (n, '' if n == 1 else 's'), ctx.F_TINY, (150, 190, 240))
        else:
            ctx.lt(d, 16, y + 14, name[:20], ctx.F_SM, ctx.FG)
            ctx.lt(d, 300, y + 14, '%d btn%s' % (n, '' if n == 1 else 's'), ctx.F_TINY, (245, 180, 120))
            if _browse_mode == 'view':
                ctx.rr(d, (426, y, 470, y + 28), fill=(120, 40, 48), r=6)
                ctx.ct(d, 448, y + 14, 'X', ctx.F_SM, (255, 220, 220))
        y += 32
    if total > 1:
        _draw_page_bar(d, ctx, list_top + per_page * 32 + 4, page, total)
    elif _browse_mode == 'view':
        ctx.lt(d, 14, ctx.H - 9, 'tap = open folder/remote   |   X = delete', ctx.F_TINY, ctx.DIM)


def _touch_browse(tx, ty, ctx):
    global _view, _browse_rel, _browse_page, _remote_path, _remote_name, _name, _save_ctx
    nested = bool(_browse_rel)
    at_pick_root = (_browse_mode == 'pick' and not nested)
    if ty <= 25 and tx >= 370 and ctx.debounce(0.3):
        if nested:
            _browse_rel = _rel_up(_browse_rel); _browse_page = 0
            _refresh_browse(); ctx.mark_dirty()
        else:
            _view = 'main'; ctx.mark_dirty()
        return
    if at_pick_root and 34 <= ty <= 62 and ctx.debounce(0.3):
        _name = ''; _save_ctx = ('new_remote',); _view = 'savename'; ctx.mark_dirty(); return

    list_top = 70 if at_pick_root else 34
    per_page = _PICK_ROOT_PER_PAGE if at_pick_root else _BROWSE_PER_PAGE
    if not _browse_entries:
        return
    page, total, start = _paged(len(_browse_entries), _browse_page, per_page)
    bar_y = list_top + per_page * 32 + 4
    if total > 1 and bar_y <= ty <= bar_y + 28:
        newp = _touch_page_bar(tx, page, total, ctx)
        if newp is not None:
            _browse_page = newp; ctx.mark_dirty()
        return
    if list_top <= ty <= list_top + per_page * 32:
        idx = start + (ty - list_top) // 32
        if start <= idx < min(start + per_page, len(_browse_entries)):
            is_dir, path, name, n = _browse_entries[idx]
            if is_dir and ctx.debounce(0.3):
                _browse_rel = _rel_join(_browse_rel, name); _browse_page = 0
                _refresh_browse(); ctx.mark_dirty()
            elif not is_dir:
                is_delete_zone = (_browse_mode == 'view' and tx >= 426)
                if is_delete_zone and ctx.debounce(0.4):
                    _spawn(ctx, _w_delete_remote, path); ctx.mark_dirty()
                elif not is_delete_zone and ctx.debounce(0.4):
                    if _browse_mode == 'view':
                        _remote_path = path; _remote_name = name
                        _refresh_remote_buttons(); _view = 'remote'; ctx.mark_dirty()
                    else:
                        _name = ''; _save_ctx = ('add_button', path); _view = 'savename'; ctx.mark_dirty()


# ---------- view: REMOTE (buttons inside one open remote) ----------
def _draw_remote(d, ctx):
    ctx.topbar(d, _remote_name[:16] or 'REMOTE')
    _btn(ctx, d, (286, 3, 366, 25), '+ RECORD', (60, 45, 35), (245, 180, 120), ctx.F_TINY)
    _btn(ctx, d, (370, 3, 472, 25), 'REMOTES', (45, 52, 68), ctx.ACC, ctx.F_SM)
    pending = bool(_last)   # a freshly-captured, not-yet-added signal
    list_bottom = 262 if pending else 290
    if not _remote_buttons:
        ctx.ct(d, 240, 130, 'no buttons yet', ctx.F_NM, ctx.DIM)
        ctx.ct(d, 240, 154, 'tap + RECORD to add one', ctx.F_SM, ctx.DIM)
    else:
        y = 34
        for idx, name, lbl, sig in _remote_buttons[:7]:
            if y + 28 > list_bottom:
                break
            ctx.rr(d, (10, y, 420, y + 28), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
            ctx.lt(d, 16, y + 14, name[:14], ctx.F_SM, ctx.FG)
            ctx.lt(d, 190, y + 14, lbl[:18], ctx.F_TINY, (245, 180, 120))
            _play_icon(d, 385, y + 14, 8, (23, 150, 86))
            ctx.rr(d, (426, y, 470, y + 28), fill=(120, 40, 48), r=6)
            ctx.ct(d, 448, y + 14, 'X', ctx.F_SM, (255, 220, 220))
            y += 32
        if not pending:
            ctx.lt(d, 14, ctx.H - 9, 'tap = play button   |   X = delete', ctx.F_TINY, ctx.DIM)
    if pending:
        # clear, discoverable CTA - replaces the vague "tap anywhere" approach
        ctx.rr(d, (8, 270, 472, 300), fill=(225, 170, 40), r=8)
        ctx.ct(d, 240, 285, 'GOT SIGNAL - tap to ADD AS BUTTON', ctx.F_SM, (30, 25, 5))
    elif _busy:
        ctx.ct(d, 240, ctx.H - 22, _status[:52], ctx.F_TINY, (235, 170, 40))


def _touch_remote(tx, ty, ctx):
    global _view, _name, _save_ctx
    if ty <= 25 and 286 <= tx <= 366 and ctx.debounce(0.4):
        _spawn(ctx, _w_record); ctx.mark_dirty(); return
    if ty <= 25 and tx >= 370 and ctx.debounce(0.3):
        _refresh_browse(); _view = 'browse'; ctx.mark_dirty(); return
    if _last and 270 <= ty <= 300 and ctx.debounce(0.4):
        _name = ''; _save_ctx = ('add_button', _remote_path); _view = 'savename'; ctx.mark_dirty(); return
    if 34 <= ty <= 262:
        idx = (ty - 34) // 32
        if 0 <= idx < len(_remote_buttons[:7]):
            bidx, name, lbl, sig = _remote_buttons[idx]
            if tx >= 426 and ctx.debounce(0.4):
                _spawn(ctx, _w_delete_button, _remote_path, bidx); ctx.mark_dirty()
            elif tx < 420 and ctx.debounce(0.5):
                _spawn(ctx, _w_tx_signal, sig); ctx.mark_dirty()


# ---------- view: PRESETS ----------
def _draw_presets(d, ctx):
    ctx.topbar(d, 'UNIVERSAL PRESETS')
    _btn(ctx, d, (370, 3, 472, 25), 'MAIN', (45, 52, 68), ctx.ACC, ctx.F_SM)
    rows = proto.PRESETS if proto else []
    if not rows:
        ctx.ct(d, 240, 140, 'nothing here yet', ctx.F_NM, ctx.DIM); return
    y = 36
    for p in rows[:8]:
        ctx.rr(d, (10, y, 470, y + 28), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
        ctx.lt(d, 16, y + 14, p['name'][:16], ctx.F_SM, ctx.FG)
        ctx.lt(d, 220, y + 14, _label(p)[:22], ctx.F_TINY, (245, 180, 120))
        _play_icon(d, 445, y + 14, 8, (23, 150, 86))
        y += 32
    ctx.lt(d, 14, ctx.H - 9, 'tap = TRANSMIT (own devices only)', ctx.F_TINY, ctx.DIM)


def _touch_presets(tx, ty, ctx):
    global _view
    if ty <= 25 and tx >= 370 and ctx.debounce(0.3):
        _view = 'main'; ctx.mark_dirty(); return
    if 36 <= ty <= 292 and proto:
        idx = (ty - 36) // 32
        if 0 <= idx < len(proto.PRESETS[:8]) and ctx.debounce(0.5):
            _spawn(ctx, _w_tx_signal, dict(proto.PRESETS[idx])); ctx.mark_dirty()


# ---------- view: SAVE NAME (keyboard; context-aware via _save_ctx) ----------
def _draw_savename(d, ctx):
    title = 'NEW REMOTE NAME' if (_save_ctx and _save_ctx[0] == 'new_remote') else 'BUTTON NAME'
    ctx.topbar(d, title)
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
    global _name, _view, _save_ctx
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
            if ctx.debounce(0.3):
                _view = 'remote' if _remote_path else 'main'; ctx.mark_dirty()
        else:
            if ctx.debounce(0.3) and _save_ctx:
                nm = _name.strip()
                if _save_ctx[0] == 'new_remote':
                    _spawn(ctx, _w_create_remote, nm)
                elif _save_ctx[0] == 'add_button':
                    _spawn(ctx, _w_add_button, _save_ctx[1], nm)
                ctx.mark_dirty()


# ---------- dispatch ----------
def draw(d, ctx):
    {'browse': _draw_browse, 'remote': _draw_remote,
     'presets': _draw_presets, 'savename': _draw_savename}.get(_view, _draw_main)(d, ctx)


def handle_touch(tx, ty, ctx):
    {'browse': _touch_browse, 'remote': _touch_remote,
     'presets': _touch_presets, 'savename': _touch_savename}.get(_view, _touch_main)(tx, ty, ctx)
