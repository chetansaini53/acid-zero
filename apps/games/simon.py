# Acid Zero game - "Simon": repeat the growing colour sequence.
#
# Drop-in module for the Games plugin (games.py loads games/<key>.py needing draw +
# handle_touch, optional on_enter/on_exit/hud). The Games play-view owns the top bar
# (0-28: '< home' via the launcher back-zone, 'MENU' top-right); this game renders the
# four pads below it. Pads start at y>=44 so the top-left home-zone never eats a tap.
# Pure-stdlib, single-touch friendly. Educational fun; own device.
import random
import threading
import time

META = {'name': 'Simon'}

# pad boxes (2x2) and their idle / lit colours. Index: 0=TL 1=TR 2=BL 3=BR.
PADS = [(2, 44, 238, 180), (242, 44, 478, 180), (2, 184, 238, 318), (242, 184, 478, 318)]
IDLE = [(30, 100, 42), (110, 36, 36), (30, 56, 112), (112, 96, 30)]
LIT = [(84, 240, 112), (250, 92, 92), (92, 152, 255), (250, 220, 82)]
LEAD = 0.45          # pause before the sequence starts playing

_seq = []            # the sequence of pad indices to repeat
_done = 0            # rounds completed this game = score
_best = 0            # best score this session
_pos = 0             # player's position while repeating
_phase = 'idle'      # show | input | over
_show_start = 0.0
_flash_pad = -1      # pad briefly lit by a tap
_flash_t = 0.0
_gen = 0


def _step():
    return max(0.34, 0.60 - _done * 0.02)     # sequence plays a little faster each round


def _show_lit(now):
    """Which pad is lit during the 'show' phase: pad index, -1 (gap), or -2 (done)."""
    st = _step()
    t = now - _show_start - LEAD
    if t < 0:
        return -1
    k = int(t / st)
    if k >= len(_seq):
        return -2
    return _seq[k] if (t - k * st) < st * 0.6 else -1


def _pad_at(tx, ty):
    if ty < 44:
        return -1
    return (0 if ty < 182 else 2) + (0 if tx < 240 else 1)


def _add_and_show():
    global _phase, _show_start, _pos
    _seq.append(random.randint(0, 3))
    _phase = 'show'; _show_start = time.time(); _pos = 0


def _new_game(ctx):
    global _seq, _done, _pos, _flash_pad
    _seq = []; _done = 0; _pos = 0; _flash_pad = -1
    _add_and_show()
    ctx.mark_dirty()


# ---------- lifecycle ----------
def on_enter(ctx):
    global _gen
    _gen += 1
    threading.Thread(target=_tick, args=(ctx, _gen), daemon=True).start()
    _new_game(ctx)


def on_exit(ctx):
    global _gen
    _gen += 1


def _tick(ctx, gen):
    global _phase, _pos
    while gen == _gen:
        time.sleep(0.05)
        now = time.time()
        busy = False
        if _phase == 'show':
            busy = True
            if _show_lit(now) == -2:          # sequence finished playing -> player's turn
                _phase = 'input'; _pos = 0
        if _flash_pad >= 0 and now < _flash_t:
            busy = True
        if busy:
            try: ctx.mark_dirty()
            except Exception: break


def hud():
    return 'Rnd %d  Best %d' % (_done, _best)


# ---------- draw ----------
def draw(d, ctx):
    now = time.time()
    lit = -1
    if _phase == 'show':
        l = _show_lit(now)
        lit = l if l >= 0 else -1
    elif _flash_pad >= 0 and now < _flash_t:
        lit = _flash_pad
    for i, box in enumerate(PADS):
        ctx.rr(d, box, fill=(LIT[i] if i == lit else IDLE[i]), r=16)
    if _phase in ('show', 'input'):
        msg, mc = ('WATCH', (245, 215, 120)) if _phase == 'show' else ('YOUR TURN', (150, 240, 175))
        ctx.rr(d, (192, 167, 288, 197), fill=(14, 14, 19), r=9)
        ctx.ct(d, 240, 182, msg, ctx.F_SM, mc)
    elif _phase == 'over':
        ctx.rr(d, (96, 132, 384, 230), fill=(16, 16, 22), outline=(235, 80, 80), w=2, r=14)
        ctx.ct(d, 240, 162, 'GAME OVER', ctx.F_TIT, (240, 95, 95))
        ctx.ct(d, 240, 190, 'score  %d       best  %d' % (_done, _best), ctx.F_SM, (232, 236, 242))
        ctx.ct(d, 240, 212, 'tap any pad to play again', ctx.F_TINY, (150, 160, 172))


# ---------- touch ----------
def handle_touch(tx, ty, ctx):
    global _pos, _flash_pad, _flash_t, _phase, _done, _best
    pad = _pad_at(tx, ty)
    if pad < 0:
        return
    if _phase == 'over':
        if ctx.debounce(0.3):
            _new_game(ctx)
        return
    if _phase != 'input' or not ctx.debounce(0.1):
        return
    _flash_pad = pad; _flash_t = time.time() + 0.18
    if pad == _seq[_pos]:
        _pos += 1
        if _pos >= len(_seq):                 # whole sequence repeated -> next round
            _done += 1; _best = max(_best, _done)
            _add_and_show()
    else:
        _phase = 'over'; _best = max(_best, _done)
    ctx.mark_dirty()
