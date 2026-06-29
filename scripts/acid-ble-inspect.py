#!/usr/bin/env python3
# Acid Zero - BLE Inspect: connect to ONE BLE peripheral and enumerate its GATT
# (services + characteristics + a few well-known readable values) via bluetoothctl.
# Stdlib only, no extra deps. Output -> /tmp/acid_ble_inspect  (status -> *_status).
# Educational / authorized only: inspect devices you own or are permitted to test.
import subprocess, sys, time, re, threading

MAC = (sys.argv[1] if len(sys.argv) > 1 else '').upper()
OUT = '/tmp/acid_ble_inspect'
STF = '/tmp/acid_ble_inspect_status'

UUIDre = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
UUID16 = re.compile(r'0000([0-9a-fA-F]{4})-0000-1000-8000-00805f9b34fb')

NAMES = {  # subset of SIG-assigned GATT services + characteristics
 '1800': 'Generic Access', '1801': 'Generic Attribute', '180a': 'Device Information',
 '180f': 'Battery', '1805': 'Current Time', '180d': 'Heart Rate', '1809': 'Thermometer',
 '1816': 'Cycling Speed', '1818': 'Cycling Power', '181c': 'User Data', '110a': 'Audio Source',
 '2a00': 'Device Name', '2a01': 'Appearance', '2a04': 'Conn Params', '2a19': 'Battery Level',
 '2a23': 'System ID', '2a24': 'Model Number', '2a25': 'Serial Number', '2a26': 'Firmware Rev',
 '2a27': 'Hardware Rev', '2a28': 'Software Rev', '2a29': 'Manufacturer', '2a50': 'PnP ID',
 '2a37': 'Heart Rate Meas', '2a6e': 'Temperature', '2a6f': 'Humidity', '2a05': 'Service Changed',
}
READ = {'2a00', '2a19', '2a24', '2a25', '2a26', '2a27', '2a28', '2a29', '2a23', '2a01'}

def st(s):
    try: open(STF, 'w').write(s)
    except Exception: pass

class BTCtl:
    def __init__(self):
        self.p = subprocess.Popen(['bluetoothctl'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.buf = []
        threading.Thread(target=self._rd, daemon=True).start()
    def _rd(self):
        try:
            for line in self.p.stdout:
                self.buf.append(line.rstrip('\n'))
        except Exception:
            pass
    def cmd(self, c, wait=1.0):
        try:
            self.p.stdin.write(c + '\n'); self.p.stdin.flush()
        except Exception:
            pass
        time.sleep(wait)
    def tail(self, n=800):
        return '\n'.join(self.buf[-n:])
    def close(self):
        try:
            self.cmd('exit', 0.2); self.p.terminate()
        except Exception:
            pass

def main():
    if not re.match(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$', MAC):
        st('bad mac'); open(OUT, 'w').write('ERR|invalid MAC'); return
    open(OUT, 'w').write(''); st('connecting')
    b = BTCtl()
    b.cmd('scan on', 4.0)        # make sure bluez knows the device
    b.cmd('scan off', 0.5)
    b.buf.clear()
    b.cmd('connect %s' % MAC, 9.0)
    out = b.tail()
    if 'Connection successful' not in out and 'Connected: yes' not in out:
        b.cmd('', 3.0); out = b.tail()     # give slow stacks one more chance
    if 'Connection successful' not in out and 'Connected: yes' not in out:
        st('failed'); open(OUT, 'w').write('ERR|connect failed - device may need pairing or is not connectable')
        b.cmd('disconnect %s' % MAC, 0.5); b.close(); return
    st('enumerating')
    b.buf.clear()
    b.cmd('menu gatt', 0.5)
    b.cmd('list-attributes %s' % MAC, 3.0)
    lines = b.buf[-1500:]
    records = []; cur = None
    for ln in lines:
        s = ln.strip(); low = s.lower()
        if 'service (handle' in low or 'primary service' in low or 'secondary service' in low:
            if cur and cur.get('uuid'): records.append(cur)
            cur = {'kind': 'S'}; continue
        if low.startswith('characteristic'):
            if cur and cur.get('uuid'): records.append(cur)
            cur = {'kind': 'C'}; continue
        if low.startswith('descriptor'):
            if cur and cur.get('uuid'): records.append(cur)
            cur = {'kind': 'D'}; continue
        if cur is None:
            continue
        if s.startswith('/org/bluez'):
            cur['path'] = s; continue
        m = UUIDre.search(s)
        if m and 'uuid' not in cur:
            full = m.group(0).lower(); cur['uuid'] = full
            s16 = UUID16.match(full); cur['short'] = s16.group(1).lower() if s16 else full[:8]
            continue
        if 'uuid' in cur and 'name' not in cur and s and 'handle' not in low:
            cur['name'] = s
    if cur and cur.get('uuid'):
        records.append(cur)
    # read a few well-known readable characteristic values
    name_hint = ''
    rows = []
    for r in records:
        short = r.get('short', ''); friendly = r.get('name') or NAMES.get(short, '')
        val = ''
        if r['kind'] == 'C' and short in READ and r.get('path'):
            b.buf.clear()
            b.cmd('select-attribute %s' % r['path'], 0.3)
            b.cmd('read', 1.0)
            hexs = []
            for L in b.buf[-40:]:
                mm = re.match(r'\s+((?:[0-9a-f]{2}\s+)+)', L)
                if mm:
                    hexs += re.findall(r'[0-9a-f]{2}', mm.group(1))
            if hexs:
                try:
                    bs = bytes(int(h, 16) for h in hexs[:40])
                    if short == '2a19':
                        val = str(bs[-1]) + '%'
                    else:
                        asc = ''.join(chr(x) if 32 <= x < 127 else '' for x in bs).strip()
                        val = asc if asc else bs.hex()
                    if short == '2a00' and val:
                        name_hint = val
                except Exception:
                    pass
        rows.append((r['kind'], short, friendly, val))
    b.cmd('disconnect %s' % MAC, 1.5)
    b.close()
    out_lines = ['DEV|%s|%s' % (MAC, name_hint)]
    for kind, short, friendly, val in rows:
        out_lines.append('%s|%s|%s|%s' % (kind, short, friendly, val))
    open(OUT, 'w').write('\n'.join(out_lines))
    st('done %d' % len([r for r in rows if r[0] in ('S', 'C')]))

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        st('error')
        try: open(OUT, 'w').write('ERR|%s' % e)
        except Exception: pass
