#!/usr/bin/env python3
# Acid Zero / Radar - BLE Spam Detector (ALERT MODE, passive, burst capture).
# Periodic FRESH btmon+scan bursts (parsed from a file) - the Pi onboard BT discovery is bursty
# under load, so each cycle re-captures (same proven pattern as the BLE Scan app).
# Detects a flood of pairing-popup spam (Apple ProximityPair/NearbyAction, Google Fast Pair,
# Samsung, Microsoft) from many distinct random MACs. Read-only - never transmits.
# Out -> /tmp/acid_radar_blespam   ; stop -> touch /tmp/acid_radar_blespam_stop
import subprocess, time, os, re, glob, collections

OUT = '/tmp/acid_radar_blespam'; STOP = '/tmp/acid_radar_blespam_stop'; BT = '/tmp/acid_blespam_bt'
B_TH = 12; BURST = 6

B_ADDR = re.compile(r'\bAddress:\s+([0-9A-F:]{17})')
B_COMP = re.compile(r'Company:\s+(.+?)\s*\(\d+\)')
B_TYPE = re.compile(r'\bType:\s+\w+\s*\((\d+)\)')

def vendor(c):
    comp = c.get('company', '')
    if c.get('fp'): return 'FastPair'
    if comp.startswith('Apple') and c.get('atype') in (7, 15): return 'Apple'
    if comp.startswith('Samsung'): return 'Samsung'
    if comp.startswith('Microsoft'): return 'Microsoft'
    return None

def parse_burst():
    recs = []; cur = None
    def commit(c):
        if c and c.get('mac'): recs.append(c)
    try: lines = open(BT, errors='replace').read().split('\n')
    except Exception: lines = []
    for L in lines:
        m = B_ADDR.search(L)
        if m:
            commit(cur); cur = {'mac': m.group(1)}; continue
        if cur is None: continue
        mc = B_COMP.search(L)
        if mc: cur['company'] = mc.group(1).strip(); continue
        if cur.get('company', '').startswith('Apple'):
            mt = B_TYPE.search(L)
            if mt:
                try: cur['atype'] = int(mt.group(1))
                except Exception: pass
                continue
        if 'fe2c' in L.lower(): cur['fp'] = True
    commit(cur)
    return recs

def write(cnt, macs, alert, dur, mx, vend):
    out = ['count=%d macs=%d alert=%d dur=%d max=%d' % (cnt, macs, alert, dur, mx)]
    for v in ('Apple', 'FastPair', 'Samsung', 'Microsoft'):
        if vend.get(v): out.append('V|%s|%d' % (v, vend[v]))
    try: open(OUT, 'w').write('\n'.join(out))
    except Exception: pass

def main():
    for f in (STOP, OUT):
        try: os.remove(f)
        except Exception: pass
    write(0, 0, 0, 0, 0, {})
    t0 = time.time(); mx = 0
    while not os.path.exists(STOP):
        try: os.remove(BT)
        except Exception: pass
        bm = subprocess.Popen(['btmon'], stdout=open(BT, 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        subprocess.run(['bash', '-c', 'sleep %d | timeout %d btmgmt find -l >/dev/null 2>&1' % (BURST + 2, BURST)])
        try: bm.terminate()
        except Exception: pass
        time.sleep(0.3)
        recs = parse_burst()
        seen = collections.defaultdict(set); cnt = 0
        for c in recs:
            v = vendor(c)
            if v:
                cnt += 1; seen[v].add(c['mac'])
        macset = set().union(*seen.values()) if seen else set()
        macs = len(macset); mx = max(mx, macs)
        vend = {v: len(s) for v, s in seen.items()}
        write(cnt, macs, 1 if macs >= B_TH else 0, int(time.time() - t0), mx, vend)
    try: os.remove(STOP)
    except Exception: pass

if __name__ == '__main__':
    main()
