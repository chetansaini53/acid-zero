# Acid Zero game - Tic-Tac-Toe. Tap a cell to place your mark. 1-PLAYER = you (X)
# vs a perfect minimax AI (O) that never loses; 2-PLAYER = pass-and-play. Score is
# kept across rounds. Turn-based (redraw on tap).
META = {'name': 'Tic-Tac-Toe'}
BX, BY, CELL = 8, 42, 88

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]

_board = [0] * 9
_turn = 'X'
_mode = '1P'                 # '1P' (vs AI) | '2P'
_result = None               # None | 'X' | 'O' | 'draw'
_score = {'X': 0, 'O': 0, 'draw': 0}


# ---------- pure logic (unit-testable) ----------
def _winner(b):
    for a, x, c in LINES:
        if b[a] and b[a] == b[x] == b[c]:
            return b[a]
    return None


def _win_line(b):
    for ln in LINES:
        a, x, c = ln
        if b[a] and b[a] == b[x] == b[c]:
            return ln
    return None


def _minimax(b, player):
    w = _winner(b)
    if w == 'O':
        return 1
    if w == 'X':
        return -1
    if all(b):
        return 0
    nxt = 'X' if player == 'O' else 'O'
    scores = []
    for i in range(9):
        if not b[i]:
            b[i] = player
            scores.append(_minimax(b, nxt))
            b[i] = 0
    return max(scores) if player == 'O' else min(scores)


def _ai_move(b):
    best, bs = None, -2
    for i in range(9):
        if not b[i]:
            b[i] = 'O'
            s = _minimax(b, 'X')
            b[i] = 0
            if s > bs:
                bs, best = s, i
    return best


def _check():
    global _result
    w = _winner(_board)
    if w:
        _result = w
        _score[w] += 1
        return True
    if all(_board):
        _result = 'draw'
        _score['draw'] += 1
        return True
    return False


def _place(i):
    global _turn
    if _result or _board[i]:
        return
    _board[i] = _turn
    if _check():
        return
    _turn = 'O' if _turn == 'X' else 'X'
    if _mode == '1P' and _turn == 'O':
        mv = _ai_move(_board)
        if mv is not None:
            _board[mv] = 'O'
            if _check():
                return
            _turn = 'X'


def _new(keep_score=True):
    global _board, _turn, _result, _score
    _board = [0] * 9
    _turn = 'X'
    _result = None
    if not keep_score:
        _score = {'X': 0, 'O': 0, 'draw': 0}


# ---------- plugin contract ----------
def on_enter(ctx):
    _new(keep_score=False)
    ctx.mark_dirty()


def hud():
    if _result:
        return 'DRAW' if _result == 'draw' else '%s WINS' % _result
    return "%s's turn" % _turn


def draw(d, ctx):
    G = 3 * CELL
    ctx.rr(d, (BX - 2, BY - 2, BX + G + 2, BY + G + 2), fill=(24, 28, 34), outline=ctx.LINE, w=1, r=4)
    wl = _win_line(_board)
    for i in range(9):
        r, c = i // 3, i % 3
        x, y = BX + c * CELL, BY + r * CELL
        if wl and i in wl:
            ctx.rr(d, (x + 2, y + 2, x + CELL - 2, y + CELL - 2), fill=(40, 66, 48), r=4)
        v = _board[i]
        if v == 'X':
            d.line([(x + 20, y + 20), (x + CELL - 20, y + CELL - 20)], fill=(90, 200, 235), width=5)
            d.line([(x + CELL - 20, y + 20), (x + 20, y + CELL - 20)], fill=(90, 200, 235), width=5)
        elif v == 'O':
            d.ellipse((x + 18, y + 18, x + CELL - 18, y + CELL - 18), outline=(235, 150, 60), width=5)
    for i in range(1, 3):
        d.line([(BX + i * CELL, BY), (BX + i * CELL, BY + G)], fill=(90, 100, 118), width=2)
        d.line([(BX, BY + i * CELL), (BX + G, BY + i * CELL)], fill=(90, 100, 118), width=2)
    # right panel
    px = 286
    st = ('DRAW!' if _result == 'draw' else ('%s WINS!' % _result)) if _result else "%s's turn" % _turn
    sc = (255, 215, 60) if _result else ctx.ACC
    ctx.ct(d, 379, 56, st, ctx.F_NM, sc)
    ctx.rr(d, (px, 80, 472, 120), fill=(45, 55, 72), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, 379, 100, '1 PLAYER (vs AI)' if _mode == '1P' else '2 PLAYER', ctx.F_SM, ctx.FG)
    ctx.ct(d, 379, 150, 'SCORE', ctx.F_TINY, ctx.DIM)
    ctx.ct(d, 320, 176, 'X', ctx.F_SM, (90, 200, 235)); ctx.ct(d, 320, 196, str(_score['X']), ctx.F_NM, ctx.FG)
    ctx.ct(d, 379, 176, 'DRAW', ctx.F_TINY, ctx.DIM); ctx.ct(d, 379, 196, str(_score['draw']), ctx.F_NM, ctx.FG)
    ctx.ct(d, 438, 176, 'O', ctx.F_SM, (235, 150, 60)); ctx.ct(d, 438, 196, str(_score['O']), ctx.F_NM, ctx.FG)
    ctx.rr(d, (px, 250, 472, 290), fill=(60, 70, 90), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, 379, 270, 'NEW GAME', ctx.F_SM, ctx.FG)


def handle_touch(tx, ty, ctx):
    px = 286
    if 80 <= ty <= 120 and tx >= px and ctx.debounce(0.3):        # mode toggle
        global _mode
        _mode = '2P' if _mode == '1P' else '1P'
        _new()
        ctx.mark_dirty()
        return
    if 250 <= ty <= 290 and tx >= px and ctx.debounce(0.3):        # new game
        _new()
        ctx.mark_dirty()
        return
    if BX <= tx < BX + 3 * CELL and BY <= ty < BY + 3 * CELL and ctx.debounce(0.25):
        c, r = (tx - BX) // CELL, (ty - BY) // CELL
        _place(r * 3 + c)
        ctx.mark_dirty()
