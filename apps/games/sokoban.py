# Acid Zero game - Sokoban. Arrow pad moves the player; walking into a box pushes
# it (if the space beyond is clear). Get every box onto a target to solve. RESET
# restarts the level, NEXT advances. Turn-based (redraw on tap).
META = {'name': 'Sokoban'}
FX, FY, FW, FH = 8, 42, 288, 270      # play field

# # wall  . target  $ box  * box-on-target  @ player  + player-on-target
LEVELS = [
    ["#####",
     "#@$.#",
     "#####"],
    ["######",
     "#@$ .#",
     "######"],
    ["#######",
     "#@$  .#",
     "#     #",
     "# $  .#",
     "#######"],
    ["######",
     "#   .#",
     "# $@ #",
     "#    #",
     "######"],
]

_walls = set()
_targets = set()
_boxes = set()
_player = (0, 0)
_rows = _cols = 0
_moves = 0
_win = False
_level = 0


# ---------- pure logic (unit-testable) ----------
def _load(idx):
    global _walls, _targets, _boxes, _player, _rows, _cols, _moves, _win, _level
    _level = idx % len(LEVELS)
    lvl = LEVELS[_level]
    _walls, _targets, _boxes, _player = set(), set(), set(), (0, 0)
    _rows, _cols = len(lvl), max(len(r) for r in lvl)
    for r, line in enumerate(lvl):
        for c, ch in enumerate(line):
            p = (r, c)
            if ch == '#':
                _walls.add(p)
            elif ch == '.':
                _targets.add(p)
            elif ch == '$':
                _boxes.add(p)
            elif ch == '*':
                _boxes.add(p); _targets.add(p)
            elif ch == '@':
                _player = p
            elif ch == '+':
                _player = p; _targets.add(p)
    _moves, _win = 0, False


def _move(dr, dc):
    global _player, _moves, _win
    if _win:
        return
    r, c = _player
    t = (r + dr, c + dc)
    if t in _walls:
        return
    if t in _boxes:
        b = (r + 2 * dr, c + 2 * dc)
        if b in _walls or b in _boxes:
            return
        _boxes.discard(t)
        _boxes.add(b)
    _player = t
    _moves += 1
    if _boxes == _targets:
        _win = True


# ---------- plugin contract ----------
def on_enter(ctx):
    _load(0)
    ctx.mark_dirty()


def hud():
    return 'SOLVED!' if _win else 'lvl %d/%d  moves %d' % (_level + 1, len(LEVELS), _moves)


def _btn(d, ctx, box, ch, col=None):
    ctx.rr(d, box, fill=(col or (55, 62, 78)), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, ch, ctx.F_BIG if len(ch) == 1 else ctx.F_SM, ctx.FG)


def draw(d, ctx):
    cs = min(FW // _cols, FH // _rows) if _cols and _rows else 30
    ox = FX + (FW - cs * _cols) // 2
    oy = FY + (FH - cs * _rows) // 2
    for r in range(_rows):
        for c in range(_cols):
            p = (r, c)
            x, y = ox + c * cs, oy + r * cs
            ctx.rr(d, (x, y, x + cs - 1, y + cs - 1), fill=((68, 76, 92) if p in _walls else (30, 34, 42)), r=2)
            if p in _targets and p not in _boxes and p != _player:
                d.ellipse((x + cs // 2 - 4, y + cs // 2 - 4, x + cs // 2 + 4, y + cs // 2 + 4), outline=(235, 205, 80), width=2)
            if p in _boxes:
                bc = (70, 200, 110) if p in _targets else (215, 150, 60)
                ctx.rr(d, (x + 4, y + 4, x + cs - 4, y + cs - 4), fill=bc, r=3)
            if p == _player:
                d.ellipse((x + 5, y + 5, x + cs - 5, y + cs - 5), fill=(90, 200, 235))
    # arrow pad
    _btn(d, ctx, (356, 74, 416, 118), '^')
    _btn(d, ctx, (298, 124, 352, 168), '<')
    _btn(d, ctx, (420, 124, 472, 168), '>')
    _btn(d, ctx, (356, 174, 416, 218), 'v')
    _btn(d, ctx, (298, 232, 382, 272), 'RESET', (90, 55, 55))
    _btn(d, ctx, (390, 232, 472, 272), 'NEXT', (60, 70, 90))
    if _win:
        cx, cy = FX + FW // 2, FY + FH // 2
        ctx.rr(d, (cx - 96, cy - 26, cx + 96, cy + 24), fill=(18, 22, 28), outline=(255, 215, 60), w=2, r=10)
        ctx.ct(d, cx, cy - 4, 'LEVEL SOLVED!', ctx.F_NM, (255, 215, 60))
        ctx.ct(d, cx, cy + 14, 'tap NEXT', ctx.F_SM, ctx.DIM)


def handle_touch(tx, ty, ctx):
    if 232 <= ty <= 272 and 298 <= tx <= 382 and ctx.debounce(0.3):
        _load(_level)
        ctx.mark_dirty()
        return
    if 232 <= ty <= 272 and 390 <= tx <= 472 and ctx.debounce(0.3):
        _load(_level + 1)
        ctx.mark_dirty()
        return
    if not ctx.debounce(0.12):
        return
    if 74 <= ty <= 118 and 356 <= tx <= 416:
        _move(-1, 0)
    elif 174 <= ty <= 218 and 356 <= tx <= 416:
        _move(1, 0)
    elif 124 <= ty <= 168 and 298 <= tx <= 352:
        _move(0, -1)
    elif 124 <= ty <= 168 and 420 <= tx <= 472:
        _move(0, 1)
    else:
        return
    ctx.mark_dirty()
