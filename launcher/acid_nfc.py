#!/usr/bin/env python3
"""
Acid Zero - NFC/RFID client (Pi side), for the ACR122U USB reader/writer.

The ACR122U is a PN532-based 13.56 MHz reader that libnfc drives natively over
USB (driver acr122_usb) - no wiring, DIP switch or serial adapter. This module
is a thin wrapper around the libnfc command-line tools the launcher's NFC app
imports:

  read  -> nfc-list                 (UID / ATQA / SAK of the presented tag;
                                     Debian's libnfc-bin ships nfc-list, NOT the
                                     example tool nfc-poll, so read() polls
                                     nfc-list on a short loop until a tag appears)
  dump  -> nfc-mfclassic r a u      (Mifare Classic 1K/4K, default keys, any UID)
           nfc-mfultralight r       (Ultralight / NTAG)
  write -> nfc-mfclassic w a u      (clone a dump onto a writable/blank card)
           nfc-mfultralight w
  emul  -> nfc-emulate-uid          (present a saved UID as a target; a Flipper
                                     / another reader can then read it back - this
                                     example tool is NOT in libnfc-bin; it is built
                                     from the libnfc source in INSTALL.md, and the
                                     UI degrades gracefully when it is absent)

On Linux the kernel's pn533/nfc modules grab the ACR122U before libnfc can; the
one-time fix (blacklist pn533 + stop pcscd) is documented in INSTALL.md.

Educational / own-lab use only. The CLI argument forms above were verified
against libnfc 1.8.0 driving the real ACR122U (this build's nfc-mfclassic takes
the u|U any/specific-UID argument between the key type and the dump file).
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
# nfc-poll isn't shipped in Debian's libnfc-bin, so read() polls nfc-list instead.
# nfc-emulate-uid is a libnfc *example* tool (not packaged); built from source in
# INSTALL.md - when absent, the Emulator reports "not installed" cleanly.
T_LIST = "nfc-list"
T_MFC = "nfc-mfclassic"
T_MFU = "nfc-mfultralight"
T_EMU_UID = "nfc-emulate-uid"

# ---------------------------------------------------------------------------
# Tag identification + NDEF content. Tables verified against NXP AN10833 rev3.9,
# libnfc target-subr.c, Proxmark3 cmdhfmfu.c, ISO/IEC 7816-6 & 14443-3, and the
# NFC Forum Type-2 spec. SAK maps to a FAMILY; the exact product inside the
# Ultralight/NTAG (SAK 0x00) bucket is refined from the memory-dump size.
# ---------------------------------------------------------------------------

# First UID byte -> IC manufacturer (ISO/IEC 7816-6). Only meaningful for a 7- or
# 10-byte UID; a 4-byte UID carries no standardized manufacturer byte.
_MFR = {
    0x01: "Motorola", 0x02: "STMicroelectronics", 0x03: "Hitachi",
    0x04: "NXP Semiconductors", 0x05: "Infineon", 0x07: "Texas Instruments",
    0x08: "Fujitsu", 0x0E: "Samsung", 0x15: "Atmel/Microchip",
    0x16: "EM Microelectronic", 0x1A: "Sony (FeliCa)", 0x1D: "Shanghai Fudan",
    0x20: "Renesas", 0x28: "Ricoh", 0x2B: "Dallas/Maxim",
}

# SAK -> (product, family, category, kind). `category` drives the beginner copy +
# badge; `kind` drives the dump path: mfc=Classic, mfu=Ultralight/NTAG,
# iso4=secure (no default-key dump), uid=UID only. SAK 0x00 = the whole
# Ultralight/NTAG family (refined by dump size); SAK 0x20 refined by ATQA.
_TYPE = {
    "00": ("Ultralight / NTAG",           "MIFARE Ultralight / NTAG",  "nfc-tag",     "mfu"),
    "08": ("Mifare Classic 1K",           "MIFARE Classic",            "rfid-card",   "mfc"),
    "09": ("Mifare Classic Mini",         "MIFARE Classic",            "rfid-card",   "mfc"),
    "18": ("Mifare Classic 4K",           "MIFARE Classic",            "rfid-card",   "mfc"),
    "88": ("Mifare Classic 1K (clone)",   "MIFARE Classic-compatible", "rfid-card",   "mfc"),
    "98": ("Mifare Classic 4K (clone)",   "MIFARE Classic-compatible", "rfid-card",   "mfc"),
    "10": ("Mifare Plus 2K",              "MIFARE Plus (AES)",         "secure-card", "iso4"),
    "11": ("Mifare Plus 4K",              "MIFARE Plus (AES)",         "secure-card", "iso4"),
    "20": ("ISO 14443-4 smartcard",       "ISO 14443-4",               "other",       "iso4"),
    "28": ("JCOP (Classic 1K emul.)",     "SmartMX / JCOP",            "secure-card", "iso4"),
    "38": ("JCOP (Classic 4K emul.)",     "SmartMX / JCOP",            "secure-card", "iso4"),
}

# Product -> beginner-friendly memory description (user/usable memory).
_MEM = {
    "Mifare Classic Mini": "320 B (~224 B usable)",
    "Mifare Classic 1K": "1 KB (~752 B usable)",
    "Mifare Classic 4K": "4 KB (~3.4 KB usable)",
    "Mifare Classic 1K (clone)": "1 KB (~752 B usable)",
    "Mifare Classic 4K (clone)": "4 KB (~3.4 KB usable)",
    "Mifare Plus 2K": "2 KB (AES-encrypted)",
    "Mifare Plus 4K": "4 KB (AES-encrypted)",
    "DESFire / NTAG424 DNA": "2-8 KB (encrypted)",
}

# Ultralight/NTAG: nfc-mfultralight dump file size (bytes, header pages included)
# -> exact product + user-memory string. Unknown sizes fall back to a generic label.
_MFU_DUMP = {
    64:  ("Mifare Ultralight",   "48 B user memory"),
    80:  ("Ultralight EV1",      "48 B user memory"),
    164: ("Ultralight EV1",      "128 B user memory"),
    168: ("NTAG203",             "144 B user memory"),
    180: ("NTAG213",             "144 B user memory"),
    192: ("Ultralight C",        "144 B user memory (3DES)"),
    540: ("NTAG215",             "504 B user memory"),
    924: ("NTAG216",             "888 B user memory"),
}

# NFC Forum URI record identifier-code -> prefix (full 0x00..0x23 table).
_URI_PREFIXES = {
    0x00: "", 0x01: "http://www.", 0x02: "https://www.", 0x03: "http://",
    0x04: "https://", 0x05: "tel:", 0x06: "mailto:",
    0x07: "ftp://anonymous:anonymous@", 0x08: "ftp://ftp.", 0x09: "ftps://",
    0x0A: "sftp://", 0x0B: "smb://", 0x0C: "nfs://", 0x0D: "ftp://",
    0x0E: "dav://", 0x0F: "news:", 0x10: "telnet://", 0x11: "imap:",
    0x12: "rtsp://", 0x13: "urn:", 0x14: "pop:", 0x15: "sip:", 0x16: "sips:",
    0x17: "tftp:", 0x18: "btspp://", 0x19: "btl2cap://", 0x1A: "btgoep://",
    0x1B: "tcpobex://", 0x1C: "irdaobex://", 0x1D: "file://",
    0x1E: "urn:epc:id:", 0x1F: "urn:epc:tag:", 0x20: "urn:epc:pat:",
    0x21: "urn:epc:raw:", 0x22: "urn:epc:", 0x23: "urn:nfc:",
}


def identify(atqa: str, sak: str, uid_hex: str) -> dict:
    """ATQA/SAK/UID -> rich identity dict for the UI (no dump needed).

    The exact Ultralight/NTAG product is left generic here and refined from the
    dump size by mfu_product() once the tag has been read.
    """
    sak = (sak or "").upper().rjust(2, "0")[-2:]
    atqa = (atqa or "").upper()
    uid = "".join(c for c in (uid_hex or "") if c in "0123456789ABCDEFabcdef").upper()
    uid_len = len(uid) // 2
    product, family, category, kind = _TYPE.get(
        sak, ("Unknown 13.56 MHz tag", "ISO 14443", "other", "uid"))
    # SAK 0x20: ATQA 0x0344 = DESFire / NTAG424 DNA (secure); otherwise a bare smartcard.
    if sak == "20":
        if atqa.endswith("0344") or atqa == "344":
            product, family, category = "DESFire / NTAG424 DNA", "MIFARE DESFire / NTAG424", "secure-card"
        else:
            product, family, category = "ISO 14443-4 smartcard", "ISO 14443-4", "other"
    mfr = _MFR.get(int(uid[:2], 16), "") if (uid_len >= 7 and len(uid) >= 2) else ""
    # A 4-byte UID whose first byte is 0x08 is a random/non-unique ID (anti-tracking).
    is_random = uid_len == 4 and uid[:2] == "08"
    return {
        "product": product, "family": family, "category": category, "kind": kind,
        "manufacturer": mfr, "uid_len": uid_len, "is_random": is_random,
        "mem": _MEM.get(product, ""),
    }


def mfu_product(dump_size: int) -> tuple[str, str]:
    """Best-effort exact Ultralight/NTAG product + memory string from dump size."""
    if dump_size in _MFU_DUMP:
        return _MFU_DUMP[dump_size]
    return "Ultralight / NTAG", "%d B dump" % dump_size


def parse_ndef(data: bytes) -> list:
    """Parse NDEF records out of an NFC Forum Type-2 tag's data area.

    `data` = the user-memory bytes from page 4 onward (i.e. AFTER the 16-byte
    UID/lock/CC header). Walks the TLV stream and returns a list of
    {"kind": "URL"|"Text"|"Other", "value": str}. Every index is bounds-checked;
    truncated / malformed input is best-effort decoded and NEVER raises. (Logic
    verified against 7 test vectors incl. long records, empty and garbage tags.)
    """
    records = []
    if not data:
        return records

    def decode_record(tnf, rtype, payload):
        if tnf == 0x01 and rtype == b"U":
            if not payload:
                return {"kind": "URL", "value": ""}
            prefix = _URI_PREFIXES.get(payload[0], "")
            return {"kind": "URL", "value": prefix + payload[1:].decode("utf-8", "replace")}
        if tnf == 0x01 and rtype == b"T":
            if not payload:
                return {"kind": "Text", "value": ""}
            status = payload[0]
            lang_len = status & 0x3F
            enc = "utf-16" if (status & 0x80) else "utf-8"
            start = min(1 + lang_len, len(payload))
            return {"kind": "Text", "value": payload[start:].decode(enc, "replace")}
        if tnf == 0x03:  # absolute URI: the URI is in the TYPE field
            return {"kind": "URL", "value": rtype.decode("utf-8", "replace")}
        return {"kind": "Other", "value": payload.decode("utf-8", "replace")}

    def parse_message(msg):
        i, n = 0, len(msg)
        while i < n:
            header = msg[i]; i += 1
            tnf = header & 0x07
            il = bool(header & 0x08)
            sr = bool(header & 0x10)
            me = bool(header & 0x40)
            if i >= n:
                return
            type_len = msg[i]; i += 1
            if sr:
                if i >= n:
                    return
                payload_len = msg[i]; i += 1
            else:
                if i + 4 > n:
                    return
                payload_len = int.from_bytes(msg[i:i + 4], "big"); i += 4
            id_len = 0
            if il:
                if i >= n:
                    return
                id_len = msg[i]; i += 1
            if i + type_len > n:
                return
            rtype = msg[i:i + type_len]; i += type_len
            if i + id_len > n:
                return
            i += id_len
            avail = n - i
            take = payload_len if payload_len <= avail else avail
            payload = msg[i:i + take]
            i += payload_len
            records.append(decode_record(tnf, rtype, payload))
            if take < payload_len or me:
                return

    try:
        i, n = 0, len(data)
        while i < n:
            tag = data[i]; i += 1
            if tag == 0x00:          # NULL TLV (padding)
                continue
            if tag == 0xFE:          # Terminator TLV
                break
            if i >= n:               # length byte required but absent
                break
            length = data[i]; i += 1
            if length == 0xFF:       # 3-byte length form
                if i + 2 > n:
                    break
                length = (data[i] << 8) | data[i + 1]; i += 2
            avail = n - i
            take = length if length <= avail else avail
            value = data[i:i + take]
            if tag == 0x03:          # NDEF Message TLV
                parse_message(value)
            i += length
            if take < length:
                break
    except Exception:               # last-resort net: never raise
        pass
    return records


def read_content(kind: str, dump_path: str) -> tuple:
    """Return (records, note) for a dumped tag.

    Ultralight/NTAG (Type 2) -> parsed NDEF records. Classic -> an access-card
    note (its data sits behind sector keys; UID is the usual identifier).
    """
    try:
        with open(dump_path, "rb") as f:
            data = f.read()
    except Exception:
        return [], ""
    if kind == "mfu":
        # Type-2 data area starts at page 4 = byte offset 16 (after UID/lock/CC).
        recs = parse_ndef(data[16:]) if len(data) > 16 else []
        return recs, ("" if recs else "No NDEF data (blank or non-NDEF tag)")
    if kind == "mfc":
        return [], "Access card - identified by UID + sector data (keys needed to read all)"
    return [], ""


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
    """Pull UID / ATQA / SAK out of nfc-list output and run full identification."""
    uid = re.search(r"UID \(NFCID1\):\s*([0-9a-fA-F ]+)", out)
    if not uid:
        return None
    uid_hex = uid.group(1).split()
    atqa = re.search(r"ATQA \(SENS_RES\):\s*([0-9a-fA-F ]+)", out)
    sak = re.search(r"SAK \(SEL_RES\):\s*([0-9a-fA-F]+)", out)
    atqa_s = "".join(atqa.group(1).split()).upper() if atqa else ""
    sak_s = ("%02X" % int(sak.group(1), 16)) if sak else ""
    uid_s = "".join(uid_hex).upper()
    ident = identify(atqa_s, sak_s, uid_s)
    tag = {
        "uid": uid_s,
        "uid_spaced": " ".join(b.upper() for b in uid_hex),
        "atqa": atqa_s,
        "sak": sak_s,
        "type": ident["product"],   # back-compat: 'type' now carries the product name
    }
    tag.update(ident)               # product, family, category, kind, manufacturer, ...
    return tag


def read(timeout: float = 12.0) -> Optional[dict]:
    """Poll for one tag and return its parsed identity, or None if none appears.

    Debian's libnfc-bin has no nfc-poll, so we loop nfc-list (which probes the
    13.56 MHz field once and exits) until a tag is present or `timeout` elapses.
    Each nfc-list call re-opens the ACR122U (~0.4 s), so a tag held on the reader
    is caught within a poll or two.
    """
    if _which(T_LIST) is None:
        raise AcidNFCError("%s not installed (apt install libnfc-bin)" % T_LIST)
    deadline = time.monotonic() + max(1.0, timeout)
    while True:
        _rc, out = _run([T_LIST], timeout=5)
        tag = _parse_target(out)
        if tag:
            return tag
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.15)


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

    def start(self, uid_hex: str, atqa: str = "", sak: str = "") -> tuple[bool, str]:
        """Emulate a tag. Passing the original ATQA + SAK makes the emulated tag
        present the real card's protocol signature (so a Flipper/reader identifies
        the correct type instead of the hardcoded Mifare-Classic default)."""
        exe = _which(T_EMU_UID)
        if not exe:
            return False, "%s not installed" % T_EMU_UID
        uid = "".join(c for c in (uid_hex or "") if c in "0123456789abcdefABCDEF")
        if len(uid) < 8:
            return False, "need a 4-byte UID"
        atqa = "".join(c for c in (atqa or "") if c in "0123456789abcdefABCDEF")
        sak = "".join(c for c in (sak or "") if c in "0123456789abcdefABCDEF")
        self.stop()
        # UID must be the LAST argument (the tool treats the trailing 8-hex token as
        # the UID); options first. -a/-s only when well-formed, else the tool default.
        args = [exe, "-q"]
        if len(atqa) == 4:
            args += ["-a", atqa]
        if len(sak) == 2:
            args += ["-s", sak]
        args.append(uid[:8])
        try:
            with self._lock:
                # own process group so stop() (and its timeout) takes the child too.
                self._proc = subprocess.Popen(
                    args, stdout=subprocess.DEVNULL,
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
