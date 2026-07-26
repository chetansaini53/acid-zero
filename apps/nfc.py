# Acid Zero plugin - "NFC" : read / save / write / emulate 13.56 MHz tags via the
# ACR122U USB reader (libnfc). Mirrors the IR Remote app's shape - a captured tag
# lands in _last, SAVE names it into a Flipper-style nested-folder library, and a
# saved card can be WRITTEN onto a blank or EMULATED (UID) for a Flipper to read.
#
# Save layout: each card is a small "<name>.nfc" metadata file (UID/type/keys),
# with its full-data dump alongside as "<name>.mfd" (Mifare) / "<name>.mfu"
# (Ultralight/NTAG) when the card had readable data. Browsed one folder at a time.
#
# Educational / own-lab use only.
import os, sys, shutil, threading, time
for _p in ('/usr/local/bin', '/usr/local/lib/acid-apps'):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    import acid_nfc as nfc
except Exception:
    nfc = None

META = {'name': 'NFC', 'icon': 'nfc', 'color': (90, 175, 235)}

SAVE_DIR = '/home/pi/acid_nfc_saved'
TMP_DUMP = '/tmp/acid_nfc_dump'
KB = ['1234567890', 'QWERTYUIOP', 'ASDFGHJKL', 'ZXCVBNM']

_emu = nfc.Emulator() if nfc else None
_busy = False
_status = 'place a tag, tap READ'
_reader = 'checking reader...'      # cached reader name; nfc-list is too slow to call per-frame
_view = 'main'          # main | browse | card | savename | emulate | info
_last = None             # freshly-read tag dict {uid,uid_spaced,atqa,sak,type,kind,dump}
_info_off = 0
_spawn_lock = threading.Lock()

_browse_rel = ''
_browse_entries = []            # [(is_dir, abs_path, name, meta_or_None), ...]
_browse_page = 0
_BROWSE_PER_PAGE = 7

_card = None             # currently-open saved card meta dict (+ '_path','_dump')
_name = ''
_emu_uid = ''


def _set(ctx, s):
    global _status
    _status = s
    try: ctx.mark_dirty()
    except Exception: pass


def _sanitize(name):
    return ''.join(c for c in (name or '') if c.isalnum() or c in '_-')[:16]


def _rel_join(rel, name):
    return (rel + '/' + name) if rel else name


def _rel_up(rel):
    return rel.rsplit('/', 1)[0] if '/' in rel else ''


def _browse_abs(rel):
    return os.path.join(SAVE_DIR, *rel.split('/')) if rel else SAVE_DIR


def _unique_path(base):
    path = os.path.join(_browse_abs(_browse_rel), base + '.nfc')
    k = 1
    while os.path.exists(path):
        path = os.path.join(_browse_abs(_browse_rel), '%s_%d.nfc' % (base, k)); k += 1
    return path


# ---------- card metadata (.nfc text file) ----------
def _dump_ext(kind):
    return '.mfu' if kind == 'mfu' else '.mfd'


def _write_meta(path, card):
    with open(path, 'w') as f:
        f.write('# Acid Zero NFC card\n')
        for k in ('uid', 'uid_spaced', 'type', 'kind', 'atqa', 'sak'):
            f.write('%s: %s\n' % (k, card.get(k, '')))
        f.write('dump: %s\n' % (os.path.basename(card['_dump']) if card.get('_dump') else 'none'))


def _read_meta(path):
    meta = {}
    try:
        with open(path) as f:
            for ln in f:
                if ':' in ln and not ln.startswith('#'):
                    k, v = ln.split(':', 1)
                    meta[k.strip()] = v.strip()
    except Exception:
        return None
    meta['_path'] = path
    d = meta.get('dump', 'none')
    meta['_dump'] = os.path.join(os.path.dirname(path), d) if (d and d != 'none') else None
    return meta


def _save_card(ctx, name):
    global _card, _view
    if not _last:
        _set(ctx, 'READ a tag first'); return
    base = _sanitize(name) or 'card'
    os.makedirs(_browse_abs(_browse_rel), exist_ok=True)
    path = _unique_path(base)
    card = dict(_last)
    # move the pending dump (if any) next to the metadata as <name>.<ext>
    card['_dump'] = None
    if _last.get('dump') and os.path.exists(_last['dump']):
        dst = path[:-4] + _dump_ext(_last.get('kind', ''))
        try:
            shutil.move(_last['dump'], dst); card['_dump'] = dst
        except Exception:
            card['_dump'] = None
    _write_meta(path, card)
    card['_path'] = path
    _card = card
    _refresh_browse()
    _set(ctx, 'saved "%s"%s' % (base, '' if card['_dump'] else ' (UID only)'))
    _view = 'card'


def _delete_card(path):
    meta = _read_meta(path)
    for p in (path, meta.get('_dump') if meta else None):
        if p:
            try: os.remove(p)
            except Exception: pass
    _refresh_browse()


def _refresh_browse():
    """Scan only the current folder (never the whole tree - a big library is
    cheap to browse one level at a time, mirroring the IR app)."""
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
                elif e.name.endswith('.nfc'):
                    out.append((False, e.path, e.name[:-4], _read_meta(e.path)))
            except Exception:
                pass
    except Exception:
        pass
    _browse_entries = out


# ---------- workers ----------
def _w_read(ctx):
    global _busy, _last
    try:
        if nfc is None:
            _set(ctx, 'acid_nfc module missing'); return
        if not nfc.tools_present():
            _set(ctx, 'install libnfc-bin'); return
        _set(ctx, 'reading... hold tag on reader')
        tag = nfc.read(timeout=12)
        if not tag:
            _set(ctx, 'no tag - place it and retry'); return
        tag['dump'] = None
        if tag.get('kind') in ('mfc', 'mfu'):
            _set(ctx, 'tag %s - dumping data...' % tag['uid'])
            ok, msg = nfc.dump(tag['kind'], TMP_DUMP + _dump_ext(tag['kind']))
            if ok:
                tag['dump'] = TMP_DUMP + _dump_ext(tag['kind'])
        _last = tag
        _set(ctx, 'READ %s  (%s)%s' % (tag['uid'], tag['type'],
                                       '' if tag['dump'] else ' UID-only'))
    except Exception as e:
        _set(ctx, 'read err: %s' % str(e)[:22])
    finally:
        _busy = False; ctx.mark_dirty()


def _w_write(ctx, card):
    global _busy
    try:
        if nfc is None:
            _set(ctx, 'acid_nfc missing'); return
        if not card.get('_dump'):
            _set(ctx, 'UID-only card - nothing to write'); return
        _set(ctx, 'place BLANK card, writing...')
        ok, msg = nfc.write(card.get('kind', 'mfc'), card['_dump'])
        _set(ctx, ('WRITE OK - cloned to card' if ok else 'write failed: %s' % msg))
    except Exception as e:
        _set(ctx, 'write err: %s' % str(e)[:22])
    finally:
        _busy = False; ctx.mark_dirty()


def _w_emu_start(ctx, uid):
    global _busy, _view, _emu_uid
    try:
        if _emu is None:
            _set(ctx, 'emulate unavailable'); return
        ok, msg = _emu.start(uid)
        if ok:
            _emu_uid = uid; _view = 'emulate'
        _set(ctx, msg)
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
def _refresh_reader(ctx):
    global _reader
    _reader = (nfc.reader_name() if nfc else 'no libnfc')
    try: ctx.mark_dirty()
    except Exception: pass


def on_enter(ctx):
    global _view
    _view = 'main'
    threading.Thread(target=lambda: _refresh_reader(ctx), daemon=True).start()
    ctx.mark_dirty()


def on_exit(ctx):
    if _emu is not None:
        _emu.stop()


# ---------- draw helpers ----------
def _btn(ctx, d, box, label, fill, fg, font=None):
    ctx.rr(d, box, fill=fill, r=8)
    ctx.ct(d, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, label, font or ctx.F_NM, fg)


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
    if tx <= 130 and page > 0 and ctx.debounce(0.25):
        return page - 1
    if tx >= 350 and page < total - 1 and ctx.debounce(0.25):
        return page + 1
    return None


def _card_panel(d, ctx, box, card):
    """Render a tag's identity (UID / type / ATQA / SAK) into a panel."""
    x0, y0, x1, y1 = box
    ctx.rr(d, box, fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
    if not card:
        ctx.ct(d, (x0 + x1) // 2, (y0 + y1) // 2, 'no tag read yet - tap READ', ctx.F_SM, ctx.DIM)
        return
    ctx.lt(d, x0 + 12, y0 + 18, 'UID', ctx.F_TINY, ctx.DIM)
    ctx.lt(d, x0 + 60, y0 + 18, card.get('uid_spaced', card.get('uid', '?')), ctx.F_NM, (120, 220, 255))
    ctx.lt(d, x0 + 12, y0 + 40, card.get('type', '?')[:30], ctx.F_SM, ctx.FG)
    tags = 'ATQA %s   SAK %s' % (card.get('atqa', '--'), card.get('sak', '--'))
    ctx.lt(d, x0 + 12, y0 + 58, tags, ctx.F_TINY, ctx.DIM)
    raw = card.get('dump')   # fresh read: a path/None; saved meta: basename or 'none'
    has_dump = bool(card.get('_dump')) or (raw not in (None, '', 'none'))
    ctx.ct(d, x1 - 52, y0 + 40, 'FULL DATA' if has_dump else 'UID ONLY',
           ctx.F_TINY, (110, 220, 150) if has_dump else (235, 170, 90))


# ---------- view: MAIN (read) ----------
def _draw_main(d, ctx):
    d.rectangle((0, 0, ctx.W, 28), fill=ctx.BARBG); d.line([(0, 28), (ctx.W, 28)], fill=ctx.LINE)
    ctx.rr(d, (6, 4, 92, 24), outline=ctx.ACC, w=1, r=5); ctx.ct(d, 49, 15, '< back', ctx.F_SM, ctx.ACC)
    ctx.ct(d, 190, 14, 'NFC', ctx.F_TIT, ctx.FG)
    ctx.rr(d, (250, 4, 290, 24), outline=(70, 130, 235), w=1, r=5); ctx.ct(d, 270, 14, '(i)', ctx.F_SM, (70, 130, 235))
    _btn(ctx, d, (370, 3, 472, 25), 'SAVED', (45, 52, 68), ctx.ACC, ctx.F_SM)

    _card_panel(d, ctx, (8, 36, 472, 128), _last)
    busy = _busy
    _btn(ctx, d, (8, 138, 158, 190), 'READ', (30, 120, 210) if not busy else (40, 70, 100), (255, 255, 255))
    can = bool(_last) and not busy
    _btn(ctx, d, (162, 138, 316, 190), 'SAVE', (225, 170, 40) if can else (90, 80, 45), (30, 25, 5))
    _btn(ctx, d, (320, 138, 472, 190), 'EMULATE', (150, 95, 235) if can else (75, 60, 100), (245, 240, 255))

    ctx.rr(d, (8, 200, 472, 250), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=6)
    ctx.lt(d, 16, 214, 'reader:', ctx.F_TINY, ctx.DIM); ctx.lt(d, 70, 214, _reader, ctx.F_SM, ctx.FG)
    ctx.lt(d, 16, 236, 'READ a tag -> SAVE to library -> WRITE a blank / EMULATE', ctx.F_TINY, ctx.DIM)
    ctx.rr(d, (8, 256, 472, 292), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=6)
    ctx.ct(d, 240, 274, _status[:52], ctx.F_SM, (235, 170, 40) if busy else ctx.FG)


def _touch_main(tx, ty, ctx):
    global _view, _name, _browse_rel, _browse_page, _info_off
    if ty <= 24 and 250 <= tx <= 290 and ctx.debounce(0.3):
        _info_off = 0; _view = 'info'; ctx.mark_dirty(); return
    if ty <= 25 and tx >= 370 and ctx.debounce(0.3):
        _browse_rel = ''; _browse_page = 0; _refresh_browse(); _view = 'browse'; ctx.mark_dirty(); return
    if 138 <= ty <= 190:
        if tx <= 158 and ctx.debounce(0.5):
            _spawn(ctx, _w_read); ctx.mark_dirty()
        elif tx <= 316 and _last and ctx.debounce(0.4):
            _name = ''; _view = 'savename'; ctx.mark_dirty()
        elif tx >= 320 and _last and ctx.debounce(0.4):
            _spawn(ctx, _w_emu_start, _last.get('uid', '')); ctx.mark_dirty()


# ---------- view: BROWSE (saved library) ----------
def _draw_browse(d, ctx):
    nested = bool(_browse_rel)
    title = _browse_rel.rsplit('/', 1)[-1].upper() if nested else 'SAVED CARDS'
    ctx.topbar(d, title[:20])
    _btn(ctx, d, (370, 3, 472, 25), 'UP' if nested else 'MAIN', (45, 52, 68), ctx.ACC, ctx.F_SM)
    if not _browse_entries:
        ctx.ct(d, 240, 150, 'no saved cards yet', ctx.F_NM, ctx.DIM)
        ctx.ct(d, 240, 174, 'READ a tag, then SAVE it', ctx.F_SM, ctx.DIM); return
    page, total, start = _paged(len(_browse_entries), _browse_page, _BROWSE_PER_PAGE)
    y = 34
    for is_dir, path, name, meta in _browse_entries[start:start + _BROWSE_PER_PAGE]:
        ctx.rr(d, (10, y, 470, y + 28), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
        if is_dir:
            ctx.rr(d, (16, y + 8, 28, y + 20), fill=(90, 140, 225), r=4)
            ctx.lt(d, 36, y + 14, name[:20], ctx.F_SM, ctx.FG)
            ctx.lt(d, 320, y + 14, '%d item%s' % (meta, '' if meta == 1 else 's'), ctx.F_TINY, (150, 190, 240))
        else:
            ctx.lt(d, 16, y + 14, name[:16], ctx.F_SM, ctx.FG)
            uid = (meta or {}).get('uid', '')[:14]
            ctx.lt(d, 200, y + 14, uid, ctx.F_TINY, (120, 220, 255))
            ctx.rr(d, (426, y, 470, y + 28), fill=(120, 40, 48), r=6)
            ctx.ct(d, 448, y + 14, 'X', ctx.F_SM, (255, 220, 220))
        y += 32
    if total > 1:
        _draw_page_bar(d, ctx, 34 + _BROWSE_PER_PAGE * 32 + 4, page, total)
    else:
        ctx.lt(d, 14, ctx.H - 9, 'tap = open   |   X = delete', ctx.F_TINY, ctx.DIM)


def _touch_browse(tx, ty, ctx):
    global _view, _browse_rel, _browse_page, _card
    nested = bool(_browse_rel)
    if ty <= 25 and tx >= 370 and ctx.debounce(0.3):
        if nested:
            _browse_rel = _rel_up(_browse_rel); _browse_page = 0; _refresh_browse(); ctx.mark_dirty()
        else:
            _view = 'main'; ctx.mark_dirty()
        return
    if not _browse_entries:
        return
    page, total, start = _paged(len(_browse_entries), _browse_page, _BROWSE_PER_PAGE)
    bar_y = 34 + _BROWSE_PER_PAGE * 32 + 4
    if total > 1 and bar_y <= ty <= bar_y + 28:
        newp = _touch_page_bar(tx, page, total, ctx)
        if newp is not None:
            _browse_page = newp; ctx.mark_dirty()
        return
    if 34 <= ty <= 34 + _BROWSE_PER_PAGE * 32:
        idx = start + (ty - 34) // 32
        if start <= idx < min(start + _BROWSE_PER_PAGE, len(_browse_entries)):
            is_dir, path, name, meta = _browse_entries[idx]
            if is_dir and ctx.debounce(0.3):
                _browse_rel = _rel_join(_browse_rel, name); _browse_page = 0; _refresh_browse(); ctx.mark_dirty()
            elif not is_dir:
                if tx >= 426 and ctx.debounce(0.4):
                    _delete_card(path); ctx.mark_dirty()
                elif tx < 420 and ctx.debounce(0.4):
                    _card = meta; _view = 'card'; ctx.mark_dirty()


# ---------- view: CARD (a saved card: write / emulate) ----------
def _draw_card(d, ctx):
    ctx.topbar(d, (os.path.basename(_card['_path'])[:-4] if _card else 'CARD')[:18])
    _btn(ctx, d, (370, 3, 472, 25), 'SAVED', (45, 52, 68), ctx.ACC, ctx.F_SM)
    _card_panel(d, ctx, (8, 36, 472, 128), _card)
    busy = _busy
    has_dump = bool(_card and _card.get('_dump'))
    _btn(ctx, d, (8, 140, 158, 194), 'WRITE', (23, 150, 86) if (has_dump and not busy) else (55, 75, 62), (240, 255, 246))
    _btn(ctx, d, (162, 140, 316, 194), 'EMULATE', (150, 95, 235) if not busy else (75, 60, 100), (245, 240, 255))
    _btn(ctx, d, (320, 140, 472, 194), 'DELETE', (120, 40, 48), (255, 220, 220))
    ctx.rr(d, (8, 204, 472, 250), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=6)
    ctx.lt(d, 16, 220, 'WRITE = clone onto a blank card (needs FULL DATA)', ctx.F_TINY, ctx.DIM)
    ctx.lt(d, 16, 238, 'EMULATE = present this UID for a Flipper to read', ctx.F_TINY, ctx.DIM)
    ctx.rr(d, (8, 256, 472, 292), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=6)
    ctx.ct(d, 240, 274, _status[:52], ctx.F_SM, (235, 170, 40) if busy else ctx.FG)


def _touch_card(tx, ty, ctx):
    global _view, _card
    if ty <= 25 and tx >= 370 and ctx.debounce(0.3):
        _refresh_browse(); _view = 'browse'; ctx.mark_dirty(); return
    if 140 <= ty <= 194 and _card:
        if tx <= 158 and _card.get('_dump') and ctx.debounce(0.5):
            _spawn(ctx, _w_write, _card); ctx.mark_dirty()
        elif 162 <= tx <= 316 and ctx.debounce(0.4):
            _spawn(ctx, _w_emu_start, _card.get('uid', '')); ctx.mark_dirty()
        elif tx >= 320 and ctx.debounce(0.4):
            _delete_card(_card['_path']); _view = 'browse'; ctx.mark_dirty()


# ---------- view: EMULATE (running) ----------
def _draw_emulate(d, ctx):
    ctx.topbar(d, 'EMULATING')
    ctx.rr(d, (8, 60, 472, 150), fill=(28, 20, 44), outline=(150, 95, 235), w=2, r=10)
    ctx.ct(d, 240, 86, 'PRESENTING UID', ctx.F_SM, (200, 170, 245))
    ctx.ct(d, 240, 116, _emu_uid.upper() or '--', ctx.F_BIG, (185, 150, 255))
    running = _emu.running if _emu else False
    ctx.ct(d, 240, 168, 'ON AIR - read it on your Flipper now' if running else 'stopped', ctx.F_SM,
           (110, 220, 150) if running else ctx.DIM)
    _btn(ctx, d, (140, 200, 340, 252), 'STOP', (200, 60, 60), (255, 240, 240))
    ctx.ct(d, 240, 274, 'UID-only emulation (PN532 limit) - sectors not replayed', ctx.F_TINY, ctx.DIM)


def _touch_emulate(tx, ty, ctx):
    global _view
    if 200 <= ty <= 252 and 140 <= tx <= 340 and ctx.debounce(0.3):
        if _emu:
            _emu.stop()
        _set(ctx, 'emulation stopped')
        _view = 'card' if _card else 'main'; ctx.mark_dirty()


# ---------- view: SAVE NAME (keyboard) ----------
def _draw_savename(d, ctx):
    ctx.topbar(d, 'CARD NAME')
    ctx.rr(d, (8, 34, 472, 70), fill=(12, 20, 28), outline=ctx.ACC, w=1, r=6)
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
                _save_card(ctx, _name.strip()); ctx.mark_dirty()


# ---------- view: INFO (educational Learn, scrollable) ----------
NFC_INFO = [
    (14, 'WHAT IS THIS?', (150, 200, 255)),
    (20, 'Reads, saves, clones and emulates 13.56 MHz', 'fg'),
    (20, 'contactless tags (NFC / RFID) with the ACR122U.', 'fg'),
    (20, 'Mifare Classic S50, NTAG, Ultralight, and more.', 'fg'),
    (0, '', 'fg'),
    (14, 'WHY IS IT HERE? (educational)', (120, 220, 150)),
    (20, 'To show that many access cards authenticate on', 'fg'),
    (20, 'the UID alone, or use factory-default keys - so a', 'fg'),
    (20, 'card can be read and cloned in seconds.', 'fg'),
    (0, '', 'fg'),
    (14, 'HOW TO DETECT / DEFEND', (235, 180, 40)),
    (20, '- Never trust the UID for access control: it is', 'dim'),
    (20, '  readable and clonable by anyone nearby.', 'dim'),
    (20, '- Change factory keys; use Mifare DESFire / EV1/2', 'dim'),
    (20, '  with per-card diversified keys + crypto.', 'dim'),
    (20, '- Keep cards in an RF-blocking sleeve; enforce a', 'dim'),
    (20, '  second factor for anything that matters.', 'dim'),
    (0, '', 'fg'),
    (14, 'THE RULE', (255, 120, 120)),
    (20, 'Use ONLY on cards you OWN or are authorized to', 'fg'),
    (20, 'test.', 'fg'),
]
_INFO_VIS = 13


def _draw_info(d, ctx):
    global _info_off
    ctx.topbar(d, 'NFC - LEARN')
    ctx.rr(d, (418, 4, 472, 24), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, 445, 14, 'back', ctx.F_TINY, ctx.ACC)
    total = len(NFC_INFO); maxoff = max(0, total - _INFO_VIS)
    _info_off = min(max(_info_off, 0), maxoff)
    y = 38
    for indent, txt, ck in NFC_INFO[_info_off:_info_off + _INFO_VIS]:
        if txt:
            col = ctx.FG if ck == 'fg' else ctx.DIM if ck == 'dim' else ck
            ctx.lt(d, indent, y, txt, ctx.F_SM, col)
        y += 18
    if total > _INFO_VIS:
        by = ctx.H - 24
        ctx.rr(d, (10, by, 120, by + 21), outline=ctx.LINE, w=1, r=6)
        ctx.ct(d, 65, by + 10, 'UP', ctx.F_SM, ctx.FG if _info_off > 0 else ctx.DIM)
        ctx.ct(d, 240, by + 10, '%d-%d / %d' % (_info_off + 1, min(_info_off + _INFO_VIS, total), total), ctx.F_TINY, ctx.DIM)
        ctx.rr(d, (360, by, 470, by + 21), outline=ctx.LINE, w=1, r=6)
        ctx.ct(d, 415, by + 10, 'DOWN', ctx.F_SM, ctx.FG if _info_off < maxoff else ctx.DIM)


def _touch_info(tx, ty, ctx):
    global _view, _info_off
    if ty <= 24 and tx >= 418 and ctx.debounce(0.3):
        _view = 'main'; ctx.mark_dirty(); return
    total = len(NFC_INFO); maxoff = max(0, total - _INFO_VIS)
    if total > _INFO_VIS and ctx.H - 24 <= ty <= ctx.H - 2 and ctx.debounce(0.2):
        st = max(1, _INFO_VIS - 2)
        if tx <= 120 and _info_off > 0:
            _info_off = max(0, _info_off - st); ctx.mark_dirty()
        elif tx >= 360 and _info_off < maxoff:
            _info_off = min(maxoff, _info_off + st); ctx.mark_dirty()


# ---------- dispatch ----------
def draw(d, ctx):
    {'browse': _draw_browse, 'card': _draw_card, 'emulate': _draw_emulate,
     'savename': _draw_savename, 'info': _draw_info}.get(_view, _draw_main)(d, ctx)


def handle_touch(tx, ty, ctx):
    {'browse': _touch_browse, 'card': _touch_card, 'emulate': _touch_emulate,
     'savename': _touch_savename, 'info': _touch_info}.get(_view, _touch_main)(tx, ty, ctx)
