# Acid Zero plugin - "Honeypot": low-interaction fake SSH/HTTP/Telnet trap that logs who
# probes the device and what creds/commands they try - live on screen. Pure DEFENSIVE: it
# only listens + logs, never grants access. A honeypot has zero legit users, so any hit is
# a scan/intrusion attempt. OWN-NETWORK / authorized monitoring only. (i) = Learn (detect &
# defend). See ETHICS.md.
import os
import signal

META = {'name': 'Honeypot', 'icon': 'flask', 'color': (235, 190, 60)}

DAEMON = '/usr/local/bin/acid-honeypot.py'
STATUS = '/tmp/acid_honeypot_status'
PIDFILE = '/tmp/acid_honeypot.pid'

_view = 'main'          # main | info


def _pid():
    try:
        p = int(open(PIDFILE).read().strip())
        os.kill(p, 0)       # raises if not alive
        return p
    except Exception:
        return 0


def _running():
    return _pid() > 0


def _start(ctx):
    if not _running():
        ctx.popen(['python3', DAEMON])


def _stop(ctx):
    p = _pid()
    if p:
        try:
            os.kill(p, signal.SIGTERM)
        except Exception:
            pass


def on_enter(ctx):
    global _view
    _view = 'main'
    ctx.mark_dirty()


def _parse(ctx):
    txt = ctx.fread(STATUS)
    running = txt.startswith('RUNNING') and _running()
    listen = ''
    total = '0'
    uniq = '0'
    hits = []
    in_hits = False
    for l in txt.split('\n'):
        if l.startswith('listen '):
            listen = l[7:]
        elif l.startswith('total '):
            total = l[6:]
        elif l.startswith('uniq '):
            uniq = l[5:]
        elif l == 'HITS':
            in_hits = True
        elif in_hits and l.strip():
            hits.append(l.strip())
    return running, listen, total, uniq, hits


def draw(d, ctx):
    if _view == 'info':
        return _draw_info(d, ctx)
    ctx.topbar(d, 'HONEYPOT')
    ctx.rr(d, (418, 4, 472, 24), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, 445, 14, '(i) info', ctx.F_TINY, ctx.ACC)

    # DEFENSIVE banner (always on)
    ctx.rr(d, (6, 30, 474, 48), fill=(26, 46, 30), outline=(70, 170, 110), w=1, r=6)
    ctx.ct(d, 240, 39, 'DEFENSIVE - logs probes on YOUR network only (authorized)',
           ctx.F_SM, (170, 235, 190))

    running, listen, total, uniq, hits = _parse(ctx)

    # START / STOP
    ctx.rr(d, (10, 56, 150, 84), fill=(30, 110, 60) if not running else (46, 50, 40),
           outline=ctx.ACC if not running else ctx.LINE, w=1, r=7)
    ctx.ct(d, 80, 70, 'START' if not running else 'running', ctx.F_NM,
           ctx.FG if not running else ctx.DIM)
    ctx.rr(d, (160, 56, 300, 84), fill=(120, 45, 45) if running else (44, 44, 44),
           outline=(210, 90, 90) if running else ctx.LINE, w=1, r=7)
    ctx.ct(d, 230, 70, 'STOP', ctx.F_NM, ctx.FG if running else ctx.DIM)
    c = (30, 200, 121) if running else (150, 160, 170)
    d.ellipse((312, 65, 321, 74), fill=c)
    ctx.lt(d, 326, 70, 'LISTENING' if running else 'stopped', ctx.F_SM, c)

    # ports + counters
    ctx.lt(d, 14, 96, 'ports: ' + (listen or 'ssh:2222  http:80  telnet:23'),
           ctx.F_TINY, (150, 190, 240))  # live 'listen' line from the daemon overrides this
    ctx.rr(d, (10, 108, 150, 142), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=6)
    ctx.ct(d, 80, 120, total, ctx.F_BIG, ctx.FG)
    ctx.ct(d, 80, 135, 'hits', ctx.F_TINY, ctx.DIM)
    ctx.rr(d, (160, 108, 300, 142), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=6)
    ctx.ct(d, 230, 120, uniq, ctx.F_BIG, ctx.FG)
    ctx.ct(d, 230, 135, 'unique IPs', ctx.F_TINY, ctx.DIM)

    # recent probes
    ctx.lt(d, 14, 152, 'recent probes:', ctx.F_SM, (235, 190, 60))
    y = 170
    if not hits:
        ctx.lt(d, 20, y, 'none yet - connect to a port above from another box', ctx.F_TINY, ctx.DIM)
    else:
        for l in hits[:8]:
            ctx.lt(d, 18, y, l[:60], ctx.F_TINY, ctx.FG)
            y += 17
            if y > 304:
                break


def _draw_info(d, ctx):
    ctx.topbar(d, 'HONEYPOT - LEARN')
    ctx.rr(d, (418, 4, 472, 24), outline=ctx.ACC, w=1, r=8)
    ctx.ct(d, 445, 14, 'back', ctx.F_TINY, ctx.ACC)
    rows = [
        ('what', (235, 190, 60)),
        ('Fake SSH/HTTP/Telnet services that NEVER grant access - they only', ctx.FG),
        ('record who connects and what creds/commands they try.', ctx.FG),
        ('why it works', (235, 190, 60)),
        ('A honeypot has zero legit users, so ANY hit = a scan or intrusion', ctx.FG),
        ('attempt: near-zero false positives. Low-interaction (banner only)', ctx.FG),
        ('means no real shell is ever exposed - safe to run.', ctx.FG),
        ('detect & defend', (70, 200, 140)),
        ('- Feed hits to fail2ban / an IDS to auto-block the scanner.', ctx.FG),
        ('- Run REAL ssh on a non-default port; keys only, no passwords.', ctx.FG),
        ('- Alert on the first hit - internal hosts should never touch it.', ctx.FG),
        ('- Never expose real creds; a honeypot misleads, never authenticates.', ctx.FG),
    ]
    y = 42
    for t, c in rows:
        ctx.lt(d, 14, y, t, ctx.F_SM, c)
        y += 19


def handle_touch(tx, ty, ctx):
    global _view
    if _view == 'info':
        if ty <= 24 and tx >= 418 and ctx.debounce(0.3):
            _view = 'main'
            ctx.mark_dirty()
        return
    if ty <= 24 and tx >= 418 and ctx.debounce(0.3):
        _view = 'info'
        ctx.mark_dirty()
        return
    if 56 <= ty <= 84:
        if tx <= 150 and ctx.debounce(0.5):
            _start(ctx)
            ctx.mark_dirty()
        elif 160 <= tx <= 300 and ctx.debounce(0.5):
            _stop(ctx)
            ctx.mark_dirty()
