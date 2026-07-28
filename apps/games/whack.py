# Acid Zero game - "Whack-Mole": tap the moles before they duck back.
#
# Drop-in for the Games plugin. Moles pop up in a 3x3 grid; tap one to score. They
# pop faster and stay up shorter as the 30s clock runs down. Score + time show in the
# HUD (games.py top bar). Pads start at y>=44 to clear the launcher's home-zone.
# Pure-stdlib, single-touch friendly. Educational fun; own device.
import random
import threading
import time

META = {'name': 'Whack-Mole'}

COLS, ROWS = 3, 3
CX0, CY0, CW, CH = 4, 48, 158, 89
GAME_DUR = 30.0

_up = {}             # hole index -> despawn time
_hit = {}            # hole index -> hit-flash-until (whacked feedback)
_score = 0
_best = 0
_phase = 'play'      # play | over
_end_time = 0.0
_gen = 0


def _center(i):
    c, r = i % COLS, i // COLS
    return CX0 + c * CW + CW // 2, CY0 + r * CH + CH // 2


def _hole_at(tx, ty):
    if ty < CY0:
        return -1
    c, r = (tx - CX0) // CW, (ty - CY0) // CH
    return r * COLS + c if 0 <= c < COLS and 0 <= r < ROWS else -1


def _new_game(ctx):
    global _score, _phase, _end_time, _up, _hit
    _score = 0; _phase = 'play'; _end_time = time.time() + GAME_DUR
    _up = {}; _hit = {}
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
    global _phase, _best
    while gen == _gen:
        time.sleep(0.06)
        now = time.time()
        if _phase == 'play':
            if now >= _end_time:
                _phase = 'over'; _best = max(_best, _score)
            else:
                for h in [h for h, t in _up.items() if now >= t]:
                    del _up[h]                              # ducked back (missed)
                elapsed = GAME_DUR - (_end_time - now)
                life = max(0.6, 1.4 - elapsed * 0.022)
                spawn_p = 0.055 + elapsed * 0.004
                if len(_up) < 3 and random.random() < spawn_p:
                    empty = [i for i in range(9) if i not in _up]
                    if empty:
                        _up[random.choice(empty)] = now + life
            try: ctx.mark_dirty()
            except Exception: break
        elif any(t > now for t in _hit.values()):
            try: ctx.mark_dirty()
            except Exception: break


def hud():
    if _phase == 'over':
        return 'Score %d  Best %d' % (_score, _best)
    return 'Score %d   %ds' % (_score, max(0, int(_end_time - time.time())))


# ---------- draw ----------
def _draw_mole(d, cx, cy):
    d.ellipse((cx - 34, cy - 30, cx + 34, cy + 34), fill=(150, 110, 70), outline=(92, 62, 36), width=2)
    d.ellipse((cx - 15, cy - 8, cx - 5, cy + 2), fill=(20, 20, 20))
    d.ellipse((cx + 5, cy - 8, cx + 15, cy + 2), fill=(20, 20, 20))
    d.ellipse((cx - 7, cy + 8, cx + 7, cy + 19), fill=(212, 120, 120))


def draw(d, ctx):
    now = time.time()
    for i in range(9):
        cx, cy = _center(i)
        d.ellipse((cx - 48, cy + 16, cx + 48, cy + 40), fill=(28, 24, 20), outline=(58, 48, 38))
        if _hit.get(i, 0) > now:
            ctx.ct(d, cx, cy, 'BONK!', ctx.F_NM, (250, 220, 82))
        elif i in _up:
            _draw_mole(d, cx, cy - 4)
    if _phase == 'over':
        ctx.rr(d, (96, 132, 384, 230), fill=(16, 16, 22), outline=(235, 80, 80), w=2, r=14)
        ctx.ct(d, 240, 162, 'TIME UP', ctx.F_TIT, (240, 190, 95))
        ctx.ct(d, 240, 190, 'score  %d       best  %d' % (_score, _best), ctx.F_SM, (232, 236, 242))
        ctx.ct(d, 240, 212, 'tap to play again', ctx.F_TINY, (150, 160, 172))


# ---------- touch ----------
def handle_touch(tx, ty, ctx):
    global _score, _up, _hit
    if _phase == 'over':
        if ctx.debounce(0.3):
            _new_game(ctx)
        return
    h = _hole_at(tx, ty)
    if h < 0 or not ctx.debounce(0.05):
        return
    if h in _up:
        del _up[h]; _score += 1; _hit[h] = time.time() + 0.25
        ctx.mark_dirty()
