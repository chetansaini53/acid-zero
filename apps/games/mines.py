# Acid Zero game - Minesweeper. Tap cells to dig; toggle to FLAG mode to mark mines.
# First dig is always safe (mines placed after, avoiding it + neighbours). Flood-fill
# on empty cells; reveal all safe cells to win, hit a mine to lose. Turn-based.
import random

META = {'name': 'Minesweeper'}
COLS, ROWS, MINES = 9, 8, 10
CELL, BX, BY = 30, 8, 44

_mines = set()
_revealed = set()
_flagged = set()
_over = False
_won = False
_placed = False
_mode = 'dig'          # 'dig' | 'flag'

NUMCOL = {1: (90, 150, 235), 2: (40, 190, 110), 3: (235, 90, 90), 4: (120, 110, 220),
          5: (200, 90, 60), 6: (60, 190, 200), 7: (210, 210, 210), 8: (150, 150, 150)}


# ---------- pure logic (unit-testable) ----------
def _adj(cell):
    c, r = cell
    return [(c + dc, r + dr) for dc in (-1, 0, 1) for dr in (-1, 0, 1)
            if (dc, dr) != (0, 0) and 0 <= c + dc < COLS and 0 <= r + dr < ROWS]


def _count(cell):
    return sum(1 for n in _adj(cell) if n in _mines)


def _place(safe):
    global _mines, _placed
    forbidden = set([safe]) | set(_adj(safe))
    pool = [(c, r) for c in range(COLS) for r in range(ROWS) if (c, r) not in forbidden]
    _mines = set(random.sample(pool, min(MINES, len(pool))))
    _placed = True


def _reveal(cell):
    global _over, _won
    if _over or cell in _revealed or cell in _flagged:
        return
    if not _placed:
        _place(cell)
    if cell in _mines:
        _over = True
        return
    stack = [cell]
    while stack:
        cur = stack.pop()
        if cur in _revealed or cur in _flagged:
            continue
        _revealed.add(cur)
        if _count(cur) == 0:
            for n in _adj(cur):
                if n not in _revealed and n not in _mines:
                    stack.append(n)
    if len(_revealed) == COLS * ROWS - len(_mines):
        _won = True
        _over = True


def _flag(cell):
    if _over or cell in _revealed:
        return
    if cell in _flagged:
        _flagged.discard(cell)
    else:
        _flagged.add(cell)


def _reset():
    global _mines, _revealed, _flagged, _over, _won, _placed
    _mines = set()
    _revealed = set()
    _flagged = set()
    _over = False
    _won = False
    _placed = False


# ---------- plugin contract ----------
def on_enter(ctx):
    _reset()
    ctx.mark_dirty()


def hud():
    return ('WON!' if _won else ('BOOM' if _over else 'mines %d' % (MINES - len(_flagged))))


def draw(d, ctx):
    for c in range(COLS):
        for r in range(ROWS):
            cell = (c, r)
            x, y = BX + c * CELL, BY + r * CELL
            if cell in _revealed:
                ctx.rr(d, (x + 1, y + 1, x + CELL - 1, y + CELL - 1), fill=(38, 42, 50), r=3)
                n = _count(cell)
                if n:
                    ctx.ct(d, x + CELL // 2, y + CELL // 2, str(n), ctx.F_NM, NUMCOL.get(n, (220, 220, 220)))
            elif _over and cell in _mines:
                ctx.rr(d, (x + 1, y + 1, x + CELL - 1, y + CELL - 1), fill=(70, 30, 30), r=3)
                d.ellipse((x + 9, y + 9, x + CELL - 9, y + CELL - 9), fill=(235, 80, 80))
            else:
                ctx.rr(d, (x + 1, y + 1, x + CELL - 1, y + CELL - 1), fill=(72, 80, 96),
                       outline=(96, 104, 120), w=1, r=3)
                if cell in _flagged:
                    ctx.ct(d, x + CELL // 2, y + CELL // 2, 'F', ctx.F_NM, (235, 90, 90))
    # right panel
    px = 286
    ctx.rr(d, (px, 46, 472, 78), fill=ctx.TILE, outline=ctx.LINE, w=1, r=8)
    ctx.ct(d, px + 93, 56, 'MINES LEFT', ctx.F_TINY, ctx.DIM)
    ctx.ct(d, px + 93, 70, str(MINES - len(_flagged)), ctx.F_NM, ctx.ACC)
    dig = (_mode == 'dig')
    ctx.rr(d, (px, 92, 472, 134), fill=(30, 90, 60) if dig else (90, 55, 30),
           outline=ctx.ACC, w=2, r=10)
    ctx.ct(d, px + 93, 106, 'MODE', ctx.F_TINY, ctx.FG)
    ctx.ct(d, px + 93, 122, 'DIG' if dig else 'FLAG', ctx.F_NM, ctx.FG)
    st = 'YOU WIN!' if _won else ('BOOM!' if _over else 'PLAYING')
    sc = (255, 215, 60) if _won else ((235, 90, 90) if _over else ctx.DIM)
    ctx.ct(d, px + 93, 164, st, ctx.F_NM, sc)
    ctx.rr(d, (px, 250, 472, 288), fill=(60, 70, 90), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, px + 93, 269, 'NEW GAME', ctx.F_SM, ctx.FG)


def handle_touch(tx, ty, ctx):
    px = 286
    if 92 <= ty <= 134 and tx >= px and ctx.debounce(0.3):        # MODE toggle
        global _mode
        _mode = 'flag' if _mode == 'dig' else 'dig'
        ctx.mark_dirty()
        return
    if 250 <= ty <= 288 and tx >= px and ctx.debounce(0.3):        # NEW GAME
        on_enter(ctx)
        return
    # board
    if BX <= tx < BX + COLS * CELL and BY <= ty < BY + ROWS * CELL and ctx.debounce(0.18):
        c, r = (tx - BX) // CELL, (ty - BY) // CELL
        if 0 <= c < COLS and 0 <= r < ROWS:
            if _mode == 'flag':
                _flag((c, r))
            else:
                _reveal((c, r))
            ctx.mark_dirty()
