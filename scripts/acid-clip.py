#!/usr/bin/env python3
"""
Acid Zero - LAN clipboard bridge for the Terminal app.

A tiny, TOKEN-GATED HTTP endpoint so a paired laptop on the same Wi-Fi can push a
command into the Pi's clipboard (and read it back). The on-device Terminal plugin
then PASTEs that text and - only on an explicit tap - runs it. BLE HID cannot carry
a clipboard, so this rides the LAN instead.

    GET  /clip   -> {"seq":N,"text":"..."}     (needs header X-Acid-Token)
    POST /clip   body = raw UTF-8 text         (needs header X-Acid-Token)

Security model (own-lab use only, see ETHICS.md):
  * Every request needs the shared token in /etc/acid-clip.token (0600, root-only).
    A random 144-bit token is generated on first start; compare is constant-time.
  * Read is gated too - the clipboard may hold secrets, so it is never handed to an
    unauthenticated LAN peer.
  * The endpoint only STORES text. Nothing here executes anything; running a command
    is a deliberate, human-in-the-loop tap inside the Terminal app.
  * Body size is capped (MAXLEN) so a peer cannot exhaust memory.
"""
import hmac
import http.server
import json
import os
import socketserver
import tempfile
import threading

CLIP = "/run/acid_clip.txt"
TOKEN_FILE = "/etc/acid-clip.token"
PORT = 8899
MAXLEN = 256 * 1024          # 256 KiB clipboard cap

_lock = threading.Lock()
_seq = 0


def _token():
    try:
        with open(TOKEN_FILE, encoding="ascii") as f:
            return f.read().strip()
    except Exception:
        return ""


def _atomic_write(path, data, encoding):
    """Write `path` atomically with 0600 perms from creation (mkstemp is 0600),
    so the secret/clip never exists world-readable, even for an instant."""
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".acidtmp")
    try:
        os.write(fd, data.encode(encoding))
    finally:
        os.close(fd)
    os.replace(tmp, path)              # unique tmp name -> no cross-process .tmp collision


def _ensure_token():
    """Create a strong random token on first run; root-only, 0600 from birth."""
    if os.path.exists(TOKEN_FILE) and _token():
        return
    _atomic_write(TOKEN_FILE, os.urandom(18).hex(), "ascii")


def _read_clip():
    try:
        with open(CLIP, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _write_clip(text):
    global _seq
    _atomic_write(CLIP, text, "utf-8")     # 0600: the clip may hold copied-out secrets
    _seq += 1


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 5                          # drop slow/partial requests (anti-slowloris);
    #                                      the request line + headers are read pre-auth, so
    #                                      an unbounded read would let a peer pin threads.

    def _authed(self):
        want, got = _token(), self.headers.get("X-Acid-Token", "")
        if want and hmac.compare_digest(want, got):
            return True
        self._reply(403, b"forbidden\n", "text/plain")
        return False

    def _reply(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        if self.path.split("?", 1)[0] != "/clip":
            return self._reply(404, b"not found\n", "text/plain")
        if not self._authed():
            return
        with _lock:
            body = json.dumps({"seq": _seq, "text": _read_clip()}).encode("utf-8")
        self._reply(200, body, "application/json")

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/clip":
            return self._reply(404, b"not found\n", "text/plain")
        if not self._authed():
            return
        try:
            n = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            n = -1
        if n < 0 or n > MAXLEN:
            return self._reply(413, b"too large\n", "text/plain")
        try:
            raw = self.rfile.read(n) if n else b""
        except Exception:
            self.close_connection = True     # body stalled past timeout -> drop it
            return
        data = raw.decode("utf-8", "replace")
        with _lock:
            _write_clip(data)
        self._reply(204, b"", "text/plain")

    def log_message(self, *_a):          # silence stderr access log
        pass


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    _ensure_token()
    if not os.path.exists(CLIP):
        _write_clip("")                  # seed so the Terminal app always has a file to read
    _Server(("0.0.0.0", PORT), _Handler).serve_forever()


if __name__ == "__main__":
    main()
