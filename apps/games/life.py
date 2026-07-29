# Acid Zero game - "Life": Conway's Game of Life on the panel.
#
# Drop-in for the Games plugin. Tap cells to toggle them, then PLAY to run the
# automaton (B3/S23 rules on a wrap-around torus). STEP advances one generation,
# RANDOM seeds a field, CLEAR empties it. Gen + population show in the HUD. The grid
# starts at y>=44 so the launcher's top-left home-zone stays clear. Pure-stdlib.
# Educational fun; own device.
import random
import threading
import time

META = {'name': 'Life'}

COLS, ROWS, CELL = 38, 18, 12
GX, GY = 12, 44
SPEED = 0.14          # seconds per generation while running
ALIVE = (90, 220, 140)

_grid = [[0] * COLS for _ in range(ROWS)]
_running = False
_gc = 0               # generation counter
_step_t = 0.0
_gen = 0


def _neighbors(r, c):
    n = 0
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if (dr or dc) and _grid[(r + dr) % ROWS][(c + dc) % COLS]:
                n += 1
    return n


def _next():
    global _grid, _gc
    ng = [[0] * COLS for _ in range(ROWS)]
    for r in range(ROWS):
        gr = _grid[r]
        for c in range(COLS):
            n = _neighbors(r, c)
            ng[r][c] = 1 if (n == 3 or (gr[c] and n == 2)) else 0
    _grid = ng
    _gc += 1


def _randomize():
    global _grid, _gc
    _grid = [[1 if random.random() < 0.28 else 0 for _ in range(COLS)] for _ in range(ROWS)]
    _gc = 0


def _clear():
    global _grid, _gc, _running
    _grid = [[0] * COLS for _ in range(ROWS)]
    _gc = 0; _running = False


# ---------- lifecycle ----------
def on_enter(ctx):
    global _gen, _running
    _running = False
    _randomize()
    _gen += 1
    threading.Thread(target=_tick, args=(ctx, _gen), daemon=True).start()
    ctx.mark_dirty()


def on_exit(ctx):
    global _gen, _running
    _gen += 1; _running = False


def _tick(ctx, gen):
    global _step_t
    while gen == _gen:
        time.sleep(0.05)
        if _running and time.time() >= _step_t:
            _step_t = time.time() + SPEED
            _next()
            try: ctx.mark_dirty()
            except Exception: break


def hud():
    return 'Gen %d  Pop %d' % (_gc, sum(sum(row) for row in _grid))


# ---------- draw ----------
def _btn(d, ctx, box, label, fill):
    ctx.rr(d, box, fill=fill, r=8)
    ctx.ct(d, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, label, ctx.F_NM, (236, 240, 248))


def draw(d, ctx):
    ctx.rr(d, (GX - 2, GY - 2, GX + COLS * CELL + 1, GY + ROWS * CELL + 1), outline=ctx.LINE, w=1, r=4)
    d.rectangle((GX, GY, GX + COLS * CELL - 1, GY + ROWS * CELL - 1), fill=(10, 12, 16))
    for r in range(ROWS):
        gr = _grid[r]
        y = GY + r * CELL
        for c in range(COLS):
            if gr[c]:
                x = GX + c * CELL
                d.rectangle((x + 1, y + 1, x + CELL - 1, y + CELL - 1), fill=ALIVE)
    _btn(d, ctx, (4, 268, 120, 314), 'PAUSE' if _running else 'PLAY',
         (92, 72, 40) if _running else (38, 92, 60))
    _btn(d, ctx, (124, 268, 240, 314), 'STEP', (48, 56, 72))
    _btn(d, ctx, (244, 268, 360, 314), 'RANDOM', (48, 56, 72))
    _btn(d, ctx, (364, 268, 476, 314), 'CLEAR', (72, 52, 52))


# ---------- touch ----------
def handle_touch(tx, ty, ctx):
    global _running, _step_t
    if 268 <= ty <= 314:
        if not ctx.debounce(0.25):
            return
        if tx <= 120:
            _running = not _running; _step_t = time.time() + SPEED
        elif tx <= 240:
            if not _running:
                _next()
        elif tx <= 360:
            _randomize()
        else:
            _clear()
        ctx.mark_dirty()
        return
    if GY <= ty < GY + ROWS * CELL and GX <= tx < GX + COLS * CELL:
        if not ctx.debounce(0.04):
            return
        c = (tx - GX) // CELL
        r = (ty - GY) // CELL
        if 0 <= r < ROWS and 0 <= c < COLS:
            _grid[r][c] ^= 1
            ctx.mark_dirty()
