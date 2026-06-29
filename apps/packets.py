# Acid Zero plugin - "Live Packets": read-only 802.11 frame recon on the monitor radio.
# on_enter kicks a 5s capture; CAPTURE button re-runs. Shows rate, frame types, top talker
# MACs, and probe-request leaks (devices searching for known SSIDs). Non-destructive.
META = {'name': 'Packets', 'icon': 'net', 'color': (225, 180, 40)}

def _run(ctx):
    ctx.popen(['bash', '/usr/local/bin/acid-packets.sh', '5'])

def on_enter(ctx):
    _run(ctx); ctx.mark_dirty()

def draw(d, ctx):
    ctx.topbar(d, 'LIVE PACKETS')
    cap = ctx.fread('/tmp/acid_packets_status').strip() == 'capturing'
    L = [l for l in ctx.fread('/tmp/acid_packets_stats').split('\n')]
    ctx.rr(d, (10, 34, 150, 62), fill=(30, 120, 210), r=7)
    ctx.ct(d, 80, 48, ('...' if cap else 'CAPTURE'), ctx.F_NM, (240, 248, 255))
    hdr = L[0] if L and L[0] else ''
    ctx.lt(d, 162, 48, ('capturing 5s...' if cap else hdr)[:30], ctx.F_SM, ctx.DIM)
    if len(L) > 1 and L[1]:
        ctx.lt(d, 14, 80, L[1][:54], ctx.F_NM, ctx.ACC)
    y = 104; sec = None
    for l in L[2:]:
        if l == 'TOPMACS':
            ctx.lt(d, 14, y, 'top talkers (SA):', ctx.F_SM, (235, 180, 40)); y += 18; sec = 'm'; continue
        if l == 'PROBES':
            y += 4; ctx.lt(d, 14, y, 'probe-req leaks:', ctx.F_SM, (70, 130, 235)); y += 18; sec = 'p'; continue
        if l.strip() and sec:
            ctx.lt(d, 26, y, l.strip()[:46], ctx.F_SM, (ctx.FG if sec == 'm' else ctx.DIM)); y += 17
        if y > 294: break

def handle_touch(tx, ty, ctx):
    if 34 <= ty <= 62 and tx <= 150 and ctx.debounce(0.5):
        _run(ctx); ctx.mark_dirty()
