# Acid Zero game - Sudoku. Tap a cell to select, tap a number (1-9) to fill it.
# Givens are fixed; conflicts turn red; fill the whole grid validly to win.
# Turn-based (redraw on tap). Puzzle = a shuffled valid solution with cells removed.
import random

META = {'name': 'Sudoku'}
BX, BY, CELL = 8, 42, 30
G = 9 * CELL

_grid = [[0] * 9 for _ in range(9)]
_given = [[False] * 9 for _ in range(9)]
_sel = None
_win = False


# ---------- pure logic (unit-testable) ----------
def _gen_solution():
    base, side = 3, 9
    def pat(r, c):
        return (base * (r % base) + r // base + c) % side
    rows = [g * base + r for g in random.sample(range(base), base) for r in random.sample(range(base), base)]
    cols = [g * base + c for g in random.sample(range(base), base) for c in random.sample(range(base), base)]
    nums = random.sample(range(1, side + 1), side)
    return [[nums[pat(r, c)] for c in cols] for r in rows]


def _conflict(r, c):
    v = _grid[r][c]
    if v == 0:
        return False
    for i in range(9):
        if i != c and _grid[r][i] == v:
            return True
        if i != r and _grid[i][c] == v:
            return True
    br, bc = (r // 3) * 3, (c // 3) * 3
    for rr in range(br, br + 3):
        for cc in range(bc, bc + 3):
            if (rr, cc) != (r, c) and _grid[rr][cc] == v:
                return True
    return False


def _check_win():
    global _win
    for r in range(9):
        for c in range(9):
            if _grid[r][c] == 0 or _conflict(r, c):
                return
    _win = True


def _reset():
    global _grid, _given, _sel, _win
    sol = _gen_solution()
    puzzle = [row[:] for row in sol]
    cells = [(r, c) for r in range(9) for c in range(9)]
    random.shuffle(cells)
    for r, c in cells[:48]:          # remove 48 -> 33 givens (medium)
        puzzle[r][c] = 0
    _grid = puzzle
    _given = [[puzzle[r][c] != 0 for c in range(9)] for r in range(9)]
    _sel = None
    _win = False


# ---------- plugin contract ----------
def on_enter(ctx):
    _reset()
    ctx.mark_dirty()


def hud():
    if _win:
        return 'SOLVED!'
    left = sum(1 for r in range(9) for c in range(9) if _grid[r][c] == 0)
    return '%d left' % left


def draw(d, ctx):
    ctx.rr(d, (BX - 2, BY - 2, BX + G + 2, BY + G + 2), fill=(24, 28, 34), outline=ctx.LINE, w=1, r=4)
    if _sel:
        sr, sc = _sel
        x, y = BX + sc * CELL, BY + sr * CELL
        ctx.rr(d, (x + 1, y + 1, x + CELL - 1, y + CELL - 1), fill=(45, 72, 60), r=2)
    for i in range(10):
        thick = (i % 3 == 0)
        wdt = 2 if thick else 1
        lc = (120, 130, 150) if thick else (52, 58, 70)
        d.line([(BX + i * CELL, BY), (BX + i * CELL, BY + G)], fill=lc, width=wdt)
        d.line([(BX, BY + i * CELL), (BX + G, BY + i * CELL)], fill=lc, width=wdt)
    for r in range(9):
        for c in range(9):
            v = _grid[r][c]
            if v:
                col = (235, 90, 90) if _conflict(r, c) else (ctx.FG if _given[r][c] else (90, 200, 235))
                ctx.ct(d, BX + c * CELL + CELL // 2, BY + r * CELL + CELL // 2, str(v), ctx.F_NM, col)
    # number pad
    for k in range(1, 10):
        col, row = (k - 1) % 3, (k - 1) // 3
        bx, by = 290 + col * 60, 52 + row * 50
        ctx.rr(d, (bx, by, bx + 56, by + 44), fill=(55, 62, 78), outline=ctx.ACC, w=1, r=6)
        ctx.ct(d, bx + 28, by + 22, str(k), ctx.F_BIG, ctx.FG)
    ctx.rr(d, (290, 204, 466, 244), fill=(90, 55, 55), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, 378, 224, 'ERASE', ctx.F_SM, ctx.FG)
    ctx.rr(d, (290, 250, 466, 290), fill=(60, 70, 90), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, 378, 270, 'NEW GAME', ctx.F_SM, ctx.FG)
    if _win:
        ctx.rr(d, (BX + 30, BY + G // 2 - 26, BX + G - 30, BY + G // 2 + 24), fill=(18, 22, 28), outline=(255, 215, 60), w=2, r=10)
        ctx.ct(d, BX + G // 2, BY + G // 2, 'SOLVED!', ctx.F_BIG, (255, 215, 60))


def handle_touch(tx, ty, ctx):
    global _sel
    if 250 <= ty <= 290 and 290 <= tx <= 466 and ctx.debounce(0.3):     # NEW GAME (any time)
        _reset()
        ctx.mark_dirty()
        return
    if _win:
        return
    n = 0
    for k in range(1, 10):
        col, row = (k - 1) % 3, (k - 1) // 3
        bx, by = 290 + col * 60, 52 + row * 50
        if bx <= tx <= bx + 56 and by <= ty <= by + 44:
            n = k
            break
    if n:
        if ctx.debounce(0.2) and _sel and not _given[_sel[0]][_sel[1]]:
            _grid[_sel[0]][_sel[1]] = n
            _check_win()
            ctx.mark_dirty()
        return
    if 204 <= ty <= 244 and 290 <= tx <= 466:                            # ERASE
        if ctx.debounce(0.2) and _sel and not _given[_sel[0]][_sel[1]]:
            _grid[_sel[0]][_sel[1]] = 0
            ctx.mark_dirty()
        return
    if BX <= tx < BX + G and BY <= ty < BY + G and ctx.debounce(0.12):    # select cell
        _sel = ((ty - BY) // CELL, (tx - BX) // CELL)
        ctx.mark_dirty()
