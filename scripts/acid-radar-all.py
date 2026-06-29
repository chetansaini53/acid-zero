#!/usr/bin/env python3
# Acid Zero / Radar - ALL combined watch (passive, alert-mode).
# WiFi deauth = continuous tcpdump (reliable). BLE (spam / Flipper / device count) = periodic
# FRESH btmon+scan BURSTS parsed from a file - the Pi's onboard BT discovery is bursty under
# WiFi load, so we re-capture each cycle (same proven pattern as the BLE Scan app).
# Read-only - never transmits. Educational / own-lab.
import subprocess, time, os, re, threading, collections, glob

OUT = '/tmp/acid_radar_all'; STOP = '/tmp/acid_radar_all_stop'; BT = '/tmp/acid_radar_all_bt'
W_WIN = 5.0; W_TH = 15      # deauth flood (rolling)
B_TH = 12                   # ble spam: distinct spam MACs in a burst
F_HOLD = 20.0               # flipper presence hold across bursts
BURST = 6                   # BLE capture burst seconds

DA_FREQ = re.compile(r'\b(\d{4})\s*MHz')
B_ADDR = re.compile(r'\bAddress:\s+([0-9A-F:]{17})')
B_COMP = re.compile(r'Company:\s+(.+?)\s*\(\d+\)')
B_TYPE = re.compile(r'\bType:\s+\w+\s*\((\d+)\)')
B_NAME = re.compile(r'Name \([^)]*\):\s+(.+)')
FLIP_UUID = '8fe5b3d5'

def find_mon():
    for n in ['wlan0mon'] + [os.path.basename(w) for w in sorted(glob.glob('/sys/class/net/wlan*'))]:
        try:
            if 'type monitor' in subprocess.run(['iw', 'dev', n, 'info'], capture_output=True, timeout=3).stdout.decode('utf-8', 'replace'):
                return n
        except Exception:
            pass
    return 'wlan0mon'

def is_spam(c):
    comp = c.get('company', '')
    if c.get('fp'): return True
    if comp.startswith('Apple') and c.get('atype') in (7, 15): return True
    return comp.startswith('Samsung') or comp.startswith('Microsoft')

def is_flip(c):
    return 'flipper' in (c.get('name', '') or '').lower() or c.get('uuidflip', False)

def parse_burst():
    spam = set(); flip = {}; total = set(); cur = None
    def commit(c):
        if not c or not c.get('mac'): return
        total.add(c['mac'])
        if is_spam(c): spam.add(c['mac'])
        if is_flip(c): flip[c['mac']] = (c.get('name', 'Flipper'), c.get('rssi', '-99'))
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
        mn = B_NAME.search(L)
        if mn: cur['name'] = mn.group(1).strip(); continue
        if 'fe2c' in L.lower(): cur['fp'] = True
        if FLIP_UUID in L.lower(): cur['uuidflip'] = True
    commit(cur)
    return spam, flip, total

def write(dcnt, dbands, spam, flips_hold, total, mon, dur):
    out = ['deauth_count=%d deauth_alert=%d deauth_band=%s' % (dcnt, 1 if dcnt >= W_TH else 0, '+'.join(sorted(dbands)) or '-'),
           'ble_macs=%d ble_alert=%d' % (len(spam), 1 if len(spam) >= B_TH else 0),
           'flipper_count=%d flipper_alert=%d' % (len(flips_hold), 1 if flips_hold else 0),
           'ble_total=%d iface=%s dur=%d' % (len(total), mon, dur)]
    try: open(OUT, 'w').write('\n'.join(out))
    except Exception: pass

def main():
    for f in (STOP, OUT):
        try: os.remove(f)
        except Exception: pass
    mon = find_mon()
    write(0, set(), set(), {}, set(), mon, 0)
    try:
        tdp = subprocess.Popen(['tcpdump', '-i', mon, '-nn', '-e', '-l', 'subtype deauth or subtype disassoc'],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1, encoding='utf-8', errors='replace')
    except Exception:
        tdp = None
    dl = []
    if tdp:
        threading.Thread(target=lambda: [dl.append(L) for L in tdp.stdout], daemon=True).start()
    dev = collections.deque(); dbands = set(); flips_hold = {}; t0 = time.time()
    def drain_deauth():
        while dl:
            L = dl.pop(0); dev.append(time.time())
            fm = DA_FREQ.search(L)
            if fm: dbands.add('2.4' if int(fm.group(1)) < 3000 else '5')
    while not os.path.exists(STOP):
        try: os.remove(BT)
        except Exception: pass
        bm = subprocess.Popen(['btmon'], stdout=open(BT, 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        subprocess.run(['bash', '-c', 'sleep %d | timeout %d btmgmt find -l >/dev/null 2>&1' % (BURST + 2, BURST)])
        try: bm.terminate()
        except Exception: pass
        time.sleep(0.3)
        spam, flip, total = parse_burst()
        drain_deauth()
        now = time.time()
        while dev and now - dev[0] > W_WIN:
            dev.popleft()
        for mac, (nm, rs) in flip.items():
            flips_hold[mac] = (nm, rs, now)
        for mac in [k for k, v in flips_hold.items() if now - v[2] > F_HOLD]:
            del flips_hold[mac]
        write(len(dev), dbands, spam, flips_hold, total, mon, int(now - t0))
    try:
        if tdp: tdp.terminate()
    except Exception: pass
    try: os.remove(STOP)
    except Exception: pass

if __name__ == '__main__':
    main()
