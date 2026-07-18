#!/usr/bin/env python3
# Acid Zero - MJPEG screen stream: serves the live TFT (fb1, the actual touch
# panel - lowest latency, source of truth) as an HTTP MJPEG stream so it can
# be viewed/recorded from a laptop on the same network with nothing more than
# a browser, VLC ("Open Network Stream"), or ffmpeg:
#   ffmpeg -i http://<pi-ip>:8090/stream.mjpg output.mp4
#
# READ-ONLY: only reads fb1, never writes it, never touches touch/evdev - the
# actual UI and touch input are completely unaffected. LAN-only by design, no
# auth (same posture as bettercap's own admin API in this project) - do not
# expose this port beyond your own network.
import io
import time
import numpy as np
from PIL import Image
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SRC, SRC_W, SRC_H = '/dev/fb1', 480, 320
FRAME_BYTES = SRC_W * SRC_H * 2
PORT = 8090
FPS = 8
JPEG_QUALITY = 70
BOUNDARY = 'acidzeroframe'


def unpack565(buf, w, h):
    """RGB565 raw bytes -> (H,W,3) uint8 RGB array. Matches the hardware bit
    layout confirmed via fbset (rgba 5/11,6/5,5/0,0/0): R=5b@11,G=6b@5,B=5b@0."""
    raw = np.frombuffer(buf, dtype='<u2').reshape(h, w)
    r = ((raw >> 11) & 0x1F).astype('uint8') << 3
    g = ((raw >> 5) & 0x3F).astype('uint8') << 2
    b = (raw & 0x1F).astype('uint8') << 3
    return np.dstack([r, g, b])


def grab_jpeg():
    with open(SRC, 'rb') as f:
        buf = f.read(FRAME_BYTES)
    if len(buf) != FRAME_BYTES:
        return None
    img = Image.fromarray(unpack565(buf, SRC_W, SRC_H), 'RGB')
    out = io.BytesIO()
    img.save(out, 'JPEG', quality=JPEG_QUALITY)
    return out.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass   # GUARD:EXEMPT - suppress default per-request stderr spam, not app logging

    def do_GET(self):
        if self.path not in ('/', '/stream.mjpg'):
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header('Age', '0')
        self.send_header('Cache-Control', 'no-cache, private')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=%s' % BOUNDARY)
        self.end_headers()
        period = 1.0 / FPS
        try:
            while True:
                t0 = time.time()
                jpeg = grab_jpeg()
                if jpeg:
                    self.wfile.write(b'--%s\r\n' % BOUNDARY.encode())
                    self.wfile.write(b'Content-Type: image/jpeg\r\n')
                    self.wfile.write(b'Content-Length: %d\r\n\r\n' % len(jpeg))
                    self.wfile.write(jpeg)
                    self.wfile.write(b'\r\n')
                time.sleep(max(0.0, period - (time.time() - t0)))
        except (BrokenPipeError, ConnectionResetError):
            pass   # viewer disconnected - normal, not an error


def main():
    srv = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    print('acid-fb-stream: http://0.0.0.0:%d/stream.mjpg' % PORT, flush=True)  # GUARD:EXEMPT - startup diagnostic, not a loop
    srv.serve_forever()


if __name__ == '__main__':
    main()
