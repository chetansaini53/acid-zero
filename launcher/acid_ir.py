#!/usr/bin/env python3
"""
Acid Zero - IR serial client (Pi side).

Talks to the same ESP32 co-processor that owns the CC1101, over USB serial.
The ESP32 runs IRremoteESP8266 on GPIO14 (RX) / GPIO13 (TX); this module is the
Pi-side transport the launcher's IR app imports. Auto-detects the ESP32 by the
PING->PONG handshake (survives port renumbering). Mirrors acid_subghz.py.
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
_DEF_TIMEOUT = 2.0


class AcidIRError(RuntimeError):
    pass


class AcidIR:
    """Pi-side client for the Acid Zero ESP32 IR co-processor."""

    def __init__(self, port: Optional[str] = None, baud: int = BAUD):
        if serial is None:
            raise AcidIRError("pyserial not installed: %r" % (_IMPORT_ERR,))
        self._port = port
        self._baud = baud
        self._ser = None
        self._lock = threading.Lock()

    @staticmethod
    def candidate_ports():
        return sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))

    def _open(self, port: str):
        s = serial.Serial()
        s.port = port
        s.baudrate = self._baud
        s.timeout = 0.3
        s.dtr = False          # do not reset the ESP32 on open
        s.rts = False
        s.open()
        time.sleep(0.2)
        s.reset_input_buffer()
        return s

    def connect(self, probe_timeout: float = 1.2) -> str:
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
                # probe with IR_INFO: the IR ESP32 answers "IR_INFO ...", the CC1101
                # ESP32 answers "ERR unknown" -> we pick the IR one, never the radio.
                s.write(b"IR_INFO\n")
                end = time.time() + probe_timeout
                buf = ""
                while time.time() < end:
                    buf += s.read(128).decode("utf-8", "replace")
                    if "IR_INFO" in buf:
                        self._ser = s
                        self._port = p
                        return p
            except Exception as e:
                last = "probe %s: %s" % (p, e)
            try:
                s.close()
            except Exception:
                pass
        raise AcidIRError("ESP32 IR co-processor not found (%s)" % last)

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

    def cmd(self, line: str, expect: Optional[str] = None,
            timeout: float = _DEF_TIMEOUT) -> str:
        if not self.connected:
            raise AcidIRError("not connected")
        with self._lock:
            try:
                self._ser.reset_input_buffer()
                self._ser.write((line.strip() + "\n").encode("ascii", "replace"))
            except Exception as e:
                self._ser = None
                raise AcidIRError("write failed: %s" % e)
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
            return "IR_READY" in self.cmd("PING", expect="IR_READY", timeout=1.0)
        except AcidIRError:
            return False

    def info(self) -> str:
        return self.cmd("IR_INFO", expect="IR_INFO", timeout=1.5).strip()

    def capture(self, secs: int = 8) -> Optional[dict]:
        """Capture one IR press. Returns {protocol,address,command,freq,data} or None."""
        r = self.cmd("IR_RX %d" % secs, expect="IR_END", timeout=secs + 4)
        out = {"protocol": "", "address": 0, "command": 0,
               "freq": 38000, "data": []}
        got = False
        for ln in r.splitlines():
            ln = ln.strip()
            if ln.startswith("IR_PROTO"):
                got = True
                for tok in ln.split():
                    if tok.startswith("name="):
                        out["protocol"] = tok.split("=", 1)[1]
                    elif tok.startswith("addr="):
                        try: out["address"] = int(tok.split("=", 1)[1], 16)
                        except ValueError: pass
                    elif tok.startswith("cmd="):
                        try: out["command"] = int(tok.split("=", 1)[1], 16)
                        except ValueError: pass
            elif ln.startswith("IR_RAW"):
                got = True
                toks = ln.split()
                if len(toks) > 1 and toks[1].isdigit():
                    out["freq"] = int(toks[1])
                out["data"] = [int(x) for x in toks[2:] if x.lstrip('-').isdigit()]
            elif ln.startswith("IR_TIMEOUT"):
                return None
        return out if got and out["data"] else (out if got else None)

    def send_raw(self, freq: int, data, reps: int = 1) -> str:
        """Transmit a raw microsecond pulse list at `freq` Hz, `reps` times."""
        payload = ' '.join(str(int(x)) for x in data)
        return self.cmd("IR_TX_RAW %d %d %s" % (int(freq), int(reps), payload),
                        expect="IR_OK", timeout=8)


if __name__ == "__main__":
    ir = AcidIR()
    print("connecting...", flush=True)              # GUARD:EXEMPT - CLI self-test
    try:
        port = ir.connect()
    except AcidIRError as e:
        print("FAIL:", e)                           # GUARD:EXEMPT - CLI self-test
        raise SystemExit(1)
    print("connected :", port)                      # GUARD:EXEMPT - CLI self-test
    print("info      :", ir.info())                 # GUARD:EXEMPT - CLI self-test
    ir.close()
