# Acid Zero plugin - "Games": a small touch arcade for the handheld.
# The menu is a fixed 12-game roster; each game is a drop-in module in games/
# (games/<key>.py with META + draw + handle_touch). A game lights up as PLAY once
# its module exists, else shows SOON - so games are added one at a time.
# Single-touch / resistive friendly. Educational fun; own device.
import os, sys, importlib.util
for _p in ('/usr/local/bin', '/usr/local/lib/acid-apps', '/home/ella3'):
    if _p not in sys.path:
        sys.path.insert(0, _p)

META = {'name': 'Games', 'icon': 'ghost', 'color': (180, 95, 235)}

GAMES_DIR = '/usr/local/lib/acid-apps/games'
# (display name, module key) - order fixed; module lights up when its file exists.
ROSTER = [('2048', 'g2048'), ('Tetris', 'tetris'), ('Snake', 'snake'), ('Minesweeper', 'mines'),
          ('Breakout', 'breakout'), ('Sudoku', 'sudoku'), ('Sokoban', 'sokoban'), ('Simon', 'simon'),
          ('Tic-Tac-Toe', 'tictactoe'), ('Maze', 'maze'), ('Whack-Mole', 'whack'), ('Conway Life', 'life')]

_mods = {}          # key -> module (or None), loaded once
_view = 'menu'      # menu | play
_active = None      # active game module
_active_name = ''

COLS, ROWS = 3, 4


def _load(key):
    if key in _mods:
        return _mods[key]
    m = None
    p = os.path.join(GAMES_DIR, key + '.py')
    if os.path.exists(p):
        try:
            spec = importlib.util.spec_from_file_location('acidgame_' + key, p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            if not (hasattr(m, 'draw') and hasattr(m, 'handle_touch')):
                m = None
        except Exception as e:
            try: open('/tmp/acid_plugin_err.log', 'a').write('game %s: %s\n' % (key, e))
            except Exception: pass
            m = None
    _mods[key] = m
    return m


def on_enter(ctx):
    global _view, _active
    _view = 'menu'
    _active = None
    ctx.mark_dirty()


def on_exit(ctx):
    global _active
    if _active is not None and hasattr(_active, 'on_exit'):
        try: _active.on_exit(ctx)
        except Exception: pass
    _active = None


# ---------- menu ----------
def _draw_menu(d, ctx):
    ctx.topbar(d, 'GAMES')
    W = ctx.W
    cw = (W - 16) // COLS
    ch = (320 - 34) // ROWS
    for i, (name, key) in enumerate(ROSTER):
        c, r = i % COLS, i // COLS
        x0, y0 = 8 + c * cw, 34 + r * ch
        on = _load(key) is not None
        ctx.rr(d, (x0 + 4, y0 + 4, x0 + cw - 4, y0 + ch - 4), fill=ctx.TILE,
               outline=(ctx.ACC if on else ctx.LINE), w=(2 if on else 1), r=10)
        cx, cy = x0 + cw // 2, y0 + ch // 2
        ctx.ct(d, cx, cy - 8, name[:12], ctx.F_SM, (ctx.FG if on else ctx.DIM))
        ctx.ct(d, cx, cy + 12, ('PLAY' if on else 'SOON'), ctx.F_TINY, (ctx.ACC if on else (120, 130, 150)))


def _touch_menu(tx, ty, ctx):
    global _view, _active, _active_name
    if ty < 34:
        return
    W = ctx.W
    cw = (W - 16) // COLS
    ch = (320 - 34) // ROWS
    c = (tx - 8) // cw
    r = (ty - 34) // ch
    i = r * COLS + c
    if 0 <= c < COLS and 0 <= i < len(ROSTER) and ctx.debounce(0.3):
        name, key = ROSTER[i]
        m = _load(key)
        if m is not None:
            _active = m
            _active_name = name
            _view = 'play'
            if hasattr(m, 'on_enter'):
                try: m.on_enter(ctx)
                except Exception: pass
            ctx.mark_dirty()


# ---------- play ----------
def _draw_play(d, ctx):
    d.rectangle((0, 0, ctx.W, 28), fill=ctx.BARBG)
    d.line([(0, 28), (ctx.W, 28)], fill=ctx.LINE)
    ctx.rr(d, (6, 4, 92, 24), outline=ctx.ACC, w=1, r=5)
    ctx.ct(d, 49, 15, '< home', ctx.F_SM, ctx.ACC)
    ctx.ct(d, 150, 14, _active_name[:14], ctx.F_TIT, ctx.FG)
    hud = ''
    if _active is not None and hasattr(_active, 'hud'):
        try: hud = str(_active.hud())[:22]
        except Exception: hud = ''
    if hud:
        ctx.ct(d, 300, 14, hud, ctx.F_SM, ctx.ACC)
    ctx.rr(d, (410, 4, 472, 24), outline=(150, 190, 240), w=1, r=6)
    ctx.ct(d, 441, 14, 'MENU', ctx.F_TINY, (150, 190, 240))
    if _active is not None:
        try: _active.draw(d, ctx)
        except Exception: ctx.ct(d, ctx.W // 2, 170, 'game error', ctx.F_NM, (235, 80, 80))


def _touch_play(tx, ty, ctx):
    global _view, _active
    if ty <= 24 and tx >= 410 and ctx.debounce(0.3):       # MENU (top-right) -> game list
        if _active is not None and hasattr(_active, 'on_exit'):
            try: _active.on_exit(ctx)
            except Exception: pass
        _active = None
        _view = 'menu'
        ctx.mark_dirty()
        return
    if _active is not None:
        try: _active.handle_touch(tx, ty, ctx)
        except Exception: pass


# ---------- dispatch ----------
def draw(d, ctx):
    (_draw_play if _view == 'play' else _draw_menu)(d, ctx)


def handle_touch(tx, ty, ctx):
    (_touch_play if _view == 'play' else _touch_menu)(tx, ty, ctx)
