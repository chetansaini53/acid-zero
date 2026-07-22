# Acid Zero plugin - "Flasher": flash the co-processors FROM the device (no laptop).
#   ESP32 (CC1101 + IR)  -> SCAN (chip id, rejects wrong board) + FLASH (esptool)
#   Pico 2 W (Bad USB)   -> SCAN (BOOTSEL/CIRCUITPY) + FLASH (CircuitPython + code)
# The Pico AP SSID/password are entered here (defaults shown, change before flash so
# the shipped default isn't reused). On a successful flash they are also saved to the
# shared creds store, so the Bad USB app's CONNECT joins exactly what you flashed.
# Educational / own-lab only.
import os, sys, threading
for _p in ('/usr/local/bin', '/usr/local/lib/acid-apps', '/home/ella3'):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    import acid_flash as F
except Exception:
    F = None
try:
    import acid_apcreds as C
except Exception:
    C = None
try:
    import acid_kbd
except Exception:
    acid_kbd = None

META = {'name': 'Flasher', 'icon': 'usb', 'color': (235, 170, 40)}

_DEF_SSID = getattr(C, 'DEFAULT_SSID', 'AcidZero-Duck')
_DEF_PSK = getattr(C, 'DEFAULT_PSK', 'acidzero1337')

_view = 'main'            # main | kb
_ssid = _DEF_SSID
_psk = _DEF_PSK
_esp = None               # None | (ok, head, detail)
_pico = None              # None | (state, detail)
_busy = False
_log = 'SCAN a board to begin'
_kb_target = ''           # 'ssid' | 'psk'


def _set(ctx, s):
    global _log
    _log = s
    try:
        ctx.mark_dirty()
    except Exception:
        pass


def _spawn(fn, *a):
    threading.Thread(target=fn, args=a, daemon=True).start()


def on_enter(ctx):
    global _view, _ssid, _psk
    _view = 'main'
    if C:
        _ssid, _psk = C.load()            # reflect the creds currently on the Pico
    if acid_kbd:
        acid_kbd.close()                  # clear any stale editor state
    ctx.mark_dirty()


# ---------- workers ----------
def _w_esp_scan(ctx):
    global _esp
    _esp = F.esp_scan() if F else (False, 'module missing', '')
    _set(ctx, ('ESP32: ' + _esp[1]) if _esp else 'scan failed')


def _w_esp_flash(ctx):
    global _busy
    try:
        ok, msg = F.esp_flash(lambda s: _set(ctx, s)) if F else (False, 'module missing')
        _set(ctx, ('OK: ' if ok else 'ERR: ') + msg)
    finally:
        _busy = False
        try: ctx.mark_dirty()
        except Exception: pass


def _w_pico_scan(ctx):
    global _pico
    _pico = F.pico_scan() if F else ('none', 'module missing')
    _set(ctx, 'Pico: ' + _pico[1])


def _w_pico_flash(ctx):
    global _busy
    try:
        ok, msg = F.pico_flash(_ssid, _psk, lambda s: _set(ctx, s)) if F else (False, 'module missing')
        if ok and C:
            C.save(_ssid, _psk)           # share the flashed creds with Bad USB CONNECT
        _set(ctx, ('OK: ' if ok else 'ERR: ') + msg)
    finally:
        _busy = False
        try: ctx.mark_dirty()
        except Exception: pass


# ---------- draw: MAIN ----------
def _btn(d, ctx, box, label, on, col=None):
    ctx.rr(d, box, fill=(col or (30, 90, 60)) if on else (48, 48, 52),
           outline=ctx.ACC if on else ctx.LINE, w=1, r=7)
    ctx.ct(d, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, label, ctx.F_SM, ctx.FG if on else ctx.DIM)


def _draw_main(d, ctx):
    ctx.topbar(d, 'FLASHER')
    busy = _busy
    # ---- ESP32 ----
    ctx.rr(d, (8, 32, 472, 124), fill=ctx.TILE, outline=ctx.LINE, w=1, r=8)
    ctx.lt(d, 18, 48, 'ESP32 NodeMCU-32S', ctx.F_NM, ctx.FG)
    ctx.lt(d, 18, 66, 'CC1101 + IR co-processor', ctx.F_TINY, ctx.DIM)
    if _esp:
        col = (30, 200, 121) if _esp[0] else (235, 80, 80)
        ctx.lt(d, 18, 86, ('%s  %s' % (_esp[1], _esp[2]))[:56], ctx.F_TINY, col)
    else:
        ctx.lt(d, 18, 86, 'not scanned', ctx.F_TINY, ctx.DIM)
    _btn(d, ctx, (16, 98, 150, 120), 'SCAN', not busy)
    _btn(d, ctx, (326, 98, 464, 120), 'FLASH', (_esp and _esp[0] and not busy), col=(205, 60, 60))
    # ---- Pico ----
    ctx.rr(d, (8, 130, 472, 300), fill=ctx.TILE, outline=ctx.LINE, w=1, r=8)
    ctx.lt(d, 18, 148, 'Pico 2 W  ·  Bad USB', ctx.F_NM, ctx.FG)
    ctx.lt(d, 320, 148, 'shared w/ Bad USB', ctx.F_TINY, (150, 190, 240))
    # editable AP creds (also used by the Bad USB app's CONNECT)
    ctx.lt(d, 18, 172, 'SSID', ctx.F_TINY, ctx.DIM)
    ctx.rr(d, (70, 162, 300, 184), fill=ctx.PANEL, outline=ctx.ACC, w=1, r=6)
    ctx.lt(d, 78, 173, _ssid[:26], ctx.F_SM, ctx.FG)
    ctx.lt(d, 18, 200, 'PW', ctx.F_TINY, ctx.DIM)
    ctx.rr(d, (70, 190, 300, 212), fill=ctx.PANEL, outline=ctx.ACC, w=1, r=6)
    ctx.lt(d, 78, 201, _psk[:26], ctx.F_SM, ctx.FG)
    ctx.lt(d, 312, 178, 'tap to', ctx.F_TINY, ctx.DIM)
    ctx.lt(d, 312, 200, 'edit', ctx.F_TINY, ctx.DIM)
    if _pico:
        pc = (30, 200, 121) if _pico[0] in ('bootsel', 'circuitpy') else (235, 130, 55)
        ctx.lt(d, 18, 234, ('Pico: ' + _pico[1])[:56], ctx.F_TINY, pc)
    else:
        ctx.lt(d, 18, 234, 'not scanned', ctx.F_TINY, ctx.DIM)
    _btn(d, ctx, (16, 248, 150, 272), 'SCAN', not busy)
    _btn(d, ctx, (326, 248, 464, 272), 'FLASH', (_pico and _pico[0] in ('bootsel', 'circuitpy') and not busy), col=(205, 60, 60))
    # log
    ctx.ct(d, 240, 312, ('...' + _log[-54:]) if len(_log) > 54 else _log, ctx.F_TINY, (235, 170, 40) if busy else ctx.DIM)


def _touch_main(tx, ty, ctx):
    global _view, _kb_target, _busy
    if _busy:
        return
    # ESP32
    if 98 <= ty <= 120:
        if 16 <= tx <= 150 and ctx.debounce(0.5):
            _spawn(_w_esp_scan, ctx); _set(ctx, 'scanning ESP32...'); return
        if 326 <= tx <= 464 and _esp and _esp[0] and ctx.debounce(0.6):
            _busy = True; _spawn(_w_esp_flash, ctx); _set(ctx, 'flashing ESP32...'); return
    # Pico creds fields -> shared keyboard (only switch view if the kb is present)
    if 162 <= ty <= 184 and 70 <= tx <= 300 and ctx.debounce(0.3):
        if acid_kbd:
            _kb_target = 'ssid'; acid_kbd.start('SSID', _ssid, maxlen=32); _view = 'kb'
        ctx.mark_dirty(); return
    if 190 <= ty <= 212 and 70 <= tx <= 300 and ctx.debounce(0.3):
        if acid_kbd:
            _kb_target = 'psk'; acid_kbd.start('PASSWORD', _psk, maxlen=63); _view = 'kb'
        ctx.mark_dirty(); return
    # Pico buttons
    if 248 <= ty <= 272:
        if 16 <= tx <= 150 and ctx.debounce(0.5):
            _spawn(_w_pico_scan, ctx); _set(ctx, 'scanning Pico...'); return
        if 326 <= tx <= 464 and _pico and _pico[0] in ('bootsel', 'circuitpy') and ctx.debounce(0.6):
            if C:
                okv, why = C.validate(_ssid, _psk)
                if not okv:
                    _set(ctx, why); return
            _busy = True; _spawn(_w_pico_flash, ctx); _set(ctx, 'flashing Pico...'); return


# ---------- dispatch ----------
def draw(d, ctx):
    if _view == 'kb' and acid_kbd:
        acid_kbd.draw(d, ctx)
    else:
        _draw_main(d, ctx)


def handle_touch(tx, ty, ctx):
    global _view, _ssid, _psk
    if _view == 'kb':
        if not acid_kbd:
            _view = 'main'; ctx.mark_dirty(); return
        r = acid_kbd.touch(tx, ty, ctx)
        if r == 'editing':
            return
        if isinstance(r, tuple) and r[0] == 'ok':
            if _kb_target == 'ssid':
                _ssid = r[1] or _DEF_SSID
            else:
                _psk = r[1] or _DEF_PSK
        _view = 'main'
        ctx.mark_dirty()
        return
    _touch_main(tx, ty, ctx)
