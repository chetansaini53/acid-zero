# Acid Zero game - Maze. A fresh random maze each round (recursive-backtracker,
# perfect maze). Arrow pad moves the blue dot; reach the green exit (bottom-right)
# to solve. NEW makes a new maze. Turn-based (redraw on tap).
import random

META = {'name': 'Maze'}
FX, FY, FW, FH = 8, 42, 288, 270
COLS, ROWS = 10, 9
DIRS = {'N': (0, -1), 'S': (0, 1), 'E': (1, 0), 'W': (-1, 0)}
OPP = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}

_open = {}
_player = (0, 0)
_win = False


# ---------- pure logic (unit-testable) ----------
def _gen():
    global _open
    _open = {(c, r): set() for c in range(COLS) for r in range(ROWS)}
    visited = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        c, r = stack[-1]
        nbrs = []
        for d, (dc, dr) in DIRS.items():
            nc, nr = c + dc, r + dr
            if 0 <= nc < COLS and 0 <= nr < ROWS and (nc, nr) not in visited:
                nbrs.append((d, (nc, nr)))
        if nbrs:
            d, (nc, nr) = random.choice(nbrs)
            _open[(c, r)].add(d)
            _open[(nc, nr)].add(OPP[d])
            visited.add((nc, nr))
            stack.append((nc, nr))
        else:
            stack.pop()


def _reset():
    global _player, _win
    _gen()
    _player = (0, 0)
    _win = False


def _move(d):
    global _player, _win
    if _win or d not in _open[_player]:
        return
    dc, dr = DIRS[d]
    _player = (_player[0] + dc, _player[1] + dr)
    if _player == (COLS - 1, ROWS - 1):
        _win = True


# ---------- plugin contract ----------
def on_enter(ctx):
    _reset()
    ctx.mark_dirty()


def hud():
    return 'SOLVED!' if _win else 'reach the green exit'


def _btn(d, ctx, box, ch, col=None):
    ctx.rr(d, box, fill=(col or (55, 62, 78)), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, ch, ctx.F_BIG if len(ch) == 1 else ctx.F_SM, ctx.FG)


def draw(d, ctx):
    cs = min(FW // COLS, FH // ROWS)
    ox = FX + (FW - cs * COLS) // 2
    oy = FY + (FH - cs * ROWS) // 2
    ctx.rr(d, (ox - 2, oy - 2, ox + cs * COLS + 2, oy + cs * ROWS + 2), fill=(24, 28, 34), r=4)
    ex, ey = ox + (COLS - 1) * cs, oy + (ROWS - 1) * cs
    ctx.rr(d, (ex + 2, ey + 2, ex + cs - 2, ey + cs - 2), fill=(30, 100, 62), r=2)
    wc = (120, 130, 150)
    for r in range(ROWS):
        for c in range(COLS):
            x, y = ox + c * cs, oy + r * cs
            o = _open[(c, r)]
            if 'N' not in o:
                d.line([(x, y), (x + cs, y)], fill=wc, width=2)
            if 'W' not in o:
                d.line([(x, y), (x, y + cs)], fill=wc, width=2)
            if 'S' not in o:
                d.line([(x, y + cs), (x + cs, y + cs)], fill=wc, width=2)
            if 'E' not in o:
                d.line([(x + cs, y), (x + cs, y + cs)], fill=wc, width=2)
    px, py = ox + _player[0] * cs, oy + _player[1] * cs
    d.ellipse((px + 5, py + 5, px + cs - 5, py + cs - 5), fill=(90, 200, 235))
    _btn(d, ctx, (356, 74, 416, 118), '^')
    _btn(d, ctx, (298, 124, 352, 168), '<')
    _btn(d, ctx, (420, 124, 472, 168), '>')
    _btn(d, ctx, (356, 174, 416, 218), 'v')
    _btn(d, ctx, (298, 236, 472, 278), 'NEW MAZE', (60, 70, 90))
    if _win:
        cx, cy = FX + FW // 2, FY + FH // 2
        ctx.rr(d, (cx - 90, cy - 24, cx + 90, cy + 24), fill=(18, 22, 28), outline=(255, 215, 60), w=2, r=10)
        ctx.ct(d, cx, cy - 2, 'SOLVED!', ctx.F_BIG, (255, 215, 60))
        ctx.ct(d, cx, cy + 16, 'tap NEW MAZE', ctx.F_SM, ctx.DIM)


def handle_touch(tx, ty, ctx):
    if 236 <= ty <= 278 and 298 <= tx <= 472 and ctx.debounce(0.3):
        _reset()
        ctx.mark_dirty()
        return
    if not ctx.debounce(0.12):
        return
    if 74 <= ty <= 118 and 356 <= tx <= 416:
        _move('N')
    elif 174 <= ty <= 218 and 356 <= tx <= 416:
        _move('S')
    elif 124 <= ty <= 168 and 298 <= tx <= 352:
        _move('W')
    elif 124 <= ty <= 168 and 420 <= tx <= 472:
        _move('E')
    else:
        return
    ctx.mark_dirty()
