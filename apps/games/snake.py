# Acid Zero game - Snake. Arrow pad steers; eat red food to grow; hitting a wall
# or yourself ends it. Real-time: a tick thread advances the snake + marks dirty,
# so it animates without blocking the launcher. Speeds up as you grow.
import threading
import time
import random

META = {'name': 'Snake'}
COLS, ROWS = 16, 14
CELL, BX, BY = 18, 8, 48

_snake = [(8, 7), (7, 7), (6, 7)]
_dir = (1, 0)
_food = (12, 7)
_score = 0
_best = 0
_over = False
_run = False
_gen = 0                 # thread generation - invalidates a stale tick thread
_ctx = None


# ---------- pure logic (unit-testable) ----------
def _place_food():
    global _food
    empt = [(c, r) for c in range(COLS) for r in range(ROWS) if (c, r) not in _snake]
    _food = random.choice(empt) if empt else _snake[0]


def _reset():
    global _snake, _dir, _score, _over
    cx, cy = COLS // 2, ROWS // 2
    _snake = [(cx, cy), (cx - 1, cy), (cx - 2, cy)]
    _dir = (1, 0)
    _score = 0
    _over = False
    _place_food()


def _step():
    """Advance one cell. Sets _over on wall/self hit; grows on food."""
    global _snake, _score, _over, _best
    if _over:
        return
    hc, hr = _snake[0]
    dc, dr = _dir
    nc, nr = hc + dc, hr + dr
    if nc < 0 or nc >= COLS or nr < 0 or nr >= ROWS or (nc, nr) in _snake:
        _over = True
        if _score > _best:
            _best = _score
        return
    _snake.insert(0, (nc, nr))
    if (nc, nr) == _food:
        _score += 1
        _place_food()
    else:
        _snake.pop()


def _setdir(dc, dr):
    global _dir
    if (dc, dr) != (-_dir[0], -_dir[1]):    # no instant 180 reversal
        _dir = (dc, dr)


# ---------- plugin contract ----------
def _tick(g):
    while _run and g == _gen:
        time.sleep(max(0.07, 0.17 - _score * 0.005))
        if _run and g == _gen and not _over:
            _step()
            if _ctx is not None:
                try: _ctx.mark_dirty()
                except Exception: pass


def on_enter(ctx):
    global _run, _ctx, _gen
    _ctx = ctx
    _reset()
    _gen += 1
    _run = True
    threading.Thread(target=_tick, args=(_gen,), daemon=True).start()
    ctx.mark_dirty()


def on_exit(ctx):
    global _run, _gen
    _run = False
    _gen += 1                # kill any running tick thread


def hud():
    return 'score %d' % _score


def _btn(d, ctx, box, ch):
    ctx.rr(d, box, fill=(55, 62, 78), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, ch, ctx.F_BIG, ctx.FG)


def draw(d, ctx):
    ctx.rr(d, (BX - 2, BY - 2, BX + COLS * CELL + 2, BY + ROWS * CELL + 2),
           fill=(22, 26, 32), outline=ctx.LINE, w=1, r=6)
    fc, fr = _food
    ctx.rr(d, (BX + fc * CELL + 3, BY + fr * CELL + 3, BX + fc * CELL + CELL - 3, BY + fr * CELL + CELL - 3),
           fill=(235, 80, 80), r=4)
    for i, (c, r) in enumerate(list(_snake)):     # snapshot: the tick thread mutates _snake
        col = (60, 220, 140) if i == 0 else (25, 165, 105)
        ctx.rr(d, (BX + c * CELL + 1, BY + r * CELL + 1, BX + c * CELL + CELL - 1, BY + r * CELL + CELL - 1),
               fill=col, r=3)
    # right panel: arrow pad + length/best + new
    _btn(d, ctx, (360, 64, 420, 110), '^')
    _btn(d, ctx, (360, 176, 420, 222), 'v')
    _btn(d, ctx, (302, 120, 356, 166), '<')
    _btn(d, ctx, (424, 120, 472, 166), '>')
    ctx.ct(d, 388, 238, 'len %d   best %d' % (len(_snake), _best), ctx.F_SM, ctx.DIM)
    ctx.rr(d, (306, 252, 472, 286), fill=(60, 70, 90), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, 389, 269, 'NEW GAME', ctx.F_SM, ctx.FG)
    if _over:
        bw = COLS * CELL
        ctx.rr(d, (BX + 10, BY + bw // 2 - 60, BX + bw - 10, BY + bw // 2), fill=(18, 22, 28), outline=(235, 80, 80), w=2, r=10)
        ctx.ct(d, BX + bw // 2, BY + bw // 2 - 42, 'GAME OVER', ctx.F_NM, (235, 90, 90))
        ctx.ct(d, BX + bw // 2, BY + bw // 2 - 22, 'tap NEW GAME', ctx.F_SM, ctx.DIM)


def handle_touch(tx, ty, ctx):
    if 252 <= ty <= 286 and 306 <= tx <= 472 and ctx.debounce(0.3):
        on_enter(ctx)
        return
    if not ctx.debounce(0.06):
        return
    if 64 <= ty <= 110 and 360 <= tx <= 420:
        _setdir(0, -1)
    elif 176 <= ty <= 222 and 360 <= tx <= 420:
        _setdir(0, 1)
    elif 120 <= ty <= 166 and 302 <= tx <= 356:
        _setdir(-1, 0)
    elif 120 <= ty <= 166 and 424 <= tx <= 472:
        _setdir(1, 0)
    ctx.mark_dirty()
