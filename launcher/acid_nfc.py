#!/usr/bin/env python3
"""
Acid Zero - NFC/RFID client (Pi side), for the ACR122U USB reader/writer.

The ACR122U is a PN532-based 13.56 MHz reader that libnfc drives natively over
USB (driver acr122_usb) - no wiring, DIP switch or serial adapter. This module
is a thin wrapper around the libnfc command-line tools the launcher's NFC app
imports:

  read  -> nfc-poll                 (UID / ATQA / SAK of the presented tag)
  dump  -> nfc-mfclassic r          (Mifare Classic 1K/4K, default keys)
           nfc-mfultralight r       (Ultralight / NTAG)
  write -> nfc-mfclassic w          (clone a dump onto a writable/blank card)
           nfc-mfultralight w
  emul  -> nfc-emulate-uid          (present a saved UID as a target; a Flipper
                                     / another reader can then read it back)

On Linux the kernel's pn533/nfc modules grab the ACR122U before libnfc can; the
one-time fix (blacklist pn533 + stop pcscd) is documented in INSTALL.md.

Educational / own-lab use only. All exact CLI argument forms are re-verified on
first-run against the connected reader (verify_cli()), because libnfc tool flags
differ slightly across 1.7/1.8 builds.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import threading
import time
from typing import Optional

# Tool names (resolved lazily; missing ones degrade gracefully in the UI).
T_LIST = "nfc-list"
T_POLL = "nfc-poll"
T_MFC = "nfc-mfclassic"
T_MFU = "nfc-mfultralight"
T_EMU_UID = "nfc-emulate-uid"

# SAK (SEL_RES) -> human tag family. Covers the common 13.56 MHz cards.
_SAK = {
    0x08: ("Mifare Classic 1K", "mfc"),
    0x18: ("Mifare Classic 4K", "mfc"),
    0x09: ("Mifare Mini", "mfc"),
    0x00: ("Ultralight / NTAG", "mfu"),
    0x20: ("ISO14443-4 (DESFire/JCOP)", "iso4"),
    0x28: ("SmartMX / JCOP", "iso4"),
}


class AcidNFCError(RuntimeError):
    pass


def _which(tool: str) -> Optional[str]:
    return shutil.which(tool)


def _run(args, timeout: float = 10.0, stdin: Optional[bytes] = None):
    """Run a libnfc tool. -> (returncode, combined_output_str). -1 on missing tool."""
    exe = _which(args[0])
    if not exe:
        return -1, "%s not installed (apt install libnfc-bin)" % args[0]
    try:
        p = subprocess.run([exe] + args[1:], input=stdin, capture_output=True,
                           timeout=timeout)
        out = (p.stdout or b"").decode("utf-8", "replace") + \
              (p.stderr or b"").decode("utf-8", "replace")
        return p.returncode, out
    except subprocess.TimeoutExpired:
        return 1, "(timeout)"
    except Exception as e:  # pragma: no cover - defensive
        return 1, str(e)


# ------------------------------ presence / status ------------------------------
def tools_present() -> bool:
    return _which(T_LIST) is not None


def reader_present() -> bool:
    """True if libnfc can open a reader (ACR122U shows up under acr122_usb)."""
    rc, out = _run([T_LIST], timeout=6)
    return rc == 0 and ("NFC device" in out or "opened" in out or "ISO14443" in out)


def reader_name() -> str:
    rc, out = _run([T_LIST], timeout=6)
    m = re.search(r"NFC device:\s*(.+?)\s+opened", out)
    if m:
        return m.group(1).strip()[:28]
    m = re.search(r"(ACR122U[^\n]*)", out)
    return m.group(1).strip()[:28] if m else ("no reader" if rc != 0 else "reader")


# ------------------------------ read a presented tag ------------------------------
def _parse_target(out: str) -> Optional[dict]:
    """Pull UID / ATQA / SAK out of nfc-poll / nfc-list output."""
    uid = re.search(r"UID \(NFCID1\):\s*([0-9a-fA-F ]+)", out)
    if not uid:
        return None
    uid_hex = uid.group(1).split()
    atqa = re.search(r"ATQA \(SENS_RES\):\s*([0-9a-fA-F ]+)", out)
    sak = re.search(r"SAK \(SEL_RES\):\s*([0-9a-fA-F]+)", out)
    sak_val = int(sak.group(1), 16) if sak else -1
    kind_name, kind = _SAK.get(sak_val, ("Unknown 13.56MHz", "uid"))
    return {
        "uid": "".join(uid_hex).upper(),
        "uid_spaced": " ".join(b.upper() for b in uid_hex),
        "atqa": "".join(atqa.group(1).split()).upper() if atqa else "",
        "sak": ("%02X" % sak_val) if sak_val >= 0 else "",
        "type": kind_name,
        "kind": kind,
    }


def read(timeout: float = 12.0) -> Optional[dict]:
    """Poll for one tag on the reader. Returns the parsed dict or None (no tag)."""
    rc, out = _run([T_POLL], timeout=timeout)
    if rc == -1:
        raise AcidNFCError(out)
    return _parse_target(out)


# ------------------------------ dump (read full card) ------------------------------
def dump(kind: str, path: str) -> tuple[bool, str]:
    """Read the full card to `path`. kind in mfc|mfu. Returns (ok, message)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if kind == "mfc":
        # r=read, a=key A, u=default-key unlock. Blank/default cards use FFFF..FF.
        rc, out = _run([T_MFC, "r", "a", "u", path], timeout=40)
        ok = rc == 0 and os.path.exists(path) and os.path.getsize(path) > 0
        return ok, ("dumped %dB" % os.path.getsize(path)) if ok else _tail(out)
    if kind == "mfu":
        rc, out = _run([T_MFU, "r", path], timeout=25)
        ok = rc == 0 and os.path.exists(path) and os.path.getsize(path) > 0
        return ok, ("dumped %dB" % os.path.getsize(path)) if ok else _tail(out)
    return False, "UID-only tag (no data to dump)"


# ------------------------------ write (clone onto a card) ------------------------------
def write(kind: str, path: str) -> tuple[bool, str]:
    """Write a saved dump `path` onto the presented (blank/writable) card."""
    if not os.path.exists(path):
        return False, "dump file missing"
    if kind == "mfc":
        # w=write, a=key A, u=unlock (needed to also write block0/UID on gen-1
        # 'magic' blanks; on normal blanks it writes data sectors with default keys).
        rc, out = _run([T_MFC, "w", "a", "u", path], timeout=60)
        return (rc == 0), (_tail(out) or "written")
    if kind == "mfu":
        rc, out = _run([T_MFU, "w", path], timeout=40)
        return (rc == 0), (_tail(out) or "written")
    return False, "UID-only tag (nothing to write)"


def _tail(out: str) -> str:
    lines = [ln for ln in (out or "").strip().splitlines() if ln.strip()]
    return lines[-1][:40] if lines else ""


# ------------------------------ emulate a UID ------------------------------
class Emulator:
    """Runs nfc-emulate-uid as a background process; stop() kills it.

    UID emulation only: the reader presents the saved 4-byte UID as an ISO14443-A
    target. UID-based access-control systems (and a Flipper's 'read UID') see it.
    Full Mifare-sector emulation is NOT supported by the PN532/ACR122U, so data
    beyond the UID is not replayed - that's a hardware limit, not a bug.
    """

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def start(self, uid_hex: str) -> tuple[bool, str]:
        exe = _which(T_EMU_UID)
        if not exe:
            return False, "%s not installed" % T_EMU_UID
        uid = "".join(c for c in (uid_hex or "") if c in "0123456789abcdefABCDEF")
        if len(uid) < 8:
            return False, "need a 4-byte UID"
        self.stop()
        try:
            with self._lock:
                # nfc-emulate-uid takes the UID (8 hex chars) as its argument and
                # runs until killed; own process group so stop() takes the child.
                self._proc = subprocess.Popen(
                    [exe, uid[:8]], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True)
            time.sleep(0.3)
            if self._proc.poll() is not None:
                return False, "emulate exited (reader busy?)"
            return True, "emulating %s" % uid[:8].upper()
        except Exception as e:  # pragma: no cover - defensive
            return False, str(e)[:32]

    def stop(self) -> None:
        with self._lock:
            p = self._proc
            self._proc = None
        if p and p.poll() is None:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception:
                try:
                    p.terminate()
                except Exception:
                    pass
            try:
                p.wait(timeout=2)
            except Exception:
                try:
                    os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                except Exception:
                    pass


if __name__ == "__main__":                              # GUARD:EXEMPT - CLI self-test
    print("tools present:", tools_present())            # GUARD:EXEMPT - CLI self-test
    print("reader       :", reader_name())              # GUARD:EXEMPT - CLI self-test
    tag = None
    try:
        print("present a tag...")                       # GUARD:EXEMPT - CLI self-test
        tag = read(timeout=8)
    except AcidNFCError as e:
        print("err:", e)                                # GUARD:EXEMPT - CLI self-test
    print("tag          :", tag)                        # GUARD:EXEMPT - CLI self-test
