#!/usr/bin/env python3
# ACID native app - Wardrive CSV reader.  Educational / own-lab only.
# A second native-plugin sample (alongside hello-native): a standalone program
# that OWNS the ILI9486 framebuffer + ADS7846 touch, reads the WigleWifi CSV logs
# the Wardrive app writes to /home/ella3/acid_wardrive/, and shows them in a
# scrollable TABLE - fixed column header on top + UP/DOWN pagination, the same
# look as the IR / Sub-GHz plugins. Tap EXIT to return to the launcher.
#
# Native-plugin contract (see apps/hello-native/): render fb, decode touch
# (evdev + the launcher's 4-point calibration in /home/pi/acid_cal), exit on
# the EXIT tap - the launcher is blocked on us and redraws home when we return.
import os, glob, struct, select, time, csv
from PIL import Image, ImageDraw, ImageFont
try:
    import numpy as np
except Exception:
    np = None

W, H, BPP = 480, 320, 2
CSV_DIR = '/home/ella3/acid_wardrive'
CAL_FILE = '/home/pi/acid_cal'

# ---- palette (dark, theme-independent) ----
BG = (14, 18, 26); PANEL = (24, 30, 42); TILE = (26, 32, 44); TILE2 = (20, 26, 36)
LINE = (44, 54, 74); FG = (226, 233, 243); DIM = (120, 134, 156)
ACC = (60, 200, 140); HDR = (150, 190, 240)

# ---- layout regions (draw AND touch use these - keep in sync) ----
TB_H = 30
EXIT = (412, 5, 476, 26)
BACK = (6, 5, 72, 26)
COLHDR_Y, COLHDR_H = 32, 22
ROW_Y0, ROW_H, REC_PER = 56, 23, 10        # records rows: 56 .. 286
FROW_Y0, FROW_H, FILE_PER = 36, 30, 8      # file rows:    36 .. 276
UP = (6, 290, 152, 316)
DOWN = (328, 290, 474, 316)

# WigleWifi columns shown (label, csv index, x, max chars)
COLS = [('SSID', 1, 10, 22), ('BSSID', 0, 172, 18),
        ('CH', 4, 326, 4), ('RSSI', 6, 362, 5), ('AUTH', 2, 408, 9)]


def font(sz, bold=True):
    order = ['DejaVuSans-Bold.ttf', 'DejaVuSans.ttf'] if bold else ['DejaVuSans.ttf', 'DejaVuSans-Bold.ttf']
    for nm in order:
        try:
            return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/' + nm, sz)
        except Exception:
            pass
    return ImageFont.load_default()


F_TITLE = font(17); F_HDR = font(13); F_ROW = font(12, bold=False); F_SM = font(11)


def ct(d, x, y, t, f, c):
    d.text((x, y), str(t), font=f, fill=c, anchor='mm')


def lt(d, x, y, t, f, c):
    d.text((x, y), str(t), font=f, fill=c, anchor='lm')


def in_box(x, y, b):
    return b[0] <= x <= b[2] and b[1] <= y <= b[3]


def paged(count, page, per):
    total = max(1, (count + per - 1) // per)
    page = min(max(page, 0), total - 1)
    return page, total, page * per


def short_auth(a):
    u = (a or '').upper()
    if 'WPA3' in u: return 'WPA3'
    if 'WPA2' in u: return 'WPA2'
    if 'WPA' in u: return 'WPA'
    if 'WEP' in u: return 'WEP'
    if u and 'WPA' not in u and 'WEP' not in u and ('ESS' in u or 'OPEN' in u): return 'OPEN'
    return (a or '-')[:9]


# ---- framebuffer ----
def find_fb():
    for fb in sorted(glob.glob('/sys/class/graphics/fb*')):
        try:
            nm = open(os.path.join(fb, 'name')).read().strip().lower()
        except Exception:
            continue
        if 'ili9486' in nm or 'fb_ili9486' in nm or 'piscreen' in nm:
            return '/dev/' + os.path.basename(fb)
    return '/dev/fb1'


def rgb565(img):
    if np is not None:
        a = np.asarray(img, dtype=np.uint16)
        v = ((a[:, :, 0] & 0xF8) << 8) | ((a[:, :, 1] & 0xFC) << 3) | (a[:, :, 2] >> 3)
        return v.astype('<u2').tobytes()
    px = img.load(); out = bytearray(W * H * BPP); i = 0
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y][:3]
            val = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out[i] = val & 0xFF; out[i + 1] = (val >> 8) & 0xFF; i += 2
    return bytes(out)


# ---- touch (evdev + the launcher's affine calibration) ----
CAL = [480.0 / 2816.0, 0.0, -663 * 480.0 / 2816.0, 0.0, -320.0 / 2512.0, 2948 * 320.0 / 2512.0]


def load_cal():
    global CAL
    try:
        v = [float(x) for x in open(CAL_FILE).read().split()]
        if len(v) == 6:
            CAL = v
    except Exception:
        pass


def find_touch():
    for e in sorted(glob.glob('/sys/class/input/event*')):
        try:
            n = open(e + '/device/name').read().strip().lower()
        except Exception:
            continue
        if 'ads7846' in n or 'touch' in n or 'stmpe' in n:
            return '/dev/input/' + os.path.basename(e)
    return None


def map_touch(rx, ry):
    sx = CAL[0] * rx + CAL[1] * ry + CAL[2]
    sy = CAL[3] * rx + CAL[4] * ry + CAL[5]
    return max(0, min(W - 1, int(round(sx)))), max(0, min(H - 1, int(round(sy))))


# ---- CSV ----
def list_csvs():
    out = []
    try:
        for p in sorted(glob.glob(os.path.join(CSV_DIR, '*.csv')), reverse=True):
            try:
                n = sum(1 for _ in open(p, 'rb')) - 2      # minus the 2 WigleWifi header lines
            except Exception:
                n = 0
            out.append((p, os.path.basename(p), max(0, n)))
    except Exception:
        pass
    return out


def load_csv(path):
    try:
        with open(path, newline='', encoding='utf-8', errors='replace') as f:
            rows = list(csv.reader(f))
    except Exception:
        return [], []
    hi = 0
    for i, r in enumerate(rows[:4]):
        if 'MAC' in r and 'SSID' in r:
            hi = i
            break
    header = rows[hi] if rows else []
    data = [r for r in rows[hi + 1:] if any(c.strip() for c in r)]
    return header, data


# ---- state ----
STATE = {'view': 'files', 'files': [], 'fpage': 0,
         'cur_name': '', 'header': [], 'rows': [], 'rpage': 0}


def open_file(path, name):
    header, rows = load_csv(path)
    STATE['cur_name'] = name
    STATE['header'] = header
    STATE['rows'] = rows
    STATE['rpage'] = 0
    STATE['view'] = 'records'


# ---- draw ----
def _tri(d, cx, cy, up, col):
    d.polygon([(cx - 7, cy + (4 if up else -4)), (cx + 7, cy + (4 if up else -4)),
               (cx, cy + (-5 if up else 5))], fill=col)


def _bottom_bar(d, page, total, mid):
    d.rectangle((0, 288, W, H), fill=PANEL)
    up_on, dn_on = page > 0, page < total - 1
    d.rounded_rectangle(UP, radius=6, fill=(34, 58, 46) if up_on else (28, 32, 40))
    _tri(d, 40, 303, True, ACC if up_on else DIM); ct(d, 96, 303, 'UP', F_HDR, ACC if up_on else DIM)
    ct(d, W // 2, 303, mid, F_SM, FG)
    d.rounded_rectangle(DOWN, radius=6, fill=(34, 58, 46) if dn_on else (28, 32, 40))
    ct(d, 384, 303, 'DOWN', F_HDR, ACC if dn_on else DIM); _tri(d, 440, 303, False, ACC if dn_on else DIM)


def _draw_files(d):
    files = STATE['files']
    d.rectangle((0, 0, W, TB_H), fill=PANEL)
    ct(d, W // 2, 15, 'WARDRIVE  CSV  LOGS', F_HDR, FG)
    d.rounded_rectangle(EXIT, radius=5, fill=(120, 50, 50)); ct(d, 444, 15, 'EXIT', F_SM, (255, 225, 225))
    if not files:
        ct(d, W // 2, 150, 'no wardrive logs yet', F_TITLE, DIM)
        ct(d, W // 2, 178, 'run the Wardrive app first, then come back', F_SM, DIM)
        ct(d, W // 2, 198, CSV_DIR, F_SM, HDR)
        _bottom_bar(d, 0, 1, 'no files')
        return
    pg, tot, start = paged(len(files), STATE['fpage'], FILE_PER)
    y = FROW_Y0
    for path, nm, cnt in files[start:start + FILE_PER]:
        d.rounded_rectangle((8, y, W - 8, y + FROW_H - 4), radius=6, fill=TILE, outline=LINE)
        lt(d, 16, y + (FROW_H - 4) // 2, nm[:30], F_ROW, FG)
        lt(d, 396, y + (FROW_H - 4) // 2, '%d APs' % cnt, F_SM, ACC)
        y += FROW_H
    _bottom_bar(d, pg, tot, 'tap a log to open  ·  %d files' % len(files))


def _draw_records(d):
    rows = STATE['rows']
    d.rectangle((0, 0, W, TB_H), fill=PANEL)
    d.rounded_rectangle(BACK, radius=5, fill=(40, 52, 72)); ct(d, 39, 15, 'BACK', F_SM, ACC)
    ct(d, W // 2, 15, STATE['cur_name'][:32], F_HDR, FG)
    d.rounded_rectangle(EXIT, radius=5, fill=(120, 50, 50)); ct(d, 444, 15, 'EXIT', F_SM, (255, 225, 225))
    # fixed column header
    d.rectangle((0, COLHDR_Y, W, COLHDR_Y + COLHDR_H), fill=(30, 40, 58))
    for lbl, idx, x, mc in COLS:
        lt(d, x, COLHDR_Y + COLHDR_H // 2, lbl, F_HDR, HDR)
    total = len(rows)
    pg, tot, start = paged(total, STATE['rpage'], REC_PER)
    if total == 0:
        ct(d, W // 2, 160, 'no records in this file', F_TITLE, DIM)
        _bottom_bar(d, 0, 1, 'no rows')
        return
    y = ROW_Y0
    for k, r in enumerate(rows[start:start + REC_PER]):
        d.rectangle((0, y, W, y + ROW_H), fill=TILE if k % 2 == 0 else TILE2)
        for lbl, idx, x, mc in COLS:
            val = r[idx] if idx < len(r) else ''
            if lbl == 'AUTH':
                val = short_auth(val)
            lt(d, x, y + ROW_H // 2, str(val)[:mc], F_ROW, FG)
        y += ROW_H
    _bottom_bar(d, pg, tot, 'rows %d-%d of %d  ·  pg %d/%d'
                % (start + 1, min(start + REC_PER, total), total, pg + 1, tot))


def render(fb):
    img = Image.new('RGB', (W, H), BG)
    (_draw_files if STATE['view'] == 'files' else _draw_records)(ImageDraw.Draw(img))
    try:
        with open(fb, 'wb') as f:
            f.write(rgb565(img))
    except Exception:
        pass


# ---- touch handling ----
def handle_tap(sx, sy):
    """Returns True to EXIT the app, else False (re-render)."""
    if in_box(sx, sy, EXIT):
        return True
    if STATE['view'] == 'files':
        files = STATE['files']
        if files and in_box(sx, sy, UP):
            STATE['fpage'] = max(0, STATE['fpage'] - 1)
        elif files and in_box(sx, sy, DOWN):
            _, tot, _ = paged(len(files), STATE['fpage'], FILE_PER)
            STATE['fpage'] = min(tot - 1, STATE['fpage'] + 1)
        elif files and FROW_Y0 <= sy < FROW_Y0 + FILE_PER * FROW_H:
            _, _, start = paged(len(files), STATE['fpage'], FILE_PER)
            idx = start + (sy - FROW_Y0) // FROW_H
            if start <= idx < min(start + FILE_PER, len(files)):
                open_file(files[idx][0], files[idx][1])
        return False
    # records view
    if in_box(sx, sy, BACK):
        STATE['view'] = 'files'
    elif in_box(sx, sy, UP):
        STATE['rpage'] = max(0, STATE['rpage'] - 1)
    elif in_box(sx, sy, DOWN):
        _, tot, _ = paged(len(STATE['rows']), STATE['rpage'], REC_PER)
        STATE['rpage'] = min(tot - 1, STATE['rpage'] + 1)
    return False


def main():
    fb = find_fb()
    load_cal()
    STATE['files'] = list_csvs()
    render(fb)
    tdev = find_touch()
    try:
        fd = os.open(tdev, os.O_RDONLY | os.O_NONBLOCK) if tdev else -1
    except Exception:
        fd = -1
    if fd < 0:
        time.sleep(8)          # no touch device -> auto-exit like the template
        return 0
    SZ = struct.calcsize('llHHi')
    rx = ry = -1; down = False; pts = []
    while True:
        r, _, _ = select.select([fd], [], [], 0.5)
        if not r:
            continue
        try:
            data = os.read(fd, SZ * 256)
        except Exception:
            continue
        tap = None
        for off in range(0, len(data) - SZ + 1, SZ):
            _, _, typ, code, val = struct.unpack('llHHi', data[off:off + SZ])
            if typ == 3 and code == 0:
                rx = val
            elif typ == 3 and code == 1:
                ry = val
            elif typ == 0:
                if down and 100 < rx < 4000 and 100 < ry < 4000:
                    pts.append((rx, ry))
            elif typ == 1 and code == 330:
                if val == 1:
                    down = True; pts = []; rx = ry = -1
                elif val == 0:
                    down = False
                    if len(pts) >= 3:
                        ps = pts[1:-1]
                        xs = sorted(p[0] for p in ps); ys = sorted(p[1] for p in ps)
                        tap = map_touch(xs[len(xs) // 2], ys[len(ys) // 2])
        if tap is not None:
            if handle_tap(*tap):
                break
            render(fb)
    try:
        os.close(fd)
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    main()
