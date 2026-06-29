#!/usr/bin/env python3
# Acid Zero / Radar - Flipper Detector (ALERT MODE, passive, burst capture).
# Periodic FRESH btmon+scan bursts (parsed from a file). Flags a BLE device as a Flipper if its
# Local Name contains "flipper" OR it advertises the Flipper serial GATT service (8fe5b3d5-...).
# Read-only - never transmits. Educational / own-lab.
# Out -> /tmp/acid_radar_flipper   ; stop -> touch /tmp/acid_radar_flipper_stop
import subprocess, time, os, re

OUT = '/tmp/acid_radar_flipper'; STOP = '/tmp/acid_radar_flipper_stop'; BT = '/tmp/acid_flipper_bt'
HOLD = 20.0; BURST = 6
FLIP_UUID = '8fe5b3d5'
B_ADDR = re.compile(r'\bAddress:\s+([0-9A-F:]{17})')
B_NAME = re.compile(r'Name \([^)]*\):\s+(.+)')
B_RSSI = re.compile(r'RSSI:\s+(-?\d+)')

def is_flip(c):
    return 'flipper' in (c.get('name', '') or '').lower() or c.get('uuidflip', False)

def parse_burst():
    found = {}; cur = None   # mac -> (name, rssi)
    def commit(c):
        if c and c.get('mac') and is_flip(c):
            found[c['mac']] = (c.get('name', 'Flipper'), c.get('rssi', '-99'))
    try: lines = open(BT, errors='replace').read().split('\n')
    except Exception: lines = []
    for L in lines:
        m = B_ADDR.search(L)
        if m:
            commit(cur); cur = {'mac': m.group(1)}; continue
        if cur is None: continue
        mn = B_NAME.search(L)
        if mn: cur['name'] = mn.group(1).strip(); continue
        mr = B_RSSI.search(L)
        if mr: cur['rssi'] = mr.group(1); continue
        if FLIP_UUID in L.lower(): cur['uuidflip'] = True
    commit(cur)
    return found

def write(flips_hold, dur):
    out = ['alert=%d count=%d dur=%d' % (1 if flips_hold else 0, len(flips_hold), dur)]
    for mac, (name, rssi, ts) in sorted(flips_hold.items(), key=lambda x: x[1][1], reverse=True):
        out.append('F|%s|%s|%s' % (name or 'Flipper', mac, rssi))
    try: open(OUT, 'w').write('\n'.join(out))
    except Exception: pass

def main():
    for f in (STOP, OUT):
        try: os.remove(f)
        except Exception: pass
    write({}, 0)
    t0 = time.time(); flips_hold = {}
    while not os.path.exists(STOP):
        try: os.remove(BT)
        except Exception: pass
        bm = subprocess.Popen(['btmon'], stdout=open(BT, 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        subprocess.run(['bash', '-c', 'sleep %d | timeout %d btmgmt find -l >/dev/null 2>&1' % (BURST + 2, BURST)])
        try: bm.terminate()
        except Exception: pass
        time.sleep(0.3)
        found = parse_burst()
        now = time.time()
        for mac, (nm, rs) in found.items():
            flips_hold[mac] = (nm, rs, now)
        for mac in [k for k, v in flips_hold.items() if now - v[2] > HOLD]:
            del flips_hold[mac]
        write(flips_hold, int(now - t0))
    try: os.remove(STOP)
    except Exception: pass

if __name__ == '__main__':
    main()
