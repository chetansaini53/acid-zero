# Acid Zero - BadUSB co-processor (Raspberry Pi Pico 2 W, CircuitPython) - AP MODE
# ---------------------------------------------------------------------------
# The Pico presents itself as a USB HID keyboard to the TARGET it is plugged
# into, AND hosts its OWN WiFi access point (gateway 192.168.4.1). It needs NO
# external WiFi, so it works ANYWHERE - home, the field, a client site - with no
# per-location credentials. The Pi (Acid Zero) joins this AP on a dedicated
# adapter and sends a Flipper-compatible DuckyScript payload to 192.168.4.1:1337;
# this firmware types it into the target. A self-contained WiFi Rubber Ducky.
#
# Flipper/Hak5 DuckyScript supported: REM, STRING, STRINGLN, DELAY, DEFAULT_DELAY,
# REPEAT, ID (ignored), modifier combos (CTRL/ALT/SHIFT/GUI/WINDOWS + key, incl.
# hyphenated CTRL-ALT-DEL), and all the named keys (ENTER, TAB, ESC, arrows,
# F1-F12, HOME/END/PAGEUP/PAGEDOWN, DELETE, etc.).
#
# Setup: copy this file as code.py to the CIRCUITPY drive, copy the `adafruit_hid`
# library folder into CIRCUITPY/lib/. The AP SSID/password are optional overrides
# in settings.toml (ACIDZERO_AP_SSID / ACIDZERO_AP_PASSWORD); see settings.toml.example.
#
# AUTHORIZED USE ONLY - inject keystrokes only into machines you own or are
# explicitly authorized to test. Educational / own-lab. See ../../ETHICS.md.
import time
import os
import wifi
import socketpool
import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.keycode import Keycode

# The Pico hosts its own WPA2 AP (gateway 192.168.4.1). Override in settings.toml.
AP_SSID = os.getenv('ACIDZERO_AP_SSID') or 'AcidZero-Duck'
AP_PASSWORD = os.getenv('ACIDZERO_AP_PASSWORD') or 'acidzero1337'   # WPA2 needs >= 8 chars
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


def _start_ap():
    # Host our own WPA2 access point. The CYW43 radio can fail the first start_ap
    # after a cold boot (same transient class as a station connect), so retry.
    if len(AP_PASSWORD) < 8:
        raise RuntimeError('ACIDZERO_AP_PASSWORD must be at least 8 chars (WPA2)')
    # Clean radio state first: drop any station connection or prior AP so the
    # CYW43 starts the AP from a known state (a hot station->AP switch flakes).
    for _fn in ('stop_station', 'stop_ap'):
        try:
            getattr(wifi.radio, _fn)()
        except Exception:
            pass
    time.sleep(0.5)
    last = None
    for attempt in range(1, 8):
        try:
            print('acidducky: starting AP "%s" (attempt %d)' % (AP_SSID, attempt))
            wifi.radio.start_ap(ssid=AP_SSID, password=AP_PASSWORD)
            try:
                wifi.radio.start_dhcp_ap()      # hand out leases to clients that ask
            except Exception as e:
                print('acidducky: dhcp-ap note (client can use static IP):', e)
            print('acidducky: AP up at', wifi.radio.ipv4_address_ap)
            return
        except Exception as e:
            last = e
            print('acidducky: AP start attempt %d failed - %s' % (attempt, e))
            time.sleep(2)
    raise RuntimeError('AP start failed after 5 attempts: %s' % last)


def main():
    _start_ap()
    pool = socketpool.SocketPool(wifi.radio)
    sock = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
    sock.setsockopt(pool.SOL_SOCKET, pool.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', PORT))
    sock.listen(1)
    print('acidducky: BadUSB server up on %s:%d (AP "%s")' % (wifi.radio.ipv4_address_ap, PORT, AP_SSID))

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
