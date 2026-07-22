# Acid Zero game - Breakout. Tap anywhere in the field to move the paddle there;
# bounce the ball to break all bricks. 3 lives. Real-time via a tick thread.
import threading
import time

META = {'name': 'Breakout'}
BX, BY, FW, FH = 8, 42, 464, 264            # play field (x,y,w,h)
BCOLS, BROWS = 8, 4
BRICKW, BRICKH, BRICK_Y0 = FW // BCOLS, 16, 52
PADDLE_W, PADDLE_H, PADDLE_Y = 72, 8, 292
BALL_R = 5
BRICKCOL = [(235, 80, 80), (235, 150, 50), (235, 205, 80), (70, 200, 110)]

_bricks = [[True] * BCOLS for _ in range(BROWS)]
_fx, _fy, _vx, _vy = BX + FW / 2, PADDLE_Y - 40, 4.0, -4.5
_cx = BX + FW // 2
_lives, _score = 3, 0
_over = False
_won = False
_run = False
_gen = 0
_ctx = None


# ---------- pure logic (unit-testable) ----------
def _reset():
    global _bricks, _fx, _fy, _vx, _vy, _cx, _lives, _score, _over, _won
    _bricks = [[True] * BCOLS for _ in range(BROWS)]
    _fx, _fy, _vx, _vy = BX + FW / 2, PADDLE_Y - 40, 4.0, -4.5
    _cx = BX + FW // 2
    _lives, _score = 3, 0
    _over = _won = False


def _bricks_left():
    return sum(1 for row in _bricks for b in row if b)


def _step():
    global _fx, _fy, _vx, _vy, _lives, _over, _won, _score
    if _over:
        return
    _fx += _vx
    _fy += _vy
    if _fx < BX + BALL_R:
        _fx, _vx = BX + BALL_R, -_vx
    elif _fx > BX + FW - BALL_R:
        _fx, _vx = BX + FW - BALL_R, -_vx
    if _fy < BY + BALL_R:
        _fy, _vy = BY + BALL_R, -_vy
    # paddle
    if _vy > 0 and PADDLE_Y - BALL_R <= _fy <= PADDLE_Y + PADDLE_H and _cx - PADDLE_W // 2 <= _fx <= _cx + PADDLE_W // 2:
        _vy = -abs(_vy)
        _fy = PADDLE_Y - BALL_R
        _vx = max(-7.0, min(7.0, _vx + (_fx - _cx) * 0.08))
    # brick
    col = int((_fx - BX) // BRICKW)
    row = int((_fy - BRICK_Y0) // BRICKH)
    if 0 <= row < BROWS and 0 <= col < BCOLS and _bricks[row][col]:
        _bricks[row][col] = False
        _score += 10
        _vy = -_vy
        if _bricks_left() == 0:
            _won = _over = True
    # fall
    if _fy > BY + FH:
        _lives -= 1
        if _lives <= 0:
            _over = True
        else:
            _fx, _fy, _vx, _vy = BX + FW / 2, PADDLE_Y - 40, 4.0, -4.5


# ---------- plugin contract ----------
def _tick(g):
    while _run and g == _gen:
        time.sleep(0.10)
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
    _gen += 1


def hud():
    return 'score %d  lives %d' % (_score, _lives)


def draw(d, ctx):
    ctx.rr(d, (BX - 2, BY - 2, BX + FW + 2, BY + FH + 2), fill=(18, 22, 28), outline=ctx.LINE, w=1, r=4)
    for r in range(BROWS):
        for c in range(BCOLS):
            if _bricks[r][c]:
                x, y = BX + c * BRICKW, BRICK_Y0 + r * BRICKH
                ctx.rr(d, (x + 1, y + 1, x + BRICKW - 1, y + BRICKH - 1), fill=BRICKCOL[r % len(BRICKCOL)], r=2)
    # paddle
    ctx.rr(d, (_cx - PADDLE_W // 2, PADDLE_Y, _cx + PADDLE_W // 2, PADDLE_Y + PADDLE_H), fill=(90, 200, 235), r=3)
    # ball
    d.ellipse((int(_fx) - BALL_R, int(_fy) - BALL_R, int(_fx) + BALL_R, int(_fy) + BALL_R), fill=(245, 245, 245))
    if _over:
        cx, cy = BX + FW // 2, BY + FH // 2
        ctx.rr(d, (cx - 110, cy - 44, cx + 110, cy + 34), fill=(18, 22, 28), outline=ctx.ACC, w=2, r=10)
        ctx.ct(d, cx, cy - 22, 'YOU WIN!' if _won else 'GAME OVER',
               ctx.F_BIG, (255, 215, 60) if _won else (235, 90, 90))
        ctx.rr(d, (cx - 70, cy - 2, cx + 70, cy + 30), fill=(60, 70, 90), outline=ctx.ACC, w=1, r=8)
        ctx.ct(d, cx, cy + 14, 'NEW GAME', ctx.F_SM, ctx.FG)


def handle_touch(tx, ty, ctx):
    global _cx
    if _over:
        cx, cy = BX + FW // 2, BY + FH // 2
        if cx - 70 <= tx <= cx + 70 and cy - 2 <= ty <= cy + 30 and ctx.debounce(0.3):
            on_enter(ctx)
        return
    if BX <= tx <= BX + FW and BY <= ty <= BY + FH and ctx.debounce(0.02):
        _cx = max(BX + PADDLE_W // 2, min(BX + FW - PADDLE_W // 2, tx))
        ctx.mark_dirty()
