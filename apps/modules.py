# Acid Zero plugin - "Modules": auto-detect expansion hardware on the I2C / SPI / UART / USB
# buses and show status. Foundation for plug-and-play: wire a module and its app activates.
# Educational / own-lab. Read-only bus probing.
import os, glob, subprocess, fcntl

META = {'name': 'Modules', 'icon': 'usb', 'color': (140, 155, 180)}
_cache = {'rows': []}

def _lsusb():
    try:
        return subprocess.run(['lsusb'], capture_output=True, timeout=3).stdout.decode('utf-8', 'replace').lower()
    except Exception:
        return ''

def _i2c_ack(bus, addr):
    # pure-python I2C presence probe (no i2c-tools dep): I2C_SLAVE then a 1-byte read.
    try:
        f = os.open('/dev/i2c-%d' % bus, os.O_RDWR)
        try:
            fcntl.ioctl(f, 0x0703, addr)   # I2C_SLAVE
            os.read(f, 1)                  # raises OSError if no device ACKs
            return True
        finally:
            os.close(f)
    except Exception:
        return False

def scan():
    usb = _lsusb()
    wlans = [w for w in os.listdir('/sys/class/net') if w.startswith('wlan')]
    rows = []
    # --- onboard / already-active ---
    rows.append(('WiFi radios', 'on', '%d adapters (2.4/5GHz)' % len(wlans)))
    rows.append(('Bluetooth LE', 'on' if glob.glob('/sys/class/bluetooth/hci*') else 'off', 'hci0 (built-in)'))
    # --- expansion modules (plug-and-play) ---
    if _i2c_ack(1, 0x24):
        rows.append(('PN532  NFC / RFID', 'det', 'I2C-1 @0x24'))
    else:
        rows.append(('PN532  NFC / RFID', 'rdy' if os.path.exists('/dev/i2c-1') else 'bus', 'I2C-1 @0x24'))
    rows.append(('CC1101  Sub-GHz', 'det' if glob.glob('/dev/spidev1.*') else 'bus', 'SPI1 (dtoverlay=spi1-1cs)'))
    rows.append(('CH9329  BadUSB HID', 'rdy' if os.path.exists('/dev/ttyS0') else 'bus', 'UART ttyS0 (GPIO14/15)'))
    rows.append(('RTL-SDR', 'det' if '0bda:2838' in usb else 'rdy', 'USB host'))
    return rows

def on_enter(ctx):
    _cache['rows'] = scan(); ctx.mark_dirty()

def draw(d, ctx):
    ctx.topbar(d, 'MODULES')
    rows = _cache['rows'] or scan()
    COL = {'on': (30, 200, 121), 'det': (30, 200, 121), 'rdy': (235, 180, 40), 'bus': (120, 130, 150), 'off': (235, 80, 80)}
    LBL = {'on': 'ACTIVE', 'det': 'DETECTED', 'rdy': 'READY', 'bus': 'WIRE/ENABLE', 'off': 'OFF'}
    y = 38
    for name, st, bus in rows:
        c = COL.get(st, (150, 150, 150))
        d.ellipse((16, y + 5, 26, y + 15), fill=c)
        ctx.lt(d, 36, y, name, ctx.F_NM, ctx.FG)
        ctx.lt(d, 36, y + 15, bus, ctx.F_TINY, ctx.DIM)
        ctx.ct(d, 418, y + 9, LBL.get(st, st), ctx.F_SM, c)
        y += 34
    ctx.lt(d, 16, y + 6, 'plug a module -> its app auto-activates. detail: Hardware Info', ctx.F_TINY, ctx.DIM)
    ctx.rr(d, (330, 4, 410, 24), outline=ctx.ACC, w=1, r=5); ctx.ct(d, 370, 14, 'rescan', ctx.F_SM, ctx.ACC)

def handle_touch(tx, ty, ctx):
    if ty <= 26 and 326 <= tx <= 414 and ctx.debounce(0.5):
        _cache['rows'] = scan(); ctx.mark_dirty()
