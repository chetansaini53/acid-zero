#!/usr/bin/env python3
# Acid Zero / Radar - Deauth Detector (ALERT MODE, passive).
# Sniffs 802.11 deauth/disassoc frames on the monitor iface (wlan0mon - bettercap hops
# it across 2.4 + 5 GHz) and alerts on a flood. It NEVER transmits. Educational / own-lab.
# Output -> /tmp/acid_radar_deauth   ; stop -> touch /tmp/acid_radar_deauth_stop
import subprocess, time, re, os, glob, collections, threading

OUT = '/tmp/acid_radar_deauth'
STOP = '/tmp/acid_radar_deauth_stop'
WINDOW = 5.0      # rolling window (s)
THRESH = 15       # >= this many deauth/disassoc in WINDOW -> ALERT (normal roaming is 1-2)

MACre = re.compile(r'(SA|DA|BSSID):([0-9a-f:]{17})')
FREQre = re.compile(r'\b(\d{4})\s*MHz')

def find_mon():
    cands = ['wlan0mon'] + [os.path.basename(w) for w in sorted(glob.glob('/sys/class/net/wlan*'))]
    for n in cands:
        try:
            if 'type monitor' in subprocess.run(['iw', 'dev', n, 'info'], capture_output=True, timeout=3).stdout.decode('utf-8', 'replace'):
                return n
        except Exception:
            pass
    return 'wlan0mon'

def write(mon, cnt, rate, alert, bands, mx, dur, bc, tc):
    out = ['count=%d rate=%.1f alert=%d iface=%s band=%s max=%.1f dur=%d' % (
        cnt, rate, alert, mon, ('+'.join(sorted(bands)) or '-'), mx, dur)]
    for mac, n in bc.most_common(4):
        if mac != '?':
            out.append('B|%s|%d' % (mac, n))
    for mac, n in tc.most_common(4):
        if mac != '?':
            out.append('T|%s|%d' % (mac, n))
    try: open(OUT, 'w').write('\n'.join(out))
    except Exception: pass

def main():
    try: os.remove(STOP)
    except Exception: pass
    try: os.remove(OUT)
    except Exception: pass
    mon = find_mon()
    write(mon, 0, 0, 0, set(), 0, 0, collections.Counter(), collections.Counter())
    try:
        p = subprocess.Popen(['tcpdump', '-i', mon, '-nn', '-e', '-l', 'subtype deauth or subtype disassoc'],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1, encoding='utf-8', errors='replace')
    except Exception:
        write(mon, 0, 0, 0, {'ERR'}, 0, 0, collections.Counter(), collections.Counter())
        return
    lines = []
    threading.Thread(target=lambda: [lines.append(L) for L in p.stdout], daemon=True).start()
    ev = collections.deque()   # (ts, bssid, da)
    bands = set(); t0 = time.time(); mx = 0.0
    while not os.path.exists(STOP):
        now = time.time()
        while lines:
            L = lines.pop(0)
            m = dict(MACre.findall(L))
            fm = FREQre.search(L)
            if fm:
                bands.add('2.4' if int(fm.group(1)) < 3000 else '5')
            ev.append((now, m.get('BSSID') or m.get('SA') or '?', m.get('DA') or '?'))
        while ev and now - ev[0][0] > WINDOW:
            ev.popleft()
        cnt = len(ev); rate = cnt / WINDOW; mx = max(mx, rate)
        bc = collections.Counter(e[1] for e in ev)
        tc = collections.Counter(e[2] for e in ev)
        write(mon, cnt, rate, 1 if cnt >= THRESH else 0, bands, mx, int(now - t0), bc, tc)
        time.sleep(1.0)
    try: p.terminate()
    except Exception: pass
    try: os.remove(STOP)
    except Exception: pass

if __name__ == '__main__':
    main()
