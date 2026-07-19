# Acid Zero - BadUSB co-processor (Raspberry Pi Pico 2 W, CircuitPython)
# ---------------------------------------------------------------------------
# The Pico presents itself as a USB HID keyboard to the TARGET it is plugged
# into, and joins your WiFi as `acidducky.local:1337`. The Pi (Acid Zero) sends
# a Flipper-compatible DuckyScript payload over WiFi; this firmware parses it and
# types it into the target. One board = a WiFi-controlled Rubber Ducky.
#
# Flipper/Hak5 DuckyScript supported: REM, STRING, STRINGLN, DELAY, DEFAULT_DELAY,
# REPEAT, ID (ignored), modifier combos (CTRL/ALT/SHIFT/GUI/WINDOWS + key, incl.
# hyphenated CTRL-ALT-DEL), and all the named keys (ENTER, TAB, ESC, arrows,
# F1-F12, HOME/END/PAGEUP/PAGEDOWN, DELETE, etc.).
#
# Setup: copy this file as code.py to the CIRCUITPY drive, copy the `adafruit_hid`
# library folder into CIRCUITPY/lib/, and put your WiFi creds in settings.toml
# (see settings.toml.example). See README.md.
#
# AUTHORIZED USE ONLY - inject keystrokes only into machines you own or are
# explicitly authorized to test. Educational / own-lab. See ../../ETHICS.md.
import time
import os
import wifi
import socketpool
import mdns
import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.keycode import Keycode

HOSTNAME = 'acidducky'      # reachable from the Pi at acidducky.local
PORT = 1337

kbd = Keyboard(usb_hid.devices)
layout = KeyboardLayoutUS(kbd)

# ---- DuckyScript named keys -> HID keycodes ----
KEYS = {
    'ENTER': Keycode.ENTER, 'RETURN': Keycode.ENTER,
    'ESC': Keycode.ESCAPE, 'ESCAPE': Keycode.ESCAPE,
    'TAB': Keycode.TAB, 'SPACE': Keycode.SPACEBAR, 'SPACEBAR': Keycode.SPACEBAR,
    'BACKSPACE': Keycode.BACKSPACE, 'BKSP': Keycode.BACKSPACE,
    'DELETE': Keycode.DELETE, 'DEL': Keycode.DELETE,
    'CAPSLOCK': Keycode.CAPS_LOCK, 'NUMLOCK': Keycode.KEYPAD_NUMLOCK,
    'SCROLLLOCK': Keycode.SCROLL_LOCK, 'INSERT': Keycode.INSERT,
    'HOME': Keycode.HOME, 'END': Keycode.END,
    'PAGEUP': Keycode.PAGE_UP, 'PAGEDOWN': Keycode.PAGE_DOWN,
    'UP': Keycode.UP_ARROW, 'UPARROW': Keycode.UP_ARROW,
    'DOWN': Keycode.DOWN_ARROW, 'DOWNARROW': Keycode.DOWN_ARROW,
    'LEFT': Keycode.LEFT_ARROW, 'LEFTARROW': Keycode.LEFT_ARROW,
    'RIGHT': Keycode.RIGHT_ARROW, 'RIGHTARROW': Keycode.RIGHT_ARROW,
    'PRINTSCREEN': Keycode.PRINT_SCREEN, 'PAUSE': Keycode.PAUSE, 'BREAK': Keycode.PAUSE,
    'MENU': Keycode.APPLICATION, 'APP': Keycode.APPLICATION,
    'F1': Keycode.F1, 'F2': Keycode.F2, 'F3': Keycode.F3, 'F4': Keycode.F4,
    'F5': Keycode.F5, 'F6': Keycode.F6, 'F7': Keycode.F7, 'F8': Keycode.F8,
    'F9': Keycode.F9, 'F10': Keycode.F10, 'F11': Keycode.F11, 'F12': Keycode.F12,
}
MODS = {
    'CTRL': Keycode.CONTROL, 'CONTROL': Keycode.CONTROL,
    'SHIFT': Keycode.SHIFT, 'ALT': Keycode.ALT, 'OPTION': Keycode.ALT,
    'GUI': Keycode.GUI, 'WINDOWS': Keycode.GUI, 'WIN': Keycode.GUI, 'COMMAND': Keycode.GUI,
}


def _press_combo(line):
    # a key / modifier-combo line: "GUI r", "CTRL ALT DELETE", "CTRL-ALT-DEL"
    codes = []
    for t in line.replace('-', ' ').split():
        tu = t.upper()
        if tu in MODS:
            codes.append(MODS[tu])
        elif tu in KEYS:
            codes.append(KEYS[tu])
        elif len(t) == 1:
            try:
                codes.extend(layout.keycodes(t))
            except Exception:
                pass
    if codes:
        for c in codes:
            kbd.press(c)
        time.sleep(0.02)
        kbd.release_all()


def _sleep_ms(arg):
    try:
        time.sleep(int(arg.strip()) / 1000.0)
    except Exception:
        pass


def run_line(line, state):
    if not line.strip():
        return
    first, _, rest = line.partition(' ')
    cmd = first.upper()
    if cmd == 'REM':
        return
    if cmd in ('STRING', 'STR'):
        layout.write(rest)
    elif cmd == 'STRINGLN':
        layout.write(rest)
        kbd.press(Keycode.ENTER); kbd.release_all()
    elif cmd == 'DELAY':
        _sleep_ms(rest)
    elif cmd in ('DEFAULTDELAY', 'DEFAULT_DELAY'):
        try:
            state['dd'] = int(rest.strip()) / 1000.0
        except Exception:
            pass
        return
    elif cmd == 'REPEAT':
        try:
            n = int(rest.strip())
            for _ in range(n):
                if state['last']:
                    run_line(state['last'], state)
                    if state['dd']:
                        time.sleep(state['dd'])
        except Exception:
            pass
        return
    elif cmd == 'ID':
        return   # USB VID/PID line - we're already enumerated; ignore
    elif cmd in MODS or cmd in KEYS:
        _press_combo(line)
    else:
        return   # unknown command - skip (Flipper behaviour)
    state['last'] = line


def run_ducky(script):
    state = {'dd': 0.0, 'last': None}
    n = 0
    for line in script.replace('\r', '').split('\n'):
        run_line(line, state)
        if state['dd']:
            time.sleep(state['dd'])
        n += 1
    return n


def _connect_wifi():
    ssid = os.getenv('CIRCUITPY_WIFI_SSID')
    pw = os.getenv('CIRCUITPY_WIFI_PASSWORD')
    if not ssid:
        raise RuntimeError('set CIRCUITPY_WIFI_SSID / _PASSWORD in settings.toml')
    # The Pico W CYW43 radio frequently fails the FIRST association after a cold
    # boot with a transient ConnectionError ("Unknown failure 1") even when the
    # SSID/password are correct. Retry a few times so one transient miss doesn't
    # crash the whole firmware on boot (proven: attempt 2 connects reliably).
    last = None
    for attempt in range(1, 9):
        try:
            print('acidducky: connecting to %s (attempt %d)' % (ssid, attempt))
            wifi.radio.connect(ssid, pw)
            print('acidducky: IP', wifi.radio.ipv4_address)
            return
        except Exception as e:
            last = e
            print('acidducky: wifi attempt %d failed - %s' % (attempt, e))
            time.sleep(2)
    raise RuntimeError('wifi connect failed after 8 attempts: %s' % last)


def main():
    _connect_wifi()
    server_obj = mdns.Server(wifi.radio)
    server_obj.hostname = HOSTNAME
    try:
        server_obj.advertise_service(service_type='_acidducky', protocol='_tcp', port=PORT)
    except Exception as e:
        print('acidducky: mDNS advertise failed (still reachable by IP):', e)

    pool = socketpool.SocketPool(wifi.radio)
    sock = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
    sock.setsockopt(pool.SOL_SOCKET, pool.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', PORT))
    sock.listen(1)
    print('acidducky: BadUSB server up on %s.local:%d' % (HOSTNAME, PORT))

    buf = bytearray(4096)
    while True:
        conn = None
        try:
            conn, addr = sock.accept()
            conn.settimeout(4)
            data = b''
            while True:
                try:
                    n = conn.recv_into(buf)
                except OSError:
                    break
                if not n:
                    break
                data += bytes(buf[:n])
                if data.endswith(b'\x00'):       # payload terminator
                    data = data[:-1]
                    break
            payload = data.decode('utf-8', 'replace')
            if payload.strip() == 'PING':
                conn.send(b'PONG acidducky\n')
            else:
                lines = run_ducky(payload)
                conn.send(('OK ran %d lines\n' % lines).encode())
        except Exception as e:
            print('acidducky: err', e)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass


main()
