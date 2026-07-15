# Acid Zero plugin - "Wardrive": scanning + GPS-tagged logging only (no
# crack/deauth/connect). Polls the SAME bettercap session WiFi Hunter /
# pwnagotchi already run (no second scanner spawned, no adapter to assign -
# whichever adapter is already in monitor mode feeds this automatically) and
# an optional GPS (acid_gps.py), writing WigleWifi-CSV rows importable into
# WiGLE/Kismet-family tools. Educational / own-lab use only - see the (i) button.
#
# GPS is OPTIONAL and hot-pluggable: the AP scan (bettercap reuse) runs and is
# visible on screen with or without a GPS fix, so the scanning path is
# testable on its own. Rows are only WRITTEN to the CSV once a fix exists;
# until then the live console still shows every AP discovered (tagged SCAN
# instead of LOG) so "is anything happening" is never a mystery.
import os, sys, csv, io, glob, json, time, base64, threading, urllib.request
for _p in ('/usr/local/bin', '/usr/local/lib/acid-apps', '/home/ella3'):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    from acid_gps import Gps
except Exception:
    Gps = None

META = {'name': 'Wardrive', 'icon': 'pin', 'color': (30, 200, 121)}

LOG_DIR = '/home/ella3/acid_wardrive'
BC_URL = 'http://127.0.0.1:8081/api/session'
BC_AUTH = 'Basic ' + base64.b64encode(b'pwnagotchi:pwnagotchi').decode()
POLL_S = 5.0
MAX_LOG_LINES = 300
# WigleWifi-1.6 (verified against the live spec at https://api.wigle.net/csvFormat.html)
WIGLE_HDR1 = 'WigleWifi-1.6,appRelease=1.0,model=AcidZero,release=1,device=pi3b,display=tft,board=bcm2837,brand=AcidZero,star=Sol,body=3,subBody=0'
WIGLE_HDR2 = ['MAC', 'SSID', 'AuthMode', 'FirstSeen', 'Channel', 'Frequency', 'RSSI',
              'CurrentLatitude', 'CurrentLongitude', 'AltitudeMeters', 'AccuracyMeters',
              'RCOIs', 'MfgrId', 'Type']
# console palette - dark hacker-console look, independent of the light/dark UI theme
_BG = (6, 12, 9)
_GREEN = (60, 230, 130)
_GREEN_DIM = (30, 110, 70)
_AMBER = (225, 175, 60)

_view = 'main'            # 'main' | 'saved'
_gps = None
_gps_lock = threading.Lock()
_logging = False
_status = 'idle - tap START to arm scanning'
_log_path = None
_rows = 0
_seen = set()
_log_lines = []           # console feed: newest appended at the end
_last_aps = 0
_iface = ''                # which wlanN/monitor-vif bettercap is actually using
_saved = []                 # [(path, label, row_count), ...] for the SAVED view
_started_t = 0.0
_thread = None
_lock = threading.Lock()


def _ensure_gps():
    """Best-effort GPS connect. Returns False if absent/not wired yet - the
    caller treats that as 'scan-only, no location tag' rather than an error."""
    global _gps
    if Gps is None:
        return False
    with _gps_lock:               # guards the check-then-construct against a racing thread
        if _gps is not None and _gps.connected:
            return True
        try:
            _gps = Gps(); _gps.start(); return True
        except Exception:
            _gps = None; return False


def _bc_scan():
    """One bettercap request -> (interface_name, ap_list). Reuses the existing
    session (no new scan spawned, no adapter assigned - reads whichever radio
    bettercap/pwnagotchi already has in monitor mode), and reports which
    interface that is so the UI can show it."""
    try:
        req = urllib.request.Request(BC_URL)
        req.add_header('Authorization', BC_AUTH)
        d = json.loads(urllib.request.urlopen(req, timeout=3).read())
        iface = (d.get('interface') or {}).get('hostname') or ''
        out = []
        for a in d.get('wifi', {}).get('aps', []):
            out.append({
                'mac': a.get('mac', ''), 'ssid': a.get('hostname') or '',
                'enc': a.get('encryption') or 'OPEN', 'channel': a.get('channel') or 0,
                'rssi': a.get('rssi') if a.get('rssi') is not None else -99,
            })
        return iface, out
    except Exception:
        return '', []


def _chan_to_freq(ch):
    """802.11 channel -> center frequency (MHz), 2.4GHz + 5GHz bands."""
    if ch == 14:
        return 2484                      # Japan-only, doesn't fit the linear formula
    if 1 <= ch <= 13:
        return 2407 + 5 * ch
    if 36 <= ch <= 165:
        return 5000 + 5 * ch
    return ''


def _csv_line(fields):
    """Build one properly-escaped CSV line (handles SSIDs containing commas/quotes)."""
    buf = io.StringIO()
    csv.writer(buf, lineterminator='\n').writerow(fields)
    return buf.getvalue()


def _wigle_row(ap, fix, first_seen):
    freq = _chan_to_freq(ap['channel'])
    return _csv_line([
        ap['mac'], ap['ssid'], ap['enc'], first_seen, ap['channel'], freq,
        ap['rssi'], '%.6f' % fix['lat'], '%.6f' % fix['lon'],
        ('%.1f' % fix['alt_m']) if fix.get('alt_m') is not None else '',
        '', '', '', 'WIFI'])   # AccuracyMeters, RCOIs, MfgrId (blank for basic WiFi scan), Type


def _push_log(ap, tag):
    """Append one console line for a newly-discovered AP. tag is 'LOG'
    (written to the CSV, GPS fix present) or 'SCAN' (seen but not saved).
    No fixed-width padding - kept compact (~67 chars worst case) so it
    reliably fits the console width regardless of exact font metrics."""
    ssid = (ap['ssid'] or '<hidden>')[:14]
    line = '%s %s %s ch%d %ddBm %s [%s]' % (
        time.strftime('%H:%M:%S'), ap['mac'], ssid, ap['channel'], ap['rssi'],
        (ap['enc'] or '?')[:5], tag)
    _log_lines.append(line)
    if len(_log_lines) > MAX_LOG_LINES:
        del _log_lines[:len(_log_lines) - MAX_LOG_LINES]


def _log_loop(ctx):
    global _status, _rows, _last_aps, _iface
    while _logging:
        try:
            have_gps = _ensure_gps() and _gps.has_fix()
            iface, aps = _bc_scan()
            _iface = iface or _iface   # keep the last-known name if a poll briefly fails
            _last_aps = len(aps)
            new_aps = [a for a in aps if a['mac'] and a['mac'] not in _seen]
            for a in new_aps:
                _seen.add(a['mac'])
                _push_log(a, 'LOG' if have_gps else 'SCAN')
            if have_gps and aps:
                fix = _gps.fix()
                now = time.strftime('%Y-%m-%d %H:%M:%S')
                with _lock:
                    with open(_log_path, 'a') as f:
                        for a in aps:
                            if not a['mac']:
                                continue
                            f.write(_wigle_row(a, fix, now))
                            _rows += 1
                _status = '%d APs @ %.5f,%.5f  (%d unique, %d rows)' % (
                    len(aps), fix['lat'], fix['lon'], len(_seen), _rows)
            elif not have_gps:
                _status = ('%d APs visible - no GPS fix, scan-only (not saved yet)' % _last_aps
                            if Gps is not None else
                            '%d APs visible - GPS module not found, scan-only' % _last_aps)
            else:
                _status = 'GPS fix ok, no APs seen this poll'
            ctx.mark_dirty()
        except Exception as e:
            _status = 'log err: %s' % str(e)[:28]
        time.sleep(POLL_S)


def _start_logging(ctx):
    global _logging, _log_path, _rows, _seen, _log_lines, _started_t, _thread
    if _logging:
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    _log_path = os.path.join(LOG_DIR, 'wardrive_%s.csv' % time.strftime('%Y%m%d_%H%M%S'))
    with open(_log_path, 'w') as f:
        f.write(WIGLE_HDR1 + '\n' + _csv_line(WIGLE_HDR2))
    _rows = 0; _seen = set(); _log_lines = []; _started_t = time.time(); _logging = True
    _thread = threading.Thread(target=_log_loop, args=(ctx,), daemon=True)
    _thread.start()
    ctx.mark_dirty()


def _stop_logging(ctx):
    global _logging, _status
    _logging = False
    _status = 'stopped - %d rows saved (%s)' % (_rows, os.path.basename(_log_path or ''))
    ctx.mark_dirty()


# ---------- saved logs browser ----------
def _refresh_saved():
    global _saved
    out = []
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        for p in sorted(glob.glob(os.path.join(LOG_DIR, 'wardrive_*.csv')), reverse=True):
            try:
                with open(p) as f:
                    n = max(0, sum(1 for _ in f) - 2)   # minus the 2 WigleWifi header lines
                ts = os.path.basename(p)[len('wardrive_'):-len('.csv')]
                try:
                    label = time.strftime('%Y-%m-%d %H:%M:%S', time.strptime(ts, '%Y%m%d_%H%M%S'))
                except Exception:
                    label = ts
                out.append((p, label, n))
            except Exception:
                pass
    except Exception:
        pass
    _saved = out


def _delete_saved(path):
    try:
        os.remove(path)
    except Exception:
        pass
    _refresh_saved()


def on_enter(ctx):
    global _view
    _view = 'main'
    threading.Thread(target=lambda: (_ensure_gps(), ctx.mark_dirty()), daemon=True).start()
    ctx.mark_dirty()


def on_exit(ctx):
    """Leaving the screen does NOT stop an active logging session - wardriving
    keeps running in the background so the user can navigate elsewhere while
    driving. Only releases the GPS handle if logging was never started."""
    global _gps
    if not _logging and _gps is not None:
        try: _gps.close()
        except Exception: pass
        _gps = None


def _btn(ctx, d, box, label, fill, fg, font=None):
    ctx.rr(d, box, fill=fill, r=8)
    ctx.ct(d, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2, label, font or ctx.F_NM, fg)


# ---------- view: MAIN (console) ----------
def _draw_main(d, ctx):
    ctx.topbar(d, 'WARDRIVE')   # (i) Learn button appears automatically (LEARN['Wardrive'])
    _btn(ctx, d, (386, 3, 472, 25), 'SAVED', (45, 52, 68), ctx.ACC, ctx.F_SM)

    # adapter-in-use, top-center
    ctx.ct(d, 240, 39, ('adapter: %s' % _iface) if _iface else 'adapter: (not scanning)',
           ctx.F_TINY, ctx.ACC if _iface else ctx.DIM)

    # console log area - dark hacker-console look, monospace green text
    CONSOLE = (8, 48, 472, 244)
    d.rectangle(CONSOLE, fill=_BG)
    d.rectangle((CONSOLE[0], CONSOLE[1], CONSOLE[2], CONSOLE[1] + 1), fill=_GREEN_DIM)
    if not _log_lines:
        ctx.ct(d, 240, 146, 'no APs discovered yet' if _logging else 'tap START to begin scanning',
               ctx.F_SM, _GREEN_DIM)
    else:
        line_h = 13
        visible = (CONSOLE[3] - CONSOLE[1] - 6) // line_h
        for i, ln in enumerate(_log_lines[-visible:]):
            ctx.lt(d, CONSOLE[0] + 4, CONSOLE[1] + 8 + i * line_h, ln[:70], ctx.F_TINY, _GREEN)

    # bottom bar: status (left) ... START/STOP button (bottom-right)
    have = bool(_gps and _gps.has_fix())
    gps_txt = ('GPS: LOCKED' if have else 'GPS: NO FIX' if _gps else 'GPS: OFF')
    gps_col = _GREEN if have else _AMBER if _gps else ctx.DIM
    wd_txt = 'WARDRIVE: ACTIVE' if _logging else 'WARDRIVE: INACTIVE'
    wd_col = (225, 70, 70) if _logging else ctx.DIM
    ctx.rr(d, (8, 252, 472, 300), fill=ctx.PANEL, outline=ctx.LINE, w=1, r=8)
    ctx.lt(d, 16, 266, gps_txt, ctx.F_SM, gps_col)
    ctx.lt(d, 16, 286, wd_txt + ('  (%d APs)' % _last_aps if _logging else ''), ctx.F_SM, wd_col)
    btn = (340, 258, 466, 294)
    ctx.rr(d, btn, fill=(220, 60, 60) if _logging else (23, 150, 86), r=8)
    ctx.ct(d, (btn[0] + btn[2]) // 2, (btn[1] + btn[3]) // 2,
           'STOP' if _logging else 'START', ctx.F_NM,
           (255, 235, 235) if _logging else (240, 255, 246))
    ctx.ct(d, 240, 310, _status[:56], ctx.F_TINY, ctx.DIM)


def _touch_main(tx, ty, ctx):
    global _view
    if ty <= 25 and tx >= 386 and ctx.debounce(0.3):
        _refresh_saved(); _view = 'saved'; ctx.mark_dirty(); return
    if 258 <= ty <= 294 and tx >= 340 and ctx.debounce(0.5):
        _stop_logging(ctx) if _logging else _start_logging(ctx)


# ---------- view: SAVED (auto-saved, timestamped wardrive_*.csv) ----------
def _draw_saved(d, ctx):
    ctx.topbar(d, 'SAVED LOGS')
    _btn(ctx, d, (386, 3, 472, 25), 'MAIN', (45, 52, 68), ctx.ACC, ctx.F_SM)
    if not _saved:
        ctx.ct(d, 240, 140, 'no saved wardrive logs yet', ctx.F_NM, ctx.DIM)
        ctx.ct(d, 240, 164, 'each START creates a new timestamped file', ctx.F_SM, ctx.DIM)
        return
    y = 34
    for path, label, n in _saved[:8]:
        ctx.rr(d, (10, y, 420, y + 28), fill=ctx.TILE, outline=ctx.LINE, w=1, r=6)
        ctx.lt(d, 16, y + 14, label, ctx.F_SM, ctx.FG)
        ctx.lt(d, 240, y + 14, '%d rows' % n, ctx.F_TINY, ctx.DIM)
        ctx.rr(d, (426, y, 470, y + 28), fill=(120, 40, 48), r=6)
        ctx.ct(d, 448, y + 14, 'X', ctx.F_SM, (255, 220, 220))
        y += 32
    ctx.lt(d, 14, ctx.H - 9, 'auto-saved on START, timestamped   |   X = delete', ctx.F_TINY, ctx.DIM)


def _touch_saved(tx, ty, ctx):
    global _view
    if ty <= 25 and tx >= 386 and ctx.debounce(0.3):
        _view = 'main'; ctx.mark_dirty(); return
    if 34 <= ty <= 290:
        idx = (ty - 34) // 32
        if 0 <= idx < len(_saved[:8]) and tx >= 426 and ctx.debounce(0.4):
            _delete_saved(_saved[idx][0]); ctx.mark_dirty()


def draw(d, ctx):
    {'saved': _draw_saved}.get(_view, _draw_main)(d, ctx)


def handle_touch(tx, ty, ctx):
    {'saved': _touch_saved}.get(_view, _touch_main)(tx, ty, ctx)
