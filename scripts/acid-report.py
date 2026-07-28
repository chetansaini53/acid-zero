#!/usr/bin/env python3
"""
Acid Zero - Wireless Audit Report generator.

Polls bettercap for the current AP inventory and reads the passive BLE scan, grades
each finding from an attacker's point of view (open/WEP/WPA1 APs, evil-twin/duplicate
SSIDs, AirTag/Tile/SmartTag trackers), and writes ONE self-contained HTML report to:
  * /run/acid_clip.txt  - the LAN clipboard bridge (pull it with the laptop sync,
                          save as report.html, open in a browser; print -> PDF if you like)
  * /tmp/acid_audit.html - a local copy (scp-able)

100% passive / read-only - it never transmits. EVERY scan-derived string is HTML-escaped
(SSIDs and BLE names are attacker-controlled, so escaping prevents a malicious SSID from
injecting script into the report). Own-lab / educational use only.
"""
import base64
import html
import json
import os
import tempfile
import time
import urllib.request

BC = 'http://127.0.0.1:8081/api/session'
AUTH = 'Basic ' + base64.b64encode(b'pwnagotchi:pwnagotchi').decode()
CLIP = '/run/acid_clip.txt'
OUT = '/tmp/acid_audit.html'
STATUS = '/tmp/acid_report_status'
MAXCLIP = 256 * 1024

TRACKERS = (('find my', 'AirTag / Find My'), ('airtag', 'AirTag'), ('tile', 'Tile'),
            ('smarttag', 'Samsung SmartTag'), ('[tag]', 'BLE Tag'), ('[keyring]', 'Keyring'))


def _status(s):
    try:
        with open(STATUS, 'w') as f:
            f.write(s)
    except Exception:
        pass


def _aps():
    try:
        req = urllib.request.Request(BC)
        req.add_header('Authorization', AUTH)
        d = json.loads(urllib.request.urlopen(req, timeout=4).read())
        out = []
        for a in d.get('wifi', {}).get('aps', []):
            out.append({'ssid': a.get('hostname') or '<hidden>', 'bssid': a.get('mac', ''),
                        'ch': a.get('channel') or 0, 'rssi': a.get('rssi') or -99,
                        'enc': (a.get('encryption') or '?'), 'clients': len(a.get('clients', []))})
        return out
    except Exception:
        return []


def _ble():
    out = []
    try:
        for ln in open('/tmp/acid_ble_devices'):
            p = ln.rstrip('\n').split('|')
            if len(p) >= 4:
                out.append({'mac': p[0], 'rssi': p[1], 'label': p[3]})
    except Exception:
        pass
    return out


def _grade(enc):
    e = (enc or '').upper()
    if e in ('', '?') or 'OPEN' in e:
        return ('OPEN', 'crit', 'No encryption - traffic is sniffable and MITM-able.')
    if 'WEP' in e:
        return ('WEP', 'high', 'WEP is broken - key recoverable in minutes.')
    if 'WPA3' in e:
        return ('WPA3', 'ok', 'Modern - SAE resists offline cracking.')
    if 'WPA2' in e:
        return ('WPA2', 'ok', 'OK with a strong passphrase; enable 802.11w PMF.')
    if 'WPA' in e:
        return ('WPA1', 'high', 'WPA1/TKIP deprecated - upgrade to WPA2-AES/WPA3.')
    return (e, 'warn', 'Unrecognised - verify the cipher.')


def _tracker(label):
    low = (label or '').lower()
    for k, name in TRACKERS:
        if k in low:
            return name
    return None


def _e(s):
    return html.escape(str(s))


CSS = """
:root{color-scheme:light}
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1a2230;background:#eef1f5}
.wrap{max-width:900px;margin:0 auto;padding:24px}
header{background:linear-gradient(135deg,#0f172a,#1e293b);color:#e6edf6;border-radius:14px;padding:22px 26px}
header h1{margin:0 0 4px;font-size:22px;letter-spacing:.5px}
header .sub{color:#93a3b8;font-size:13px}
.cards{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0}
.card{flex:1 1 120px;background:#fff;border:1px solid #dbe1ea;border-radius:12px;padding:14px}
.card .n{font-size:24px;font-weight:700}
.card .l{font-size:12px;color:#68758a;text-transform:uppercase;letter-spacing:.4px}
h2{font-size:16px;margin:26px 0 10px;border-left:4px solid #2563eb;padding-left:10px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #dbe1ea;border-radius:12px;overflow:hidden}
th,td{padding:9px 12px;text-align:left;font-size:13px;border-bottom:1px solid #eef1f5}
th{background:#f6f8fb;color:#54617a;font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.4px}
tr:last-child td{border-bottom:0}
.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:700}
.crit{background:#fde2e2;color:#b3261e}.high{background:#ffe6d1;color:#b45309}.warn{background:#fff4cf;color:#8a6d00}.ok{background:#d9f2e3;color:#137a43}
.mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:#4b5566}
ul.harden{background:#fff;border:1px solid #dbe1ea;border-radius:12px;padding:14px 14px 14px 30px;margin:0}
ul.harden li{margin:6px 0}
.empty{color:#68758a;font-style:italic;padding:10px 2px}
footer{margin:26px 0 4px;color:#8492a6;font-size:12px;text-align:center}
"""


def build_html(aps, bdevs):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    graded = [(a, _grade(a['enc'])) for a in aps]
    weak = [(a, g) for a, g in graded if g[1] in ('crit', 'high')]
    # evil-twin: SSID on >=2 BSSIDs, escalate on open+secured mix
    groups = {}
    for a in aps:
        s = a['ssid']
        if s and s != '<hidden>':
            groups.setdefault(s, []).append(a)
    twins = []
    for s, lst in groups.items():
        bssids = {a['bssid'] for a in lst if a['bssid']}
        if len(bssids) < 2:
            continue
        encs = sorted({(a['enc'] or '?') for a in lst})
        sec = any(('WPA' in e.upper() or 'WEP' in e.upper()) for e in encs)
        ins = any(not ('WPA' in e.upper() or 'WEP' in e.upper()) for e in encs)
        twins.append((s, len(bssids), encs, sec and ins))
    trk = [(b, _tracker(b['label'])) for b in bdevs]
    trackers = [(b, name) for b, name in trk if name]

    def cards():
        items = [('APs seen', len(aps), 'ok'), ('Weak / open', len(weak), 'crit' if weak else 'ok'),
                 ('Evil-twin', sum(1 for t in twins if t[3]), 'crit' if any(t[3] for t in twins) else 'ok'),
                 ('BLE devices', len(bdevs), 'ok'), ('Trackers', len(trackers), 'high' if trackers else 'ok')]
        return ''.join('<div class="card"><div class="n">%d</div><div class="l">%s</div></div>' % (n, _e(l)) for l, n, _c in items)

    ap_rows = ''
    for a, (label, sev, note) in sorted(graded, key=lambda x: (x[1][1] != 'crit', x[1][1] != 'high', -int(x[0]['rssi']) if str(x[0]['rssi']).lstrip('-').isdigit() else 0)):
        ap_rows += ('<tr><td>%s</td><td class="mono">%s</td><td>%s</td><td>%s dBm</td>'
                    '<td><span class="badge %s">%s</span></td><td>%s</td></tr>' %
                    (_e(a['ssid']), _e(a['bssid']), _e(a['ch']), _e(a['rssi']), sev, _e(label), _e(note)))
    if not ap_rows:
        ap_rows = '<tr><td colspan="6" class="empty">no APs in range (is a WiFi scan running?)</td></tr>'

    twin_html = ''
    for s, n, encs, danger in sorted(twins, key=lambda x: not x[3]):
        badge = '<span class="badge crit">EVIL-TWIN</span>' if danger else '<span class="badge warn">DUPLICATE</span>'
        twin_html += '<tr><td>%s</td><td>%d BSSIDs</td><td class="mono">%s</td><td>%s</td></tr>' % (
            _e(s), n, _e(' / '.join(encs)), badge)
    if not twin_html:
        twin_html = '<tr><td colspan="4" class="empty">no duplicate SSIDs - no evil-twin indicators</td></tr>'

    ble_rows = ''
    for b, name in sorted(trk, key=lambda x: x[1] is None):
        tb = '<span class="badge high">%s</span>' % _e(name) if name else ''
        ble_rows += '<tr><td>%s</td><td class="mono">%s</td><td>%s dBm</td><td>%s</td></tr>' % (
            _e(b['label']), _e(b['mac']), _e(b['rssi']), tb)
    if not ble_rows:
        ble_rows = '<tr><td colspan="4" class="empty">no BLE devices seen (run a BLE scan first)</td></tr>'

    harden = ['Never join <b>OPEN</b> Wi-Fi without a VPN - the link is sniffable and MITM-able.',
              'Retire <b>WEP / WPA1</b> on your own gear; move to WPA2-AES or WPA3-SAE.',
              'Enable <b>802.11w PMF</b> so deauth/disassoc frames are cryptographically ignored.',
              'Distrust a duplicate SSID that appears both <b>open and secured</b> - classic evil-twin tell.',
              'Use a long random passphrase (15+ chars); disable WPS.',
              'If an unknown tracker keeps appearing, check your bag / car / clothing. (Tags rotate MAC ~15&nbsp;min, so this shows <i>presence</i>, not a confirmed follow.)',
              'Keep BLE off when not in use; keep your phone OS updated (fast-pair popup rate-limits).']

    return ('<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Acid Zero - Wireless Audit Report</title><style>%s</style></head><body><div class="wrap">'
            '<header><h1>Wireless Audit Report</h1>'
            '<div class="sub">Generated by Acid Zero &middot; passive recon &middot; %s</div></header>'
            '<div class="cards">%s</div>'
            '<h2>Access Points (attacker view)</h2>'
            '<table><tr><th>SSID</th><th>BSSID</th><th>Ch</th><th>Signal</th><th>Grade</th><th>Risk</th></tr>%s</table>'
            '<h2>Evil-Twin / Duplicate SSIDs</h2>'
            '<table><tr><th>SSID</th><th>BSSIDs</th><th>Encryption seen</th><th>Verdict</th></tr>%s</table>'
            '<h2>BLE Devices &amp; Trackers</h2>'
            '<table><tr><th>Device</th><th>MAC</th><th>Signal</th><th>Tracker?</th></tr>%s</table>'
            '<h2>Hardening Checklist</h2><ul class="harden">%s</ul>'
            '<footer>Acid Zero is a passive, own-lab defensive recon tool. It never transmits. '
            'Findings reflect only what devices already broadcast at scan time.</footer>'
            '</div></body></html>') % (CSS, _e(ts), cards(), ap_rows, twin_html, ble_rows,
                                       ''.join('<li>%s</li>' % h for h in harden))


def _write(path, data):
    try:
        d = os.path.dirname(path) or '.'
        fd, tmp = tempfile.mkstemp(dir=d, prefix='.acidrep')
        try:
            os.write(fd, data.encode('utf-8'))
        finally:
            os.close(fd)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def main():
    _status('generating...')
    aps = _aps()
    bdevs = _ble()
    doc = build_html(aps, bdevs)
    _write(OUT, doc)
    try:
        os.chmod(OUT, 0o644)       # shareable deliverable (public RF observations) - scp-able by the login user
    except Exception:
        pass
    if len(doc.encode('utf-8')) <= MAXCLIP:
        _write(CLIP, doc)              # into the LAN clipboard bridge for laptop pull
        _status('done %d APs %d BLE - report copied to clipboard + %s' % (len(aps), len(bdevs), OUT))
    else:
        _status('done %d APs %d BLE - too big for clipboard, saved %s' % (len(aps), len(bdevs), OUT))
    print('REPORT_DONE aps=%d ble=%d bytes=%d' % (len(aps), len(bdevs), len(doc)))


if __name__ == '__main__':
    main()
