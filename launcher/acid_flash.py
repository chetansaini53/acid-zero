#!/usr/bin/env python3
"""On-device firmware flasher for Acid Zero's co-processors.

Flash the ESP32 (CC1101 + IR) and the Pico 2 W (Bad USB) straight from the
handheld - no laptop needed.

  ESP32  - esptool over USB serial (fully automatic; auto-reset to bootloader).
           SCAN reads the chip id so you never flash the wrong board.
  Pico   - RP2350 BOOTSEL USB-drive + a CircuitPython .uf2 copy, then code.py +
           lib + your settings.toml. First flash needs the BOOTSEL button held.

Firmware ships in /usr/local/share/acid-firmware/. The Pico AP SSID/password
are entered at flash time (never ship the same default everywhere).
Educational / own-lab only.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import time

FW_DIR = '/usr/local/share/acid-firmware'
ESP32_BIN = os.path.join(FW_DIR, 'esp32-allinone.merged.bin')
PICO_UF2 = os.path.join(FW_DIR, 'circuitpython-pico2w.uf2')
PICO_SRC = os.path.join(FW_DIR, 'pico-badusb')   # code.py, boot.py, lib/
MNT = '/mnt/acidflash'

try:
    from acid_apcreds import DEFAULT_SSID, DEFAULT_PSK   # single source of truth
except Exception:
    DEFAULT_SSID = 'AcidZero-Duck'
    DEFAULT_PSK = 'acidzero1337'


def _stream(cmd, timeout=180, cb=None):
    """Run cmd, stream stdout lines to cb. -> (returncode, full_output)."""
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except FileNotFoundError:
        return 127, '%s not found' % cmd[0]
    except Exception as e:
        return 1, str(e)
    out, t0 = [], time.time()
    try:
        for line in p.stdout:
            out.append(line)
            if cb:
                s = line.strip()
                if s:
                    cb(s[:56])
            if time.time() - t0 > timeout:
                p.kill()
                return 1, ''.join(out) + '\n(timeout)'
        p.wait()
    except Exception as e:
        return 1, ''.join(out) + str(e)
    return p.returncode, ''.join(out)


# =============================== ESP32 (esptool) ===============================
def _esptool():
    # Prefer THIS interpreter: the launcher runs as root in a venv, and a bare
    # 'python3' under systemd's minimal PATH would miss a venv/system-installed
    # esptool that sys.executable can see.
    for c in ([sys.executable, '-m', 'esptool'], ['esptool.py'], ['esptool'], ['python3', '-m', 'esptool']):
        try:
            if subprocess.run(c + ['version'], capture_output=True, timeout=8).returncode == 0:
                return c
        except Exception:
            continue
    return None


def esp_port():
    """ESP32 dev boards use a CP210x/CH340 bridge -> /dev/ttyUSB* (the Pico and
    the GPS are /dev/ttyACM*, so ttyUSB isolates the ESP32)."""
    u = sorted(glob.glob('/dev/ttyUSB*'))
    return u[0] if u else None


def esp_scan():
    """-> (ok, headline, detail). Reads the chip id; rejects the wrong board."""
    base = _esptool()
    if not base:
        return False, 'esptool not installed', 'run: pip3 install esptool'
    port = esp_port()
    if not port:
        return False, 'no ESP32 (ttyUSB) found', 'plug the ESP32 in over USB'
    _rc, out = _stream(base + ['--port', port, 'flash_id'], timeout=30)
    # esptool v4 prints "Chip is X"; v5 prints "Chip type: X".
    chip = re.search(r'Chip (?:is|type:)\s*(\S+)', out)
    if not chip:
        last = (out.strip().splitlines() or ['no response'])[-1]
        return False, 'no ESP32 on %s' % port, last[:40]
    c = chip.group(1).upper()
    if 'ESP32' not in c or any(x in c for x in ('S3', 'S2', 'C3', 'C6', 'C2', 'H2')):
        return False, 'wrong board: %s' % chip.group(1), 'need the classic ESP32 co-processor'
    fl = re.search(r'flash size:\s*(\S+)', out, re.I)
    mac = re.search(r'MAC:\s*(\S+)', out)
    return True, chip.group(1), 'flash %s · MAC %s' % (fl.group(1) if fl else '?', mac.group(1) if mac else '?')


def esp_flash(cb):
    base = _esptool()
    if not base:
        return False, 'esptool not installed'
    port = esp_port()
    if not port:
        return False, 'no ESP32 port'
    if not os.path.exists(ESP32_BIN):
        return False, 'firmware missing: %s' % os.path.basename(ESP32_BIN)
    rc, out = _stream(base + ['--port', port, '--baud', '460800', 'write_flash', '0x0', ESP32_BIN],
                      timeout=200, cb=cb)
    o = out.lower()
    if rc == 0 and ('verified' in o or 'leaving' in o or 'hard reset' in o):
        return True, 'ESP32 flashed OK'
    return False, 'flash failed (rc=%d)' % rc


# ================================ Pico 2 W ================================
def _find_label(label):
    """(dev, mountpoint) of the block device whose FS label == label, else (None, None)."""
    try:
        out = subprocess.run(['lsblk', '-rno', 'NAME,LABEL,MOUNTPOINT'],
                             capture_output=True, text=True, timeout=6).stdout
        for ln in out.splitlines():
            p = ln.split(None, 2)
            if len(p) >= 2 and p[1] == label:
                return '/dev/' + p[0], (p[2] if len(p) >= 3 else '')
    except Exception:
        pass
    return None, None


def _mount(dev):
    if not dev:
        return None
    os.makedirs(MNT, exist_ok=True)
    subprocess.run(['mount', dev, MNT], capture_output=True, timeout=15)
    return MNT if os.path.ismount(MNT) else None


BOOTSEL_LABELS = ('RPI-RP2', 'RP2350', 'RPI-RP1')


def _bootsel_dev():
    """(dev, mnt) of a Pico BOOTSEL drive. RP2040 labels it 'RPI-RP2'; the RP2350
    (Pico 2 / Pico 2 W) labels it 'RP2350' - both must be recognised."""
    for lbl in BOOTSEL_LABELS:
        dev, mnt = _find_label(lbl)
        if dev:
            return dev, mnt
    return None, None


def pico_scan():
    """-> (state, detail). state in bootsel|circuitpy|none. (Only the CIRCUITPY
    label means CircuitPython - a bare /dev/ttyACM* could be the GPS/other CDC.)"""
    if _bootsel_dev()[0]:
        return 'bootsel', 'BOOTSEL mode - ready for a full flash'
    if _find_label('CIRCUITPY')[0]:
        return 'circuitpy', 'CircuitPython on board - code update ready'
    return 'none', 'hold BOOTSEL + plug the Pico in'


def _write_settings(cp, ssid, psk):
    # Defense in depth: even if upstream validate() was skipped (e.g. acid_apcreds
    # missing), never emit an unstartable WPA2 key or a value that breaks the
    # double-quoted TOML string. Fall back to the safe defaults on anything invalid.
    s = (ssid or '').strip()[:32] or DEFAULT_SSID
    p = (psk or '').strip()
    if not (8 <= len(p) <= 63):
        p = DEFAULT_PSK
    if any(ord(c) < 0x20 or ord(c) == 0x7f or c in '"\\' for c in s + p):
        s, p = DEFAULT_SSID, DEFAULT_PSK
    with open(os.path.join(cp, 'settings.toml'), 'w') as f:
        f.write('# Acid Zero BadUSB - Pico 2 W AP mode (set at flash time)\n')
        f.write('ACIDZERO_AP_SSID = "%s"\n' % s)
        f.write('ACIDZERO_AP_PASSWORD = "%s"\n' % p)


def _copy_code(cp, ssid, psk, cb):
    for f in ('code.py', 'boot.py'):
        s = os.path.join(PICO_SRC, f)
        if os.path.exists(s):
            shutil.copy(s, os.path.join(cp, f))
            cb('copied %s' % f)
    lib = os.path.join(PICO_SRC, 'lib')
    if os.path.isdir(lib):
        shutil.copytree(lib, os.path.join(cp, 'lib'), dirs_exist_ok=True)
        cb('copied lib/adafruit_hid')
    _write_settings(cp, ssid, psk)
    cb('wrote settings.toml (your AP creds)')
    subprocess.run(['sync'], timeout=10)
    if cp == MNT:   # release our own mount so the Pi never holds CIRCUITPY open
        subprocess.run(['umount', '-l', MNT], capture_output=True, timeout=10)


def pico_flash(ssid, psk, cb):
    state, _ = pico_scan()
    if state == 'bootsel':
        if not os.path.exists(PICO_UF2):
            return False, 'CircuitPython .uf2 missing in firmware dir'
        dev, mnt = _bootsel_dev()
        mp = mnt or _mount(dev)
        if not mp:
            return False, 'could not mount BOOTSEL drive'
        cb('flashing CircuitPython .uf2 ...')
        try:
            # The RP2350 bootloader flashes blocks as they arrive and RESETS itself
            # mid-write - so the copy is EXPECTED to error, and we must NOT sync (a
            # sync to the vanished device hangs in uninterruptible I/O). Fire+forget.
            shutil.copy(PICO_UF2, os.path.join(mp, 'fw.uf2'))
        except OSError:
            pass
        cb('CircuitPython flashed - waiting for reboot ...')
        for _ in range(40):
            time.sleep(1)
            if _find_label('CIRCUITPY')[0]:
                break
        dev, mnt = _find_label('CIRCUITPY')
        cp = mnt or _mount(dev)
        if not cp:
            return False, 'CIRCUITPY not seen after CP flash'
        _copy_code(cp, ssid, psk, cb)
        return True, 'Pico fully flashed (CircuitPython + Bad USB)'
    if state == 'circuitpy':
        dev, mnt = _find_label('CIRCUITPY')
        cp = mnt or _mount(dev)
        if not cp:
            return False, 'could not mount CIRCUITPY (hold BOOTSEL+replug for a full flash)'
        _copy_code(cp, ssid, psk, cb)
        return True, 'Pico code + settings updated'
    return False, 'Pico not in BOOTSEL - hold BOOTSEL + replug'
