# Acid Zero game - 2048. Tap the arrow pad to slide the board; equal tiles merge.
# Reach 2048 to win; no moves left = game over. Turn-based (redraw on tap only).
import random

META = {'name': '2048'}
N = 4
BX, BY, CELL, GAP = 8, 46, 58, 4        # board geometry (top-left, cell size, gap)
BW = N * (CELL + GAP)                     # board pixel span

_board = [[0] * N for _ in range(N)]
_score = 0
_best = 0
_over = False
_won = False

CLR = {0: (46, 50, 58), 2: (118, 128, 148), 4: (90, 150, 220), 8: (235, 160, 60),
       16: (235, 130, 55), 32: (235, 95, 70), 64: (235, 70, 70), 128: (235, 205, 80),
       256: (235, 195, 55), 512: (240, 185, 40), 1024: (245, 175, 28), 2048: (255, 215, 60)}


# ---------- pure game logic (unit-testable, no UI) ----------
def _slide(line):
    """Slide + merge one line toward index 0. -> (newline, points_gained)."""
    nums = [v for v in line if v]
    out, gain, i = [], 0, 0
    while i < len(nums):
        if i + 1 < len(nums) and nums[i] == nums[i + 1]:
            out.append(nums[i] * 2)
            gain += nums[i] * 2
            i += 2
        else:
            out.append(nums[i])
            i += 1
    return out + [0] * (N - len(out)), gain


def _move(dr):
    """Apply a move ('L','R','U','D') to _board. -> True if the board changed."""
    global _board, _score
    b = _board
    if dr in ('L', 'R'):
        newb = []
        for r in range(N):
            line = b[r][:]
            if dr == 'R':
                line = line[::-1]
            s, g = _slide(line)
            _score += g
            newb.append(s[::-1] if dr == 'R' else s)
    else:
        newb = [[0] * N for _ in range(N)]
        for c in range(N):
            col = [b[r][c] for r in range(N)]
            if dr == 'D':
                col = col[::-1]
            s, g = _slide(col)
            _score += g
            if dr == 'D':
                s = s[::-1]
            for r in range(N):
                newb[r][c] = s[r]
    if newb != b:
        _board = newb
        return True
    return False


def _can_move():
    for r in range(N):
        for c in range(N):
            if _board[r][c] == 0:
                return True
            if c + 1 < N and _board[r][c] == _board[r][c + 1]:
                return True
            if r + 1 < N and _board[r][c] == _board[r + 1][c]:
                return True
    return False


def _spawn():
    empt = [(r, c) for r in range(N) for c in range(N) if _board[r][c] == 0]
    if empt:
        r, c = random.choice(empt)
        _board[r][c] = 4 if random.random() < 0.1 else 2


def _reset():
    global _board, _score, _over, _won
    _board = [[0] * N for _ in range(N)]
    _score = 0
    _over = False
    _won = False
    _spawn()
    _spawn()


# ---------- plugin contract ----------
def on_enter(ctx):
    _reset()
    ctx.mark_dirty()


def hud():
    return 'score %d%s' % (_score, '  WON!' if _won else '')


def _do(dr, ctx):
    global _over, _won, _best
    if _over:
        return
    if _move(dr):
        _spawn()
        if any(_board[r][c] >= 2048 for r in range(N) for c in range(N)):
            _won = True
        if not _can_move():
            _over = True
        if _score > _best:
            _best = _score
        ctx.mark_dirty()


def _btn(d, ctx, box, ch):
    ctx.rr(d, box, fill=(55, 62, 78), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, ch, ctx.F_BIG, ctx.FG)


def draw(d, ctx):
    ctx.rr(d, (BX - 3, BY - 3, BX + BW + 1, BY + BW + 1), fill=(30, 33, 40), r=8)
    for r in range(N):
        for c in range(N):
            v = _board[r][c]
            x, y = BX + c * (CELL + GAP), BY + r * (CELL + GAP)
            ctx.rr(d, (x, y, x + CELL, y + CELL), fill=CLR.get(v, (255, 215, 60)), r=6)
            if v:
                tc = (30, 25, 10) if v >= 8 else (245, 245, 245)
                ctx.ct(d, x + CELL // 2, y + CELL // 2, str(v), ctx.F_NM if v < 128 else ctx.F_SM, tc)
    # right panel: score/best
    px = 270
    ctx.rr(d, (px, 46, 472, 96), fill=ctx.TILE, outline=ctx.LINE, w=1, r=8)
    ctx.ct(d, px + 52, 62, 'SCORE', ctx.F_TINY, ctx.DIM)
    ctx.ct(d, px + 52, 80, str(_score), ctx.F_NM, ctx.ACC)
    ctx.ct(d, px + 152, 62, 'BEST', ctx.F_TINY, ctx.DIM)
    ctx.ct(d, px + 152, 80, str(_best), ctx.F_NM, ctx.FG)
    # arrow pad
    _btn(d, ctx, (346, 110, 406, 158), '^')
    _btn(d, ctx, (346, 214, 406, 262), 'v')
    _btn(d, ctx, (290, 162, 344, 210), '<')
    _btn(d, ctx, (408, 162, 462, 210), '>')
    # new game
    ctx.rr(d, (px, 272, 472, 306), fill=(60, 70, 90), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, px + 101, 289, 'NEW GAME', ctx.F_SM, ctx.FG)
    if _over:
        ctx.rr(d, (BX + 8, BY + BW // 2 - 30, BX + BW - 8, BY + BW // 2 + 30), fill=(18, 22, 28), outline=(235, 80, 80), w=2, r=10)
        ctx.ct(d, BX + BW // 2, BY + BW // 2 - 8, 'GAME OVER', ctx.F_NM, (235, 90, 90))
        ctx.ct(d, BX + BW // 2, BY + BW // 2 + 12, 'tap NEW GAME', ctx.F_SM, ctx.DIM)


def handle_touch(tx, ty, ctx):
    if 272 <= ty <= 306 and tx >= 270 and ctx.debounce(0.3):
        on_enter(ctx)
        return
    if not ctx.debounce(0.16):
        return
    if 110 <= ty <= 158 and 346 <= tx <= 406:
        _do('U', ctx)
    elif 214 <= ty <= 262 and 346 <= tx <= 406:
        _do('D', ctx)
    elif 162 <= ty <= 210 and 290 <= tx <= 344:
        _do('L', ctx)
    elif 162 <= ty <= 210 and 408 <= tx <= 462:
        _do('R', ctx)
