#!/usr/bin/env python3
"""
Acid Zero - GPS serial client (Pi side).

Reads NMEA-0183 sentences from either a bare TTL GPS module wired to the Pi's
own GPIO UART (NEO-6M/7M class, via /dev/serial0) or a USB GPS dongle
(u-blox VK-162/VK-172 class, /dev/ttyUSB*|ttyACM*) - candidate_ports() checks
for whichever is actually present. Auto-detects the exact port by probing
candidates for valid NMEA checksums (GPS free-streams sentences with no
command needed, unlike the ESP32 co-processors which need PING/PONG). Mirrors
acid_subghz.py / acid_ir.py in structure: a small class, a background reader
owns the port, callers poll the latest fix.
"""
from __future__ import annotations

import glob
import os
import threading
import time
from typing import Optional

try:
    import serial  # pyserial
except Exception as _e:  # pragma: no cover
    serial = None
    _IMPORT_ERR = _e

BAUD_CANDIDATES = (9600, 4800, 38400)   # 9600 is the NMEA-0183 default; u-blox often ships at 9600
_DEF_TIMEOUT = 1.0


class GpsError(RuntimeError):
    pass


def nmea_checksum_ok(line: str) -> bool:
    """Validate the trailing *HH XOR checksum of an NMEA sentence."""
    line = line.strip()
    if not line.startswith('$') or '*' not in line:
        return False
    body, _, chk = line[1:].partition('*')
    if len(chk) < 2:
        return False
    x = 0
    for c in body:
        x ^= ord(c)
    try:
        return x == int(chk[:2], 16)
    except ValueError:
        return False


def _nmea_to_deg(value: str, hemi: str) -> Optional[float]:
    """NMEA ddmm.mmmm (or dddmm.mmmm) + hemisphere letter -> signed decimal degrees.
    Returns None (fail-safe) on an invalid hemisphere letter or minutes >= 60,
    rather than silently emitting a bogus coordinate."""
    if not value or hemi not in ('N', 'S', 'E', 'W'):
        return None
    try:
        v = float(value)
    except ValueError:
        return None
    deg = int(v / 100)
    minutes = v - deg * 100
    if not (0.0 <= minutes < 60.0):
        return None
    dec = deg + minutes / 60.0
    if hemi in ('S', 'W'):
        dec = -dec
    return dec


def parse_gga(line: str) -> Optional[dict]:
    """$GPGGA/$GNGGA: fix quality, lat/lon, altitude, satellite count, HDOP."""
    if not nmea_checksum_ok(line):
        return None
    body = line.strip().split('*')[0]
    f = body.split(',')
    if len(f) < 10 or not f[0].endswith('GGA'):
        return None
    fix_q = int(f[6]) if f[6].isdigit() else 0
    lat = _nmea_to_deg(f[2], f[3])   # f[2]=lat ddmm.mmmm, f[3]=N/S
    lon = _nmea_to_deg(f[4], f[5])   # f[4]=lon dddmm.mmmm, f[5]=E/W
    try:
        sats = int(f[7]) if f[7] else 0
    except ValueError:
        sats = 0
    try:
        hdop = float(f[8]) if f[8] else None
    except ValueError:
        hdop = None
    try:
        alt = float(f[9]) if f[9] else None
    except ValueError:
        alt = None
    return {'fix_quality': fix_q, 'lat': lat, 'lon': lon, 'sats': sats,
            'hdop': hdop, 'alt_m': alt, 'time_utc': f[1] or None}


def parse_rmc(line: str) -> Optional[dict]:
    """$GPRMC/$GNRMC: validity (A/V), lat/lon, speed (knots), course, date."""
    if not nmea_checksum_ok(line):
        return None
    body = line.strip().split('*')[0]
    f = body.split(',')
    if len(f) < 10 or not f[0].endswith('RMC'):
        return None
    valid = (f[2] == 'A')
    lat = _nmea_to_deg(f[3], f[4])
    lon = _nmea_to_deg(f[5], f[6])
    try:
        speed_kn = float(f[7]) if f[7] else None
    except ValueError:
        speed_kn = None
    try:
        course = float(f[8]) if f[8] else None
    except ValueError:
        course = None
    return {'valid': valid, 'lat': lat, 'lon': lon, 'speed_kn': speed_kn,
            'course': course, 'time_utc': f[1] or None, 'date': f[9] or None}


class Gps:
    """Pi-side GPS reader: auto-detects the port, parses NMEA in a daemon
    thread, exposes the latest fix via .fix()."""

    def __init__(self, port: Optional[str] = None):
        if serial is None:
            raise GpsError("pyserial not installed: %r" % (_IMPORT_ERR,))
        self._port = port
        self._ser = None
        self._lock = threading.Lock()
        self._fix = {'lat': None, 'lon': None, 'fix_quality': 0, 'sats': 0,
                     'hdop': None, 'alt_m': None, 'time_utc': None, 'updated': 0.0}
        self._stop = False

    @staticmethod
    def candidate_ports():
        """Auto-detect whichever GPS is actually present: a bare TTL module
        wired to the Pi's own GPIO UART (NEO-6M/7M class, via /dev/serial0 -
        the Raspberry Pi OS symlink to whichever UART is exposed on GPIO14/15,
        falling back to the raw device names on boards without that symlink)
        OR a USB GPS dongle (VK-162/VK-172 class, /dev/ttyUSB*|ttyACM*)."""
        onboard = [p for p in ('/dev/serial0', '/dev/ttyAMA0', '/dev/ttyS0') if os.path.exists(p)]
        usb = sorted(glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*'))
        seen, out = set(), []
        for p in onboard + usb:                       # onboard UART checked first
            rp = os.path.realpath(p)
            if rp not in seen:
                seen.add(rp); out.append(p)
        return out

    def _looks_like_nmea(self, port: str, baud: int) -> bool:
        try:
            s = serial.Serial(port, baudrate=baud, timeout=0.3)
        except Exception:
            return False
        try:
            for _ in range(6):
                raw = s.readline().decode('ascii', 'replace').strip()
                # require an actual GPS sentence type (GGA/RMC), not just checksum-valid
                # framing - a co-processor emitting unrelated "$..."-prefixed text on the
                # same USB-serial pool would otherwise pass a bare checksum check.
                if raw.startswith('$') and nmea_checksum_ok(raw) and raw[1:6].endswith(('GGA', 'RMC')):
                    return True
            return False
        finally:
            s.close()

    def connect(self) -> str:
        """Probe candidate ports/bauds for valid NMEA; opens the winner."""
        ports = [self._port] if self._port else self.candidate_ports()
        for p in ports:
            if not p:
                continue
            for baud in BAUD_CANDIDATES:
                if self._looks_like_nmea(p, baud):
                    self._ser = serial.Serial(p, baudrate=baud, timeout=1.0)
                    self._port = p
                    return p
        raise GpsError('no GPS found (checked %s)' % (ports or 'no serial0/ttyUSB*/ttyACM* candidates'))

    @property
    def connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def fix(self) -> dict:
        """Return a copy of the latest known fix (lat/lon None until a fix)."""
        with self._lock:
            return dict(self._fix)

    def has_fix(self, max_age_s: float = 10.0) -> bool:
        f = self.fix()
        return (f['lat'] is not None and f['lon'] is not None
                and f['fix_quality'] > 0 and (time.time() - f['updated']) <= max_age_s)

    def _apply(self, parsed: dict, kind: str):
        with self._lock:
            if kind == 'gga':
                if parsed['lat'] is not None:
                    self._fix['lat'] = parsed['lat']
                    self._fix['lon'] = parsed['lon']
                self._fix['fix_quality'] = parsed['fix_quality']
                self._fix['sats'] = parsed['sats']
                self._fix['hdop'] = parsed['hdop']
                self._fix['alt_m'] = parsed['alt_m']
                self._fix['time_utc'] = parsed['time_utc']
                self._fix['updated'] = time.time()
            elif kind == 'rmc' and parsed['valid'] and parsed['lat'] is not None:
                self._fix['lat'] = parsed['lat']
                self._fix['lon'] = parsed['lon']
                self._fix['time_utc'] = parsed['time_utc']
                self._fix['updated'] = time.time()

    def _reader_loop(self):
        while not self._stop:
            try:
                raw = self._ser.readline().decode('ascii', 'replace').strip()
            except Exception:
                time.sleep(0.5)
                continue
            if not raw.startswith('$'):
                continue
            g = parse_gga(raw)
            if g:
                self._apply(g, 'gga')
                continue
            r = parse_rmc(raw)
            if r:
                self._apply(r, 'rmc')

    def start(self):
        """Connect (if needed) and start the background NMEA reader thread."""
        if not self.connected:
            self.connect()
        threading.Thread(target=self._reader_loop, daemon=True).start()

    def close(self):
        self._stop = True
        try:
            if self._ser is not None:
                self._ser.close()
        except Exception:
            pass
        self._ser = None


if __name__ == '__main__':
    g = Gps()
    print('connecting...', flush=True)              # GUARD:EXEMPT - CLI self-test
    try:
        port = g.connect()
    except GpsError as e:
        print('FAIL:', e)                           # GUARD:EXEMPT - CLI self-test
        raise SystemExit(1)
    print('connected :', port)                      # GUARD:EXEMPT - CLI self-test
    g.start()
    for _ in range(30):
        time.sleep(1)
        print('fix:', g.fix())                      # GUARD:EXEMPT - CLI self-test
        if g.has_fix():
            break
    g.close()
