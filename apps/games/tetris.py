# Acid Zero game - Tetris. Buttons: ROTATE, left/right, soft-drop (v), hard DROP.
# 7 tetrominoes, wall-kick rotation, line clears, gravity that speeds up by level.
# Real-time: a generation-guarded tick thread drops the piece + marks dirty.
import threading
import time
import random

META = {'name': 'Tetris'}
COLS, ROWS = 10, 20
CELL, BX, BY = 14, 8, 38

# rotation states: list of 4 (dx,dy) cells per rotation, in a 3x3/4x4 box
PIECES = {
    'I': [[(0, 1), (1, 1), (2, 1), (3, 1)], [(2, 0), (2, 1), (2, 2), (2, 3)]],
    'O': [[(1, 0), (2, 0), (1, 1), (2, 1)]],
    'T': [[(1, 0), (0, 1), (1, 1), (2, 1)], [(1, 0), (1, 1), (2, 1), (1, 2)],
          [(0, 1), (1, 1), (2, 1), (1, 2)], [(1, 0), (0, 1), (1, 1), (1, 2)]],
    'S': [[(1, 0), (2, 0), (0, 1), (1, 1)], [(1, 0), (1, 1), (2, 1), (2, 2)]],
    'Z': [[(0, 0), (1, 0), (1, 1), (2, 1)], [(2, 0), (1, 1), (2, 1), (1, 2)]],
    'J': [[(0, 0), (0, 1), (1, 1), (2, 1)], [(1, 0), (2, 0), (1, 1), (1, 2)],
          [(0, 1), (1, 1), (2, 1), (2, 2)], [(1, 0), (1, 1), (0, 2), (1, 2)]],
    'L': [[(2, 0), (0, 1), (1, 1), (2, 1)], [(1, 0), (1, 1), (1, 2), (2, 2)],
          [(0, 1), (1, 1), (2, 1), (0, 2)], [(0, 0), (1, 0), (1, 1), (1, 2)]],
}
COL = {'I': (60, 200, 220), 'O': (230, 210, 60), 'T': (180, 90, 220), 'S': (70, 200, 110),
       'Z': (230, 80, 80), 'J': (70, 120, 230), 'L': (230, 150, 50)}
SCORES = {1: 40, 2: 100, 3: 300, 4: 1200}

_board = [[0] * COLS for _ in range(ROWS)]
_piece, _rot, _px, _py, _next = 'T', 0, 3, 0, 'I'
_score = _lines = _level = 0
_over = False
_run = False
_gen = 0
_ctx = None
_mx = threading.Lock()


# ---------- pure logic (unit-testable) ----------
def _cells(p, rot, px, py):
    return [(px + dx, py + dy) for dx, dy in PIECES[p][rot % len(PIECES[p])]]


def _valid(cells):
    for x, y in cells:
        if x < 0 or x >= COLS or y >= ROWS:
            return False
        if y >= 0 and _board[y][x] != 0:
            return False
    return True


def _spawn():
    global _piece, _next, _rot, _px, _py, _over
    _piece, _next = _next, random.choice('IOTSZJL')
    _rot, _px, _py = 0, 3, 0
    if not _valid(_cells(_piece, _rot, _px, _py)):
        _over = True


def _reset():
    global _board, _score, _lines, _level, _over, _next
    _board = [[0] * COLS for _ in range(ROWS)]
    _score = _lines = _level = 0
    _over = False
    _next = random.choice('IOTSZJL')
    _spawn()


def _lock_piece():
    global _board, _score, _lines, _level
    for x, y in _cells(_piece, _rot, _px, _py):
        if 0 <= y < ROWS and 0 <= x < COLS:
            _board[y][x] = _piece
    kept = [row for row in _board if any(v == 0 for v in row)]
    cleared = ROWS - len(kept)
    if cleared:
        _board = [[0] * COLS for _ in range(cleared)] + kept
        _score += SCORES.get(cleared, 0) * (_level + 1)
        _lines += cleared
        _level = _lines // 10
    _spawn()


def _move(dx):
    global _px
    if _valid(_cells(_piece, _rot, _px + dx, _py)):
        _px += dx
        return True
    return False


def _rotate():
    global _rot, _px
    nr = (_rot + 1) % len(PIECES[_piece])
    for kick in (0, -1, 1, -2, 2):
        if _valid(_cells(_piece, nr, _px + kick, _py)):
            _rot, _px = nr, _px + kick
            return True
    return False


def _drop():
    global _py
    if _valid(_cells(_piece, _rot, _px, _py + 1)):
        _py += 1
        return True
    _lock_piece()
    return False


def _harddrop():
    global _py
    while _valid(_cells(_piece, _rot, _px, _py + 1)):
        _py += 1
    _lock_piece()


# ---------- plugin contract ----------
def _tick(g):
    while _run and g == _gen:
        time.sleep(max(0.33, 0.78 - _level * 0.05))   # ~30% slower gravity, display-safe floor
        if _run and g == _gen and not _over:
            with _mx:
                _drop()
            if _ctx is not None:
                try: _ctx.mark_dirty()
                except Exception: pass


def on_enter(ctx):
    global _run, _ctx, _gen
    _ctx = ctx
    with _mx:
        _reset()
    _gen += 1
    _run = True
    threading.Thread(target=_tick, args=(_gen,), daemon=True).start()
    ctx.mark_dirty()


def on_exit(ctx):
    global _run, _gen
    _run = False
    _gen += 1


def hud():
    return 'score %d' % _score


def _cellrect(d, ctx, x, y, col):
    px, py = BX + x * CELL, BY + y * CELL
    ctx.rr(d, (px + 1, py + 1, px + CELL - 1, py + CELL - 1), fill=col, r=2)


def _btn(d, ctx, box, ch):
    ctx.rr(d, box, fill=(55, 62, 78), outline=ctx.ACC, w=1, r=8)
    f = ctx.F_BIG if len(ch) == 1 else ctx.F_SM
    ctx.ct(d, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, ch, f, ctx.FG)


def draw(d, ctx):
    p, rot, ppx, ppy, over = _piece, _rot, _px, _py, _over    # snapshot vs tick thread
    b = _board
    ctx.rr(d, (BX - 2, BY - 2, BX + COLS * CELL + 2, BY + ROWS * CELL + 2),
           fill=(20, 24, 30), outline=ctx.LINE, w=1, r=4)
    for y in range(ROWS):
        row = b[y]
        for x in range(COLS):
            if row[x]:
                _cellrect(d, ctx, x, y, COL.get(row[x], (200, 200, 200)))
    if not over:
        for x, y in _cells(p, rot, ppx, ppy):
            if y >= 0:
                _cellrect(d, ctx, x, y, COL[p])
    # info panel
    px = 156
    ctx.rr(d, (px, 38, 472, 94), fill=ctx.TILE, outline=ctx.LINE, w=1, r=8)
    ctx.lt(d, px + 10, 53, 'SCORE', ctx.F_TINY, ctx.DIM)
    ctx.lt(d, px + 10, 71, str(_score), ctx.F_NM, ctx.ACC)
    ctx.lt(d, px + 108, 53, 'LINES %d' % _lines, ctx.F_TINY, ctx.DIM)
    ctx.lt(d, px + 108, 71, 'LEVEL %d' % _level, ctx.F_SM, ctx.FG)
    ctx.lt(d, px + 214, 53, 'NEXT', ctx.F_TINY, ctx.DIM)
    for dx, dy in PIECES[_next][0]:
        nx, ny = px + 250 + dx * 12, 58 + dy * 12
        ctx.rr(d, (nx, ny, nx + 11, ny + 11), fill=COL[_next], r=2)
    # controls
    _btn(d, ctx, (170, 100, 458, 142), 'ROTATE')
    _btn(d, ctx, (170, 150, 256, 202), '<')
    _btn(d, ctx, (262, 150, 366, 202), 'v')
    _btn(d, ctx, (372, 150, 458, 202), '>')
    _btn(d, ctx, (170, 210, 308, 256), 'DROP')
    ctx.rr(d, (314, 210, 458, 256), fill=(60, 70, 90), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, 386, 233, 'NEW', ctx.F_SM, ctx.FG)
    if over:
        cx = BX + COLS * CELL // 2
        cy = BY + ROWS * CELL // 2
        ctx.rr(d, (BX + 4, cy - 30, BX + COLS * CELL - 4, cy + 30), fill=(18, 22, 28), outline=(235, 80, 80), w=2, r=8)
        ctx.ct(d, cx, cy - 8, 'GAME', ctx.F_NM, (235, 90, 90))
        ctx.ct(d, cx, cy + 12, 'OVER', ctx.F_NM, (235, 90, 90))


def handle_touch(tx, ty, ctx):
    if 210 <= ty <= 256 and tx >= 314 and ctx.debounce(0.3):     # NEW
        on_enter(ctx)
        return
    if _over or not ctx.debounce(0.08):
        return
    act = None
    if 100 <= ty <= 142 and 170 <= tx <= 458:
        act = 'rot'
    elif 150 <= ty <= 202 and 170 <= tx <= 256:
        act = 'left'
    elif 150 <= ty <= 202 and 262 <= tx <= 366:
        act = 'soft'
    elif 150 <= ty <= 202 and 372 <= tx <= 458:
        act = 'right'
    elif 210 <= ty <= 256 and 170 <= tx <= 308:
        act = 'hard'
    if act:
        with _mx:
            if act == 'rot': _rotate()
            elif act == 'left': _move(-1)
            elif act == 'right': _move(1)
            elif act == 'soft': _drop()
            elif act == 'hard': _harddrop()
        ctx.mark_dirty()
