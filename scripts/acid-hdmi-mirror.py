#!/usr/bin/env python3
# Acid Zero - HDMI mirror: continuously blits the TFT framebuffer (fb1, 480x320
# RGB565, the touch panel) scaled-to-fill onto the HDMI framebuffer (fb0).
#
# Scale is UNIFORM (no aspect distortion) and sized to fill the larger of the
# two axes exactly, letterboxing only the other axis - e.g. on an 800x480
# panel this fills the full height (720x480, 40px side bars) instead of a
# tiny 480x320 box in the middle.
#
# fb0's resolution is read from sysfs at startup (NOT hardcoded) because the
# vc4-kms-v3d driver renegotiates the HDMI mode via EDID on every boot and can
# land on a different size than the previous boot. bpp is asserted at 16 (the
# only format this script packs); if a future boot ever negotiates a different
# depth, this exits cleanly instead of writing garbage/oversized frames.
#
# READ-ONLY mirror of fb1 -> does not touch acidzero.py's render loop or the
# touch/evdev pipeline in any way. Touch input stays wherever it already is;
# this only changes what you can SEE on the HDMI screen. Stop this process any
# time and HDMI/TFT behave exactly as before (fully reversible).
import sys
import time
import numpy as np
from PIL import Image

SRC, SRC_W, SRC_H = '/dev/fb1', 480, 320
DST = '/dev/fb0'
FPS = 12
FRAME_BYTES = SRC_W * SRC_H * 2
# hardware RGB565 layout confirmed via fbset on both fb0/fb1: rgba 5/11,6/5,5/0,0/0
# (R=5 bits @ bit11, G=6 bits @ bit5, B=5 bits @ bit0). PIL's 'BGR;16' raw mode can
# DECODE this correctly but has no matching ENCODER, so pack/unpack is done by hand
# here to stay symmetric and avoid depending on that one-way codec.


def unpack565(buf, w, h):
    raw = np.frombuffer(buf, dtype='<u2').reshape(h, w)
    r = ((raw >> 11) & 0x1F).astype('uint8') << 3
    g = ((raw >> 5) & 0x3F).astype('uint8') << 2
    b = (raw & 0x1F).astype('uint8') << 3
    return np.dstack([r, g, b])


def pack565(rgb):
    r = (rgb[:, :, 0].astype('<u2') >> 3) << 11
    g = (rgb[:, :, 1].astype('<u2') >> 2) << 5
    b = rgb[:, :, 2].astype('<u2') >> 3
    return r | g | b


def read_fb0_geometry():
    with open('/sys/class/graphics/fb0/virtual_size') as f:
        w, h = (int(x) for x in f.read().strip().split(','))
    with open('/sys/class/graphics/fb0/bits_per_pixel') as f:
        bpp = int(f.read().strip())
    return w, h, bpp


def main():
    dst_w, dst_h, bpp = read_fb0_geometry()
    if bpp != 16:
        print('fb0 is %dbpp, not 16bpp RGB565 - mirror not supported, exiting' % bpp, file=sys.stderr)  # GUARD:EXEMPT - startup diagnostic, not a loop
        sys.exit(1)
    scale = min(dst_w / SRC_W, dst_h / SRC_H)          # uniform, fills the tighter axis fully
    out_w, out_h = int(SRC_W * scale), int(SRC_H * scale)
    off_x, off_y = (dst_w - out_w) // 2, (dst_h - out_h) // 2
    print('fb0 %dx%d @%dbpp -> mirroring %.2fx (%dx%d @ %d,%d)' % (dst_w, dst_h, bpp, scale, out_w, out_h, off_x, off_y), file=sys.stderr)  # GUARD:EXEMPT - startup diagnostic, not a loop

    canvas = np.zeros((dst_h, dst_w), dtype='<u2')
    with open(SRC, 'rb') as fsrc, open(DST, 'r+b') as fdst:
        while True:
            t0 = time.time()
            fsrc.seek(0)
            buf = fsrc.read(FRAME_BYTES)
            if len(buf) == FRAME_BYTES:
                rgb = unpack565(buf, SRC_W, SRC_H)
                if (out_w, out_h) != (SRC_W, SRC_H):
                    img = Image.fromarray(rgb, 'RGB').resize((out_w, out_h), Image.NEAREST)
                    rgb = np.asarray(img)
                canvas[off_y:off_y + out_h, off_x:off_x + out_w] = pack565(rgb)
                fdst.seek(0)
                fdst.write(canvas.tobytes())
            dt = time.time() - t0
            time.sleep(max(0.0, (1.0 / FPS) - dt))


if __name__ == '__main__':
    main()
