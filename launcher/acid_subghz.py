#!/usr/bin/env python3
"""
Acid Zero - Sub-GHz serial client (Pi side).

Talks to the ESP32 co-processor (CC1101) over USB serial. The ESP32 owns the
radio; this module is the Pi-side transport the launcher's Sub-GHz app imports.

Auto-detects the ESP32 by probing /dev/ttyUSB* (and ACM*) for the PING->PONG
handshake, so it survives port renumbering across reboots. Single-command
request/response is serialised with a lock so concurrent UI threads are safe.
"""
from __future__ import annotations

import glob
import threading
import time
from typing import Optional

try:
    import serial  # pyserial
except Exception as _e:  # pragma: no cover
    serial = None
    _IMPORT_ERR = _e

BAUD = 115200
_DEF_TIMEOUT = 1.5

# CC1101 modulation profiles (must match the firmware PROFILES order/names)
PROFILES = ['AM_DEFAULT', 'AM_WIDE', 'AM_NARROW', 'FM_FSK']


class SubGhzError(RuntimeError):
    pass


class SubGhz:
    """Pi-side client for the Acid Zero ESP32 Sub-GHz co-processor."""

    def __init__(self, port: Optional[str] = None, baud: int = BAUD):
        if serial is None:
            raise SubGhzError("pyserial not installed: %r" % (_IMPORT_ERR,))
        self._port = port
        self._baud = baud
        self._ser = None
        self._lock = threading.Lock()

    # ---------------- connection ----------------
    @staticmethod
    def candidate_ports():
        return sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))

    def _open(self, port: str):
        s = serial.Serial()
        s.port = port
        s.baudrate = self._baud
        s.timeout = 0.3
        # keep DTR/RTS low so we do NOT reset the ESP32 on open
        s.dtr = False
        s.rts = False
        s.open()
        time.sleep(0.2)
        s.reset_input_buffer()
        return s

    def connect(self, probe_timeout: float = 1.2) -> str:
        """Find + open the ESP32. Returns the port, or raises SubGhzError."""
        ports = [self._port] if self._port else self.candidate_ports()
        last = "no ports"
        for p in ports:
            if not p:
                continue
            try:
                s = self._open(p)
            except Exception as e:
                last = "open %s: %s" % (p, e)
                continue
            try:
                s.write(b"PING\n")
                end = time.time() + probe_timeout
                buf = ""
                while time.time() < end:
                    buf += s.read(128).decode("utf-8", "replace")
                    if "PONG" in buf:
                        self._ser = s
                        self._port = p
                        return p
            except Exception as e:
                last = "probe %s: %s" % (p, e)
            try:
                s.close()
            except Exception:
                pass
        raise SubGhzError("ESP32 Sub-GHz not found (%s)" % last)

    def close(self) -> None:
        with self._lock:
            if self._ser is not None:
                try:
                    self._ser.close()
                finally:
                    self._ser = None

    @property
    def connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    # ---------------- low-level ----------------
    def cmd(self, line: str, expect: Optional[str] = None,
            timeout: float = _DEF_TIMEOUT) -> str:
        """Send one command line; collect the reply text until `expect` or timeout."""
        if not self.connected:
            raise SubGhzError("not connected")
        with self._lock:
            try:
                self._ser.reset_input_buffer()
                self._ser.write((line.strip() + "\n").encode("ascii", "replace"))
            except Exception as e:
                self._ser = None
                raise SubGhzError("write failed: %s" % e)
            end = time.time() + timeout
            buf = ""
            while time.time() < end:
                chunk = self._ser.read(256).decode("utf-8", "replace")
                if chunk:
                    buf += chunk
                    if expect and expect in buf:
                        break
            return buf

    # ---------------- high-level API ----------------
    def ping(self) -> bool:
        try:
            return "PONG" in self.cmd("PING", expect="PONG", timeout=1.0)
        except SubGhzError:
            return False

    def version(self) -> dict:
        r = self.cmd("VER", expect="VER ", timeout=1.5)
        out = {"present": "present=YES" in r, "raw": r.strip()}
        for tok in r.split():
            if tok.startswith("version="):
                out["version"] = tok.split("=", 1)[1]
            elif tok.startswith("partnum="):
                out["partnum"] = tok.split("=", 1)[1]
        return out

    def info(self) -> str:
        return self.cmd("INFO", expect="INFO", timeout=1.5).strip()

    def set_freq(self, mhz: float) -> str:
        return self.cmd("FREQ %.2f" % mhz, expect="FREQ", timeout=1.5).strip()

    def rssi(self) -> Optional[int]:
        r = self.cmd("RSSI", expect="dBm", timeout=1.5)
        try:
            return int(r.split("=")[-1].split("dBm")[0].strip())
        except Exception:
            return None

    def scan(self, timeout: float = 6.0):
        """Return [(mhz, rssi_dbm), ...] across the firmware's freq list."""
        r = self.cmd("SCAN", expect="SCAN done", timeout=timeout)
        out = []
        for ln in r.splitlines():
            if ln.startswith("SCAN ") and "rssi=" in ln:
                try:
                    mhz = float(ln.split()[1])
                    rs = int(ln.split("rssi=")[1].split("dBm")[0].strip())
                    out.append((mhz, rs))
                except Exception:
                    pass
        return out

    def analyze(self, timeout: float = 8.0):
        """Frequency Analyzer: sweep common sub-GHz freqs, find the strongest.

        Returns (peak_mhz, peak_rssi, rows) where rows = [(mhz, rssi), ...].
        """
        r = self.cmd("ANALYZE", expect="ANALYZE peak=", timeout=timeout)
        rows = []
        peak_f = None
        peak_r = None
        for ln in r.splitlines():
            ln = ln.strip()
            if ln.startswith("ANALYZE peak="):
                try:
                    peak_f = float(ln.split("peak=")[1].split()[0])
                    peak_r = int(ln.split("rssi=")[1].strip())
                except Exception:
                    pass
            elif ln.startswith("ANALYZE ") and "rssi=" in ln:
                try:
                    rows.append((float(ln.split()[1]),
                                 int(ln.split("rssi=")[1].strip())))
                except Exception:
                    pass
        return peak_f, peak_r, rows

    def capture(self, secs: int = 8):
        """OOK raw capture. Returns the list of pulse durations (us)."""
        r = self.cmd('CAPTURE %d' % secs, timeout=secs + 4)
        for ln in r.splitlines():
            if ln.strip().startswith('CAPDATA'):
                return [int(x) for x in ln.split()[1:] if x.lstrip('-').isdigit()]
        return []

    def load(self, pulses) -> str:
        """Send a saved pulse list to the ESP32 buffer for REPLAY."""
        return self.cmd('LOAD ' + ' '.join(str(int(x)) for x in pulses),
                        expect='LOAD n=', timeout=6)

    def replay(self, reps: int = 15) -> str:
        """Transmit the loaded/last-captured signal `reps` times."""
        return self.cmd('REPLAY %d' % reps, expect='REPLAY done', timeout=max(10, reps + 6))

    def set_profile(self, name: str) -> str:
        """Switch modulation profile (AM_DEFAULT / AM_WIDE / AM_NARROW / FM_FSK)."""
        return self.cmd('MOD ' + str(name), expect='MOD ', timeout=2.5)

    def set_config(self, freq=None, mod=None, drate=None, dev=None, rxbw=None, rssi=None) -> str:
        """Custom runtime override, e.g. set_config(freq=433.92, mod='AM_NARROW')."""
        parts = ['SET_CONFIG']
        if freq is not None:  parts += ['--freq', '%.2f' % freq]
        if mod is not None:   parts += ['--mod', str(mod)]
        if drate is not None: parts += ['--drate', '%.2f' % drate]
        if dev is not None:   parts += ['--dev', '%.2f' % dev]
        if rxbw is not None:  parts += ['--rxbw', '%.0f' % rxbw]
        if rssi is not None:  parts += ['--rssi', '%d' % int(rssi)]
        return self.cmd(' '.join(parts), expect='CONFIG ', timeout=3)

    def classify(self, timeout: float = 5.0) -> dict:
        """Heuristic: hold the remote ~3s; guesses ASK/OOK (AM) vs FSK (FM)."""
        r = self.cmd('CLASSIFY', expect='CLASSIFY rssi', timeout=timeout)
        out = {'raw': r.strip(), 'guess': '', 'span': None}
        for ln in r.splitlines():
            if ln.strip().startswith('CLASSIFY rssi'):
                out['raw'] = ln.strip()
                if '->' in ln:
                    out['guess'] = ln.split('->', 1)[1].strip()
                for tok in ln.split():
                    if tok.startswith('span='):
                        try: out['span'] = int(tok.split('=')[1])
                        except Exception: pass
        return out


if __name__ == "__main__":
    # CLI self-test harness (run directly). Library code above never prints.
    sg = SubGhz()
    print("connecting...", flush=True)              # GUARD:EXEMPT — CLI self-test
    try:
        port = sg.connect()
    except SubGhzError as e:
        print("FAIL:", e)                           # GUARD:EXEMPT — CLI self-test
        raise SystemExit(1)
    print("connected :", port)                      # GUARD:EXEMPT — CLI self-test
    print("ping      :", sg.ping())                 # GUARD:EXEMPT — CLI self-test
    print("version   :", sg.version())              # GUARD:EXEMPT — CLI self-test
    print("info      :", sg.info())                 # GUARD:EXEMPT — CLI self-test
    print("scan      :", sg.scan())                 # GUARD:EXEMPT — CLI self-test
    print("analyze   :", sg.analyze())              # GUARD:EXEMPT — CLI self-test
    sg.close()
    print("OK - Phase 1+2 serial client working")   # GUARD:EXEMPT — CLI self-test
