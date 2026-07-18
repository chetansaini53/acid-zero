# Acid Zero plugin - "Modules": LIVE status of the ESP32 co-processor (CC1101 + IR),
# the USB GPS, and onboard/expansion buses. Probes query the real hardware and run in a
# background thread so the UI never blocks (serial probes take a few seconds).
# Educational / own-lab. Read-only probing.
import os, glob, subprocess, time, threading
try:
    import fcntl            # Linux-only; absent on dev machines (I2C probe just no-ops there)
except Exception:
    fcntl = None
try:
    import serial
except Exception:
    serial = None

META = {'name': 'Modules', 'icon': 'usb', 'color': (140, 155, 180)}
ESP32_PORT = '/dev/ttyUSB0'    # the CC1101 + IR co-processor (never probed as GPS)

_cache = {'rows': [], 'probing': False}
_lock = threading.Lock()


def _lsusb():
    try:
        return subprocess.run(['lsusb'], capture_output=True, timeout=3).stdout.decode('utf-8', 'replace').lower()
    except Exception:
        return ''


def _i2c_ack(bus, addr):
    # pure-python I2C presence probe: I2C_SLAVE then a 1-byte read.
    if fcntl is None:
        return False
    try:
        f = os.open('/dev/i2c-%d' % bus, os.O_RDWR)
        try:
            fcntl.ioctl(f, 0x0703, addr)   # I2C_SLAVE
            os.read(f, 1)                  # raises OSError if nothing ACKs
            return True
        finally:
            os.close(f)
    except Exception:
        return False


def _probe_esp32():
    """Query the ESP32 co-processor: alive (PONG), CC1101 present (VER), IR up (IR_INFO)."""
    r = {'esp32': False, 'cc1101': False, 'ir': False}
    if serial is None or not os.path.exists(ESP32_PORT):
        return r
    s = None
    try:
        s = serial.Serial()
        s.port = ESP32_PORT; s.baudrate = 115200; s.timeout = 1
        s.dtr = False; s.rts = False        # do NOT reset the ESP32 on open
        s.open()
        time.sleep(0.3); s.reset_input_buffer()

        def cmd(c, wait=1.0):
            s.reset_input_buffer(); s.write((c + '\n').encode()); time.sleep(wait)
            return s.read(3000).decode('utf-8', 'replace')

        if 'PONG' in cmd('PING'):
            r['esp32'] = True
        if 'present=YES' in cmd('VER', 1.2):
            r['cc1101'] = True
        if 'IR_INFO tx=' in cmd('IR_INFO'):
            r['ir'] = True
    except Exception:
        pass
    finally:
        try:
            if s:
                s.close()
        except Exception:
            pass
    return r


def _probe_gps():
    """Probe the USB GPS (ttyACM*/ttyUSB[1+], never the ESP32 on ttyUSB0) for NMEA + fix."""
    r = {'gps': False, 'fix': False, 'sats': 0}
    if serial is None:
        return r
    for port in sorted(glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')):
        if port == ESP32_PORT:
            continue
        s = None
        try:
            s = serial.Serial(port, 9600, timeout=0.5)
            end = time.time() + 3
            while time.time() < end:
                ln = s.readline().decode('ascii', 'replace').strip()
                if ln.startswith('$') and ln[3:6] in ('GGA', 'RMC', 'GSV', 'GSA', 'VTG', 'GLL', 'TXT'):
                    r['gps'] = True
                    if ln[3:6] == 'GGA':
                        f = ln.split(',')
                        if len(f) > 7:
                            if f[6] not in ('', '0'):
                                r['fix'] = True
                            try:
                                r['sats'] = int(f[7])
                            except ValueError:
                                pass
        except Exception:
            pass
        finally:
            try:
                if s:
                    s.close()
            except Exception:
                pass
        if r['gps']:
            break
    return r


def scan():
    usb = _lsusb()
    wlans = [w for w in os.listdir('/sys/class/net') if w.startswith('wlan')]
    esp = _probe_esp32()
    gps = _probe_gps()
    rows = []
    # --- ESP32 co-processor (CC1101 + IR) - the stuff the user asked to see live ---
    rows.append(('ESP32 co-proc', 'on' if esp['esp32'] else 'off', ESP32_PORT + ' @115200'))
    if esp['cc1101']:
        rows.append(('CC1101  Sub-GHz', 'det', 'via ESP32 - chip 0x14 present'))
    elif esp['esp32']:
        rows.append(('CC1101  Sub-GHz', 'off', 'ESP32 up, chip not detected'))
    else:
        rows.append(('CC1101  Sub-GHz', 'bus', 'ESP32 co-proc offline'))
    if esp['ir']:
        rows.append(('IR  TX / RX', 'on', 'via ESP32 - GPIO13 TX / GPIO14 RX'))
    elif esp['esp32']:
        rows.append(('IR  TX / RX', 'off', 'ESP32 up, IR not responding'))
    else:
        rows.append(('IR  TX / RX', 'bus', 'ESP32 co-proc offline'))
    # --- USB GPS ---
    if gps['fix']:
        rows.append(('GPS  u-blox', 'on', 'FIX - %d satellites' % gps['sats']))
    elif gps['gps']:
        rows.append(('GPS  u-blox', 'rdy', 'streaming - acquiring fix (%d sats)' % gps['sats']))
    else:
        rows.append(('GPS  u-blox', 'bus', 'not detected on USB'))
    # --- onboard / expansion ---
    rows.append(('WiFi radios', 'on', '%d adapters (2.4/5GHz)' % len(wlans)))
    rows.append(('Bluetooth LE', 'on' if glob.glob('/sys/class/bluetooth/hci*') else 'off', 'hci0 (built-in)'))
    if _i2c_ack(1, 0x24):
        rows.append(('PN532  NFC / RFID', 'det', 'I2C-1 @0x24'))
    else:
        rows.append(('PN532  NFC / RFID', 'rdy' if os.path.exists('/dev/i2c-1') else 'bus', 'I2C-1 @0x24'))
    rows.append(('RTL-SDR', 'det' if '0bda:2838' in usb else 'rdy', 'USB host'))
    return rows


def _bg_scan(ctx):
    try:
        rows = scan()
    except Exception:
        rows = []
    with _lock:
        _cache['rows'] = rows
        _cache['probing'] = False
    try:
        ctx.mark_dirty()
    except Exception:
        pass


def on_enter(ctx):
    with _lock:
        _cache['probing'] = True
    threading.Thread(target=_bg_scan, args=(ctx,), daemon=True).start()
    ctx.mark_dirty()


def draw(d, ctx):
    ctx.topbar(d, 'MODULES')
    ctx.rr(d, (330, 4, 410, 24), outline=ctx.ACC, w=1, r=5)
    ctx.ct(d, 370, 14, 'rescan', ctx.F_SM, ctx.ACC)
    with _lock:
        rows = list(_cache['rows'])
        probing = _cache['probing']
    if probing and not rows:
        ctx.ct(d, 240, 160, 'probing hardware...', ctx.F_NM, ctx.ACC)
        ctx.ct(d, 240, 184, 'querying ESP32 (CC1101 + IR) and GPS', ctx.F_SM, ctx.DIM)
        return
    COL = {'on': (30, 200, 121), 'det': (30, 200, 121), 'rdy': (235, 180, 40), 'bus': (120, 130, 150), 'off': (235, 80, 80)}
    LBL = {'on': 'ACTIVE', 'det': 'DETECTED', 'rdy': 'READY', 'bus': 'OFFLINE', 'off': 'OFF'}
    y = 33
    for name, st, detail in rows[:8]:
        c = COL.get(st, (150, 150, 150))
        d.ellipse((16, y + 5, 26, y + 15), fill=c)
        ctx.lt(d, 36, y, name, ctx.F_NM, ctx.FG)
        ctx.lt(d, 36, y + 15, detail, ctx.F_TINY, ctx.DIM)
        ctx.ct(d, 428, y + 9, LBL.get(st, st), ctx.F_SM, c)
        y += 32
    ctx.lt(d, 16, ctx.H - 9, 'live status - tap rescan to refresh', ctx.F_TINY, ctx.DIM)


def handle_touch(tx, ty, ctx):
    if ty <= 26 and 326 <= tx <= 414 and ctx.debounce(0.5):
        on_enter(ctx)
