#!/usr/bin/env python3
# ACID BLE scanner v6 - RICH device identification via btmon. Read-only recon.
# btmon decodes each LE advertising report (vendor Company-ID, OUI for public MACs, name,
# appearance, Apple Continuity type/model) while btmgmt drives discovery. We parse that into
# a human label: "AirPods Pro (Apple)", "Samsung device", "Motorola (Moto G)", etc.
# Output -> /tmp/acid_ble_devices : MAC|rssi|atype|label  (strongest first)
import subprocess, time, os, re, sys

DUR = int(sys.argv[1]) if len(sys.argv) > 1 else 8
BT = '/tmp/acid_ble_btmon.txt'
OUT = '/tmp/acid_ble_devices'

# ==== LOOKUP TABLES (BEGIN - replaced/expanded by the research workflow) ====
APPLE_MODELS = {
    0x0E20: "AirPods Pro", 0x0220: "AirPods", 0x0F20: "AirPods 2", 0x1320: "AirPods 3",
    0x1920: "AirPods 4", 0x1B20: "AirPods 4 (ANC)", 0x1420: "AirPods Pro 2",
    0x2420: "AirPods Pro 2 (USB-C)", 0x2720: "AirPods Pro 3", 0x0A20: "AirPods Max",
    0x1F20: "AirPods Max (USB-C)", 0x2D20: "AirPods Max 2",
    0x0520: "BeatsX", 0x0620: "Beats Solo 3", 0x0920: "Beats Studio 3", 0x0C20: "Beats Solo Pro",
    0x1020: "Beats Flex", 0x1120: "Beats Studio Buds", 0x1220: "Beats Fit Pro",
    0x1620: "Beats Studio Buds+", 0x1720: "Beats Studio Pro", 0x2520: "Beats Solo 4",
    0x2620: "Beats Solo Buds", 0x0320: "Powerbeats 3", 0x0B20: "Powerbeats Pro",
    0x0D20: "Powerbeats 4", 0x1D20: "Powerbeats Pro 2", 0x2F20: "Powerbeats Fit",
    0x0055: "AirTag", 0x0030: "Hermes AirTag",
}
APPLE_TYPES = {
    0x03: "AirPrint", 0x05: "AirDrop", 0x06: "HomeKit", 0x07: "Proximity Pair (AirPods)",
    0x08: "Hey Siri", 0x09: "AirPlay Target", 0x0A: "AirPlay Source", 0x0B: "Watch Magic Switch",
    0x0C: "Handoff", 0x0D: "Tethering Target", 0x0E: "Instant Hotspot",
    0x0F: "Nearby Action", 0x10: "Nearby (iPhone/iPad/Mac)", 0x12: "Find My",
}
APPEARANCE = {
    0x0040: "Phone", 0x0080: "Computer", 0x0083: "Laptop", 0x0086: "Tablet", 0x008A: "Wearable PC",
    0x00C0: "Watch", 0x00C1: "Sports Watch", 0x00C2: "Smartwatch", 0x0100: "Clock",
    0x0140: "Display", 0x0180: "Remote", 0x01C0: "Eyeglasses", 0x0200: "Tag", 0x0240: "Keyring",
    0x0280: "Media Player", 0x0300: "Thermometer", 0x0340: "Heart Rate", 0x0380: "Blood Pressure",
    0x03C0: "HID", 0x03C1: "Keyboard", 0x03C2: "Mouse", 0x03C3: "Joystick", 0x03C4: "Gamepad",
    0x03C7: "Digital Pen", 0x0400: "Glucose Meter", 0x0440: "Run/Walk Sensor", 0x0480: "Cycling",
    0x0C40: "Pulse Oximeter", 0x0C80: "Weight Scale", 0x1440: "Outdoor Sports",
    0x0940: "Audio Device", 0x0941: "Earbuds", 0x0942: "Headset", 0x0943: "Headphones",
    0x0944: "Microphone", 0x0945: "Speaker", 0x0946: "Soundbar",
}
FASTPAIR = {
    0x92BBBD: "Pixel Buds", 0x718C17: "Pixel Buds A", 0x07A41C: "Pixel Buds Pro", 0xD87A3E: "Pixel Buds Pro 2",
    0xCD8256: "Bose NC 700", 0x0000F0: "Bose QC35 II", 0x9E8DD1: "Bose QC Earbuds", 0xA7FEC9: "Bose QC Ultra",
    0xF52494: "JBL Buds Pro", 0x718FA4: "JBL Live 300", 0x821F66: "JBL Flip 6", 0x0001F0: "JBL Live 400BT",
    0x038B91: "JBL Tune 660NC", 0x1E8B49: "JBL Live Pro 2", 0xF00000: "JBL Endurance Peak II",
    0x2D7A23: "Sony WF-1000XM4", 0xD446A7: "Sony WH-1000XM5", 0x0E30C3: "Sony WF-1000XM3",
    0x056E2B: "Sony WH-1000XM4", 0xC8D332: "Sony LinkBuds S",
    0x9C0436: "Galaxy Buds Live", 0xA7C49E: "Galaxy Buds2", 0xE2A87B: "Galaxy Buds Pro",
    0x05A963: "Galaxy Buds2 Pro", 0xBFD25B: "Galaxy Buds+", 0x536D1E: "Galaxy Buds FE",
    0xAA187F: "Beats Studio Buds", 0xB37A62: "Beats Fit Pro", 0x9712CB: "Beats Studio Buds+",
    0x77FF67: "Beats Studio Pro", 0xC8D6FE: "Sennheiser MTW3", 0x839FB7: "Sennheiser CX Plus",
    0xC9D9F5: "Soundcore Liberty Air 2", 0xF8C5A2: "Soundcore Liberty 4", 0x72EF8D: "Razer Hammerhead",
    0x72FB00: "OnePlus Buds Pro", 0x0E2BA4: "Nothing Ear (1)", 0xBC8CD9: "LG TONE Free FP9",
}
# ==== LOOKUP TABLES (END) ====

def st(s):
    try: open('/tmp/acid_ble_status', 'w').write(s)
    except Exception: pass

def scan():
    st('scanning')
    try: mon = subprocess.Popen(['btmon'], stdout=open(BT, 'w'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    except Exception: mon = None
    time.sleep(0.3)
    # drive discovery; sleep-pipe keeps btmgmt stdin open (it stops on EOF)
    subprocess.run(['bash', '-c', 'sleep %d | timeout %d btmgmt find -l >/dev/null 2>&1' % (DUR + 2, DUR)])
    time.sleep(0.3)
    if mon:
        try: mon.terminate(); mon.wait(timeout=3)
        except Exception:
            try: mon.kill()
            except Exception: pass

def parse():
    recs = {}
    cur = None
    try: lines = open(BT, errors='replace').read().split('\n')
    except Exception: lines = []
    for ln in lines:
        m = re.search(r'\bAddress:\s+([0-9A-F:]{17})\s*(?:\(([^)]*)\))?', ln)
        if m and 'LE Address' not in ln:
            mac = m.group(1); oui = (m.group(2) or '').strip()
            cur = recs.get(mac)
            if not cur:
                cur = {'mac': mac, 'oui': '', 'company': '', 'name': '', 'appr': 0,
                       'atype': None, 'adata': '', 'rssi': -127, 'fp': 0, 'fpctx': False}
                recs[mac] = cur
            if oui and oui not in ('Resolvable', 'Non-Resolvable', 'Public', 'Static', 'Random'):
                cur['oui'] = oui
            continue
        if cur is None:
            continue
        mc = re.search(r'Company:\s+(.+?)\s*\(\d+\)', ln)
        if mc: cur['company'] = mc.group(1).strip(); continue
        mt = re.search(r'\bType:\s+\w+\s*\((\d+)\)', ln)
        if mt and cur['company'].startswith('Apple'):
            cur['atype'] = int(mt.group(1)); continue
        if 'fe2c' in ln.lower():
            cur['fpctx'] = True
            h = re.findall(r'[0-9a-fA-F]{6,}', ln)
            if h:
                try: cur['fp'] = int(h[-1][:6], 16)
                except Exception: pass
            continue
        md = re.search(r'Data\[\d+\]:\s+([0-9a-fA-F]+)', ln)
        if md:
            if cur['fpctx'] and not cur['fp']:
                try: cur['fp'] = int(md.group(1)[:6], 16)
                except Exception: pass
            elif not cur['adata']:
                cur['adata'] = md.group(1)
            continue
        mn = re.search(r'Name \([^)]*\):\s+(.+)', ln)
        if mn: cur['name'] = mn.group(1).strip(); continue
        ma = re.search(r'Appearance:.*\((0x[0-9a-fA-F]+)\)', ln)
        if ma:
            try: cur['appr'] = int(ma.group(1), 16)
            except Exception: pass
            continue
        mr = re.search(r'RSSI:\s+(-?\d+)', ln)
        if mr:
            r = int(mr.group(1))
            if r > cur['rssi']: cur['rssi'] = r
            continue
    return recs

def apple_model(adata):
    # adata for a proximity-pair (type 7) ~ "<len> <prefix> <model_hi><model_lo> <status>..."
    # try a couple of offsets to pull the 2-byte model and look it up
    b = bytes.fromhex(adata) if adata and len(adata) % 2 == 0 else b''
    for off in (2, 1, 3):
        if len(b) >= off + 2:
            mdl = (b[off] << 8) | b[off + 1]
            if mdl in APPLE_MODELS:
                return APPLE_MODELS[mdl]
    return None

def label(r):
    appr = APPEARANCE.get(r['appr'], '')
    if r['fp'] in FASTPAIR:
        base = FASTPAIR[r['fp']]
    elif r['company'].startswith('Apple'):
        at = r['atype']
        if at == 0x07:
            base = (apple_model(r['adata']) or 'AirPods/Beats') + ' (Apple)'
        elif at == 0x10:
            base = 'iPhone/iPad/Mac (Apple)'
        elif at in APPLE_TYPES:
            base = 'Apple - ' + APPLE_TYPES[at]
        else:
            base = 'Apple device'
    elif r['name']:
        base = r['name'] + ((' (' + r['company'] + ')') if r['company'] else '')
    elif r['company']:
        base = r['company'] + ' device'
    elif appr:
        base = appr
    elif r['oui']:
        base = r['oui'].title()
    else:
        base = 'unknown'
    if appr and appr.lower() not in base.lower():
        base += ' [' + appr + ']'
    return base[:40]

def main():
    scan()
    recs = parse()
    rows = []
    for r in recs.values():
        if r['rssi'] == -127:
            continue
        rows.append('%s|%d|%s|%s' % (r['mac'], r['rssi'], ('pub' if r['oui'] else 'rnd'), label(r)))
    rows.sort(key=lambda x: int(x.split('|')[1]), reverse=True)
    try: open(OUT, 'w').write('\n'.join(rows))
    except Exception: pass
    st('done %d' % len(rows))
    print('BLE_RICH_DONE %d' % len(rows))

if __name__ == '__main__':
    main()
