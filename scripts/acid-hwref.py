#!/usr/bin/env python3
# Acid Zero - Hardware & Porting Reference generator.
# Collects LIVE hardware facts from this Pi, then emits BOTH:
#   ~/acid-hwref.html  (styled, dependency-free, print-to-PDF in any browser)
#   ~/acid-hwref.pdf   (real PDF via an inline zero-dependency PDF writer)
# No pip installs, no system packages. Educational / own-lab device reference.
import subprocess, os, time, html

HOME = os.path.expanduser('~')
HTML_OUT = os.path.join(HOME, 'acid-hwref.html')
PDF_OUT = os.path.join(HOME, 'acid-hwref.pdf')

def sh(c):
    try:
        return subprocess.run(['bash', '-c', c], capture_output=True, timeout=6).stdout.decode('utf-8', 'replace').strip()
    except Exception:
        return ''

# ---------------------------------------------------------------- live facts
def live():
    f = {}
    f['model'] = sh("cat /proc/device-tree/model | tr -d '\\0'") or 'Raspberry Pi'
    f['rev'] = sh("awk '/Revision/{print $3}' /proc/cpuinfo")
    f['kernel'] = sh('uname -r')
    f['arch'] = sh('uname -m')
    f['os'] = sh("(. /etc/os-release 2>/dev/null; echo $PRETTY_NAME)")
    f['ram'] = sh("awk '/MemTotal/{printf \"%d MB\", $2/1024}' /proc/meminfo")
    f['fbname'] = sh("cat /sys/class/graphics/fb1/name 2>/dev/null") or 'fb_ili9486'
    f['fbsize'] = sh("cat /sys/class/graphics/fb1/virtual_size 2>/dev/null") or '480,320'
    f['fbbpp'] = sh("cat /sys/class/graphics/fb1/bits_per_pixel 2>/dev/null") or '16'
    f['touch'] = sh("for d in /sys/class/input/event*/device/name; do n=$(cat $d); echo \"$n\" | grep -qi 'ADS7846\\|touch' && { echo $(echo $d|grep -oE 'event[0-9]+'): $n; break; }; done") or 'event0: ADS7846 Touchscreen'
    f['bt'] = sh("hciconfig 2>/dev/null | awk '/BD Address/{print $3}' | head -1") or '-'
    f['i2c'] = sh("ls /dev/i2c* 2>/dev/null | tr '\\n' ' '") or 'none'
    f['spidev'] = sh("ls /dev/spidev* 2>/dev/null | tr '\\n' ' '") or 'none (SPI0 consumed by TFT overlay)'
    f['overlays'] = sh("grep -hoE 'dtoverlay=[^ ]*' /boot/firmware/config.txt /boot/config.txt 2>/dev/null | sort -u | tr '\\n' ' '")
    # radio table
    rows = []
    USB = {'0e8d:7612': ('MT7612U', 'AWUS036ACM', '2.4/5', 'monitor+inject'),
           '0bda:8812': ('RTL8812AU', 'AWUS036ACH', '2.4/5', 'AP+inject'),
           '2357:0120': ('RTL8821AU', 'Archer T2U+', '2.4/5', 'client/SSH'),
           '0bda:8179': ('RTL8188EUS', 'generic', '2.4 only', 'client')}
    lsusb = sh('lsusb')
    ifs = sh("ls /sys/class/net | grep -E '^wlan'").split()
    for w in ifs:
        drv = sh("basename $(readlink /sys/class/net/%s/device/driver 2>/dev/null) 2>/dev/null" % w) or '?'
        rows.append((w, drv))
    f['ifs'] = rows
    # match USB ids present
    usbrows = []
    for vid, (chip, mod, band, cap) in USB.items():
        if vid in lsusb:
            usbrows.append((vid, chip, mod, band, cap))
    if 'brcmfmac' in [d for _, d in rows]:
        usbrows.insert(0, ('onboard', 'BCM43455', 'built-in', '2.4/5', 'limited monitor'))
    f['usb'] = usbrows
    return f

# ---------------------------------------------------------------- content
def content(f):
    B = []  # (kind, text)  kind: h1 h2 b m rule sp
    def h1(t): B.append(('h1', t))
    def h2(t): B.append(('h2', t))
    def b(t): B.append(('b', t))
    def m(t): B.append(('m', t))
    def sp(): B.append(('sp', ''))
    def rule(): B.append(('rule', ''))

    h1('1. SYSTEM OVERVIEW (live)')
    b('Board : %s  (rev %s)' % (f['model'], f['rev']))
    b('OS    : %s   kernel %s  (%s)' % (f['os'], f['kernel'], f['arch']))
    b('RAM   : %s' % f['ram'])
    b('Active dtoverlays: %s' % (f['overlays'] or '-'))
    b('I2C buses: %s     SPI char devs: %s' % (f['i2c'], f['spidev']))
    sp()

    h1('2. DISPLAY - ILI9486 TFT')
    b('Panel: ILI9486  480x320  16bpp RGB565.  Driver: fbtft (piscreen overlay).  Node: /dev/fb1.')
    b('Bus: SPI0 @ 16 MHz, rotate 270.  Overlay: dtoverlay=piscreen,speed=16000000,rotate=270')
    h2('RGB565 pixel format (what every native app must write)')
    m('v = ((R & 0xF8) << 8) | ((G & 0xFC) << 3) | (B >> 3)   # 16-bit')
    m('byte order = little-endian, 2 bytes/px.  frame = 480*320*2 = 307200 bytes')
    m('pixel (x,y) byte offset = (y*480 + x) * 2')
    b('To draw: build a 480x320 RGB565 buffer and write the whole frame to /dev/fb1 (or mmap it).')
    h2('SPI wiring (piscreen standard, SPI0)')
    m('MOSI GPIO10 (pin19)   SCLK GPIO11 (pin23)   LCD-CS CE0 GPIO8 (pin24)')
    m('TOUCH-CS CE1 GPIO7 (pin26)   DC GPIO24   RESET GPIO25   backlight GPIO18')
    h2('ILI9486 command set (bare-metal SPI port)')
    m('0x01 SWRESET  0x11 SLPOUT  0x29 DISPON  0x36 MADCTL(rotation)  0x3A COLMOD(0x55=16bpp)')
    m('0x2A CASET(col)  0x2B PASET(page)  0x2C RAMWR(pixel data follows)')
    sp()

    h1('3. TOUCH - ADS7846 / XPT2046')
    b('%s   on SPI0 CE1 (GPIO7) + IRQ GPIO.  Linux input event device, 12-bit X/Y.' % f['touch'])
    b('Acid Zero uses 4-point AFFINE calibration (least-squares), residual gate <= 45 px.')
    h2('Raw read (bare-metal SPI)')
    m('TX 0x90 -> read 2 bytes -> Y (>>3 = 12-bit).   TX 0xD0 -> read 2 bytes -> X (>>3).')
    h2('Linux input_event struct (read from /dev/input/eventN)')
    m('{ struct timeval time; __u16 type; __u16 code; __s32 value; }  (16B on 32-bit / 24B 64-bit)')
    m('EV_SYN=0  EV_KEY=1  EV_ABS=3 | ABS_X=0x00  ABS_Y=0x01 | BTN_TOUCH=0x14a')
    sp()

    h1('4. NATIVE PLUGIN CONTRACT (add ANY app, incl compiled C/C++/Rust)')
    b('Drop a folder:  /usr/local/lib/acid-apps/<yourapp>/  containing app.json + an executable.')
    h2('app.json manifest')
    m('{ "type":"native", "name":"My App", "icon":"usb",')
    m('  "color":[30,200,121], "exec":"mybin"  }   # exec = binary or script in the folder')
    h2('Runtime contract')
    b('1) Your program OWNS /dev/fb1 + the touch event device while it runs.')
    b('2) Render RGB565 frames (see section 2); read taps from the ADS7846 evdev node.')
    b('3) EXIT(0) on your exit gesture. The launcher is BLOCKED on you and redraws home on return.')
    b('Find devices by NAME, not number (fb#/event# reshuffle each boot):')
    m("fb   -> match 'ili9486' / 'fb_ili9486' in /sys/class/graphics/fb*/name")
    m("touch-> match 'ADS7846' in /sys/class/input/event*/device/name")
    b('Language-agnostic: anything that can open /dev/fb1 + an evdev node works (C/C++/Rust/Go/Py).')
    b('Reference template: /usr/local/lib/acid-apps/hello-native/ (standalone Python).')
    h2('Python in-process plugins (lighter alternative)')
    m('/usr/local/lib/acid-apps/*.py  with  META={name,icon,color}  +  draw(d,ctx)')
    m('optional: on_enter(ctx), handle_touch(tx,ty,ctx).  Shares the launcher Ctx (fonts/colors/helpers).')
    sp()

    h1('5. WiFi RADIOS')
    b('Bind adapters by USB VID:PID, NEVER by wlanN (interface numbers reshuffle every boot).')
    m('%-11s %-12s %-12s %-9s %s' % ('VID:PID', 'chipset', 'module', 'bands', 'role'))
    for vid, chip, mod, band, cap in f['usb']:
        m('%-11s %-12s %-12s %-9s %s' % (vid, chip, mod, band, cap))
    h2('live interface -> driver map')
    for w, drv in f['ifs']:
        m('%-9s %s' % (w, drv))
    b('mt76x2u exposes a base iface + a monitor iface (wlan0mon). brcmfmac = onboard BCM43455.')
    sp()

    h1('6. BLUETOOTH / BLE')
    b('Controller: hci0, Broadcom over UART, BD addr %s.' % f['bt'])
    b('Acid Zero BLE spam uses a RAW HCI USER-channel socket (HCI_CHANNEL_USER=1); bluetoothd is stopped')
    b('for exclusive control. ~32 adv frames/sec. own_addr_type MUST be 01 (random) or iOS dedups.')
    h2('Key HCI LE commands (OGF 0x08)')
    m('OCF 0x0005 LE Set Random Address   0x0006 LE Set Adv Params   0x0008 LE Set Adv Data')
    m('OCF 0x000A LE Set Adv Enable        ioctl HCIDEVDOWN = 0x400448ca')
    h2('BLE advertising payloads implemented (Flipper BLE-spam port reference)')
    m('Apple Continuity : mfg Company 0x004C; ProximityPair type 0x07 + 2B model; NearbyAction 0x0F flags 0xC0')
    m('Google Fast Pair : 02 01 06 | 03 03 2C FE | 06 16 2C FE <3B model>  (Google validates model IDs)')
    m('Samsung          : mfg Company 0x0075      Microsoft Swift Pair: mfg Company 0x0006')
    h2('BLE scan (read-only recon)')
    b('btmon decodes each adv report (Company-ID->vendor, OUI, name, appearance, Apple model, Fast-Pair model).')
    m('drive discovery:  sleep N | timeout M btmgmt find -l   (keep stdin open; btmgmt stops on EOF)')
    sp()

    h1('7. SUB-GHz - CC1101 (planned: porting guide)')
    b('CC1101 = SPI sub-GHz transceiver: 300-348 / 387-464 / 779-928 MHz. Same family Flipper uses,')
    b('so .sub OOK/ASK captures are conceptually portable.')
    h2('WIRING PROBLEM on this build')
    b('SPI0 is fully consumed by the TFT + touch (piscreen). For CC1101 use one of:')
    b('  a) SPI1 - enable dtoverlay=spi1-1cs : MISO GPIO19(p35) MOSI GPIO20(p38) SCLK GPIO21(p40) CE GPIO18/16/17')
    b('     (watch GPIO18 vs backlight clash)')
    b('  b) bit-bang SPI on spare GPIOs    c) time-share SPI0 2nd CS (risky during display refresh)')
    h2('CC1101 register/strobe basics')
    m('FREQ2/1/0 carrier  MDMCFG2 (ASK/OOK)  PKTCTRL0/1  DEVIATN  AGCCTRL  FSCAL  TEST')
    m('strobes: SRES 0x30  SRX 0x34  STX 0x35  SIDLE 0x36  SFRX 0x3A  SFTX 0x3B   FIFO 0x3F(burst)')
    m('freq: f = FREQ * 26MHz / 2^16     433.92 MHz -> FREQ ~= 0x10B071')
    b('Stacks: SmartRC-CC1101 (Arduino port), pi433, python cc1101 over spidev. OOK replay via GDO0 timing.')
    b('Flipper .sub porting: parse RAW_Data timings -> toggle GDO0 TX (timed) or CC1101 async TX.')
    sp()

    h1('8. NFC / RFID - PN532 (planned: porting guide)')
    b('PN532 = 13.56 MHz NFC: ISO14443A/B, MIFARE Classic/Ultralight, FeliCa, NDEF, card emulation.')
    b('Selectable bus by DIP: I2C / SPI / HSU(UART).')
    h2('RECOMMENDED here: I2C  (I2C-1 is FREE; SPI0 is busy with the TFT)')
    m('SDA GPIO2 (pin3)   SCL GPIO3 (pin5)   VCC 3V3   GND   addr 0x24   (IRQ optional GPIO)')
    b('Software: libnfc (device = pn532_i2c:/dev/i2c-1), Adafruit-PN532 (python I2C), nfcpy (UART).')
    b('MIFARE Classic keys: mfoc / mfcuk + libnfc.')
    b('NOTE: 125 kHz RFID (EM4100/HID) needs a DIFFERENT front-end (RDM6300 UART / EM4095) - PN532 is')
    b('13.56 MHz only. (Flipper covers both bands via separate hardware front-ends.)')
    b('Flipper NFC porting: dump = UID + sector keys + blocks; replay via PN532 emulation or a magic card.')
    sp()

    h1('9. IR (planned)')
    b('TX: 38 kHz carrier via dtoverlay=gpio-ir-tx (a TX GPIO).  RX: dtoverlay=gpio-ir.')
    b('Tools: LIRC or ir-ctl.  Flipper .ir (protocol/address/command) -> LIRC config or raw timing.')
    sp()

    h1('10. GPIO / BUS AVAILABILITY MAP (this build)')
    m('SPI0      : BUSY  - ILI9486 (CE0) + ADS7846 touch (CE1)')
    m('SPI1      : FREE  - candidate for CC1101  (enable dtoverlay=spi1-1cs)')
    m('I2C-1     : FREE  - candidate for PN532   (GPIO2/3)')
    m('I2C-2     : present')
    m('UART0     : GPIO14/15 - console/BT, handle with care')
    m('USB       : 4x WiFi dongles via onboard hub')
    m('free GPIO : 5 6 12 13 16 17 19 20 21 22 23 26 27  (verify vs active overlays before use)')
    sp()

    h1('11. PORTING FLIPPER CODE -> Acid Zero (cheat-sheet)')
    m('UI      : Flipper Canvas 128x64 mono  ->  fb1 480x320 RGB565 (map canvas_draw_* to PIL/fb)')
    m('Buttons : Flipper D-pad/OK            ->  ADS7846 taps (evdev)')
    m('Sub-GHz : Flipper CC1101              ->  Pi CC1101 on SPI1 (same chip: port reg init + .sub)')
    m('NFC     : Flipper ST25R3916           ->  PN532 (diff chip: port logic via libnfc, not regs)')
    m('BLE spam: apple_ble_spam.c payloads   ->  already done via raw HCI (section 6)')
    m('IR      : .ir files                   ->  LIRC / ir-ctl')
    m('Apps    : compile to ARM64 (aarch64)  ->  drop as native plugin (section 4)')
    return B

# ---------------------------------------------------------------- HTML out
def emit_html(B, f, stamp):
    css = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:900px;margin:24px auto;
padding:0 24px;color:#14181f;line-height:1.5;font-size:15px;background:#fff}
h1.t{font-size:26px;margin:0 0 2px;color:#0b4380}
.sub{color:#5a6675;margin:0 0 14px;font-size:14px}
h1{font-size:18px;color:#0b4380;border-bottom:2px solid #0b4380;padding-bottom:3px;margin:26px 0 8px}
h2{font-size:14px;color:#2a3340;margin:14px 0 4px}
p{margin:3px 0}
pre{background:#f3f5f8;border:1px solid #dde3ea;border-radius:6px;padding:7px 10px;margin:4px 0;
font-family:Consolas,Menlo,monospace;font-size:12.5px;white-space:pre-wrap;color:#10202e}
.meta{background:#0b4380;color:#dce8f5;border-radius:8px;padding:10px 14px;font-size:12.5px;
font-family:Consolas,monospace;white-space:pre-wrap}
hr{border:0;border-top:1px solid #dde3ea;margin:10px 0}
.foot{color:#7a8694;font-size:12px;margin-top:24px;border-top:1px solid #dde3ea;padding-top:8px}
@media print{body{margin:0;max-width:none;font-size:11.5pt}h1{page-break-after:avoid}pre{page-break-inside:avoid}}
"""
    parts = ['<!doctype html><meta charset="utf-8"><title>Acid Zero - Hardware Reference</title>',
             '<style>%s</style>' % css,
             '<h1 class="t">Acid Zero &mdash; Hardware &amp; Porting Reference</h1>',
             '<p class="sub">Raspberry Pi 3B+ pentest handheld &middot; reference for porting C/C++/Rust/Python/Flipper code</p>',
             '<div class="meta">%s</div>' % html.escape('%s  (rev %s)\n%s  kernel %s %s\ngenerated %s' % (
                 f['model'], f['rev'], f['os'], f['kernel'], f['arch'], stamp))]
    buf = []
    def flush_pre():
        if buf:
            parts.append('<pre>%s</pre>' % '\n'.join(html.escape(x) for x in buf))
            buf.clear()
    for kind, txt in B:
        if kind == 'm':
            buf.append(txt); continue
        flush_pre()
        if kind == 'h1':
            parts.append('<h1>%s</h1>' % html.escape(txt))
        elif kind == 'h2':
            parts.append('<h2>%s</h2>' % html.escape(txt))
        elif kind == 'b':
            parts.append('<p>%s</p>' % html.escape(txt))
        elif kind == 'rule':
            parts.append('<hr>')
        elif kind == 'sp':
            parts.append('')
    flush_pre()
    parts.append('<div class="foot">Acid Zero &middot; Chetan Saini &middot; ITOB &middot; own-lab / educational reference</div>')
    open(HTML_OUT, 'w', encoding='utf-8').write('\n'.join(parts))

# ---------------------------------------------------------------- PDF out (zero-dep)
def emit_pdf(B, f, stamp):
    PW, PH = 595.0, 842.0
    ML, MRr, MT, MB = 48, 48, 52, 50
    LEAD = {'title': 23, 'h1': 18, 'h2': 15, 'b': 12.5, 'm': 11.5, 'sp': 7, 'rule': 11}
    SIZE = {'title': 17, 'h1': 13, 'h2': 11, 'b': 9.5, 'm': 8.5}
    FONT = {'title': '/F2', 'h1': '/F2', 'h2': '/F2', 'b': '/F1', 'm': '/F3'}
    COL = {'title': '0.04 0.26 0.5', 'h1': '0.04 0.26 0.5', 'h2': '0.16 0.2 0.25', 'b': '0 0 0', 'm': '0.08 0.13 0.18'}

    def esc(s):
        return s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

    def wrap(s, n):
        out = []
        for para in s.split('\n'):
            if not para:
                out.append(''); continue
            w = ''
            for word in para.split(' '):
                if len(w) + len(word) + 1 <= n:
                    w = (w + ' ' + word).strip()
                else:
                    if w:
                        out.append(w)
                    while len(word) > n:
                        out.append(word[:n]); word = word[n:]
                    w = word
            out.append(w)
        return out

    pages = []
    state = {'cur': [], 'y': PH - MT}

    def flush():
        if state['cur']:
            pages.append(state['cur']); state['cur'] = []

    def addline(kind, txt):
        lead = LEAD[kind]
        if state['y'] - lead < MB:
            flush(); state['y'] = PH - MT
        sz = SIZE.get(kind, 9); fnt = FONT.get(kind, '/F1'); col = COL.get(kind, '0 0 0')
        state['cur'].append('%s rg BT %s %.1f Tf 1 0 0 1 %.1f %.1f Tm (%s) Tj ET' % (
            col, fnt, sz, ML, state['y'] - sz, esc(txt)))
        state['y'] -= lead

    def addrule():
        if state['y'] - 11 < MB:
            flush(); state['y'] = PH - MT
        state['y'] -= 4
        state['cur'].append('0.7 0.72 0.78 RG 0.6 w %.1f %.1f m %.1f %.1f l S' % (ML, state['y'], PW - MRr, state['y']))
        state['y'] -= 7

    def addsp():
        if state['y'] - 7 < MB:
            flush(); state['y'] = PH - MT
        else:
            state['y'] -= 7

    addline('title', 'Acid Zero  -  Hardware & Porting Reference')
    addline('h2', 'Raspberry Pi 3B+ pentest handheld  -  for porting C/C++/Rust/Python/Flipper code')
    addrule()
    for ml in ['%s  (rev %s)' % (f['model'], f['rev']),
               '%s  kernel %s  %s' % (f['os'], f['kernel'], f['arch']),
               'generated %s' % stamp]:
        addline('m', ml)
    addsp()
    for kind, txt in B:
        if kind == 'rule':
            addrule()
        elif kind == 'sp':
            addsp()
        else:
            n = 105 if kind == 'm' else (78 if kind in ('title', 'h1', 'h2') else 95)
            for line in wrap(txt, n):
                addline(kind, line)
    flush()

    objs = []
    npages = len(pages)
    page_ids = [6 + i * 2 for i in range(npages)]
    cont_ids = [7 + i * 2 for i in range(npages)]
    objs.append((1, '<< /Type /Catalog /Pages 2 0 R >>'))
    objs.append((2, '<< /Type /Pages /Count %d /Kids [%s] >>' % (npages, ' '.join('%d 0 R' % p for p in page_ids))))
    objs.append((3, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'))
    objs.append((4, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>'))
    objs.append((5, '<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>'))
    res = '<< /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >>'
    for i in range(npages):
        objs.append((page_ids[i], '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources %s /Contents %d 0 R >>' % (res, cont_ids[i])))
        stream = '\n'.join(pages[i])
        ln = len(stream.encode('latin-1', 'replace'))
        objs.append((cont_ids[i], '<< /Length %d >>\nstream\n%s\nendstream' % (ln, stream)))
    objs.sort(key=lambda x: x[0])
    out = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'
    offs = {}
    for n, body in objs:
        offs[n] = len(out)
        out += ('%d 0 obj\n%s\nendobj\n' % (n, body)).encode('latin-1', 'replace')
    maxn = max(offs)
    xref_pos = len(out)
    out += ('xref\n0 %d\n' % (maxn + 1)).encode()
    out += b'0000000000 65535 f \n'
    for n in range(1, maxn + 1):
        out += (('%010d 00000 n \n' % offs[n]) if n in offs else '0000000000 00000 f \n').encode()
    out += ('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (maxn + 1, xref_pos)).encode()
    open(PDF_OUT, 'wb').write(out)
    return npages

def main():
    f = live()
    stamp = time.strftime('%Y-%m-%d %H:%M')
    B = content(f)
    emit_html(B, f, stamp)
    np = emit_pdf(B, f, stamp)
    print('HTML -> %s' % HTML_OUT)
    print('PDF  -> %s  (%d pages)' % (PDF_OUT, np))

if __name__ == '__main__':
    main()
