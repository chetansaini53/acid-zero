#!/usr/bin/env python3
# ACID native-app TEMPLATE. Educational / own-lab only.
# Proves the native-plugin contract: a standalone program that OWNS the TFT + touch
# while running, then EXITS so Acid Zero resumes. Port any C/C++/Rust/Flipper app the
# same way - just match this contract:
#   1. Render to the ILI9486 framebuffer (480x320, RGB565, found by NAME not number).
#   2. Block/run your UI; read taps from the ADS7846 touch event device.
#   3. EXIT (return 0) on the exit gesture - the launcher is blocked on you and
#      redraws the home grid the moment you return.
# Drop this folder in /usr/local/lib/acid-apps/<yourapp>/ with an app.json manifest.
import os, glob, struct, mmap, time, select
from PIL import Image, ImageDraw, ImageFont

W, H, BPP = 480, 320, 2  # ILI9486: 480x320, RGB565 = 2 bytes/px

def find_fb():
    # bind by NAME (fb numbers reshuffle each boot when HDMI is present)
    for fb in sorted(glob.glob('/sys/class/graphics/fb*')):
        try:
            nm = open(os.path.join(fb, 'name')).read().strip().lower()
        except Exception:
            continue
        if 'ili9486' in nm or 'fb_ili9486' in nm or 'piscreen' in nm:
            return '/dev/' + os.path.basename(fb)
    return '/dev/fb1'

def find_touch():
    for ev in sorted(glob.glob('/dev/input/event*')):
        try:
            nm = open('/sys/class/input/%s/device/name' % os.path.basename(ev)).read().strip().lower()
        except Exception:
            nm = ''
        if 'ads7846' in nm or 'touch' in nm or 'stmpe' in nm:
            return ev
    return None

def rgb565(img):
    px = img.load(); out = bytearray(W * H * BPP); i = 0
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y][:3]
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out[i] = v & 0xFF; out[i + 1] = (v >> 8) & 0xFF; i += 2
    return bytes(out)

def font(sz):
    for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
              '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        try: return ImageFont.truetype(p, sz)
        except Exception: pass
    return ImageFont.load_default()

def draw_frame(fbdev, t0):
    img = Image.new('RGB', (W, H), (12, 16, 22))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 40), fill=(30, 200, 121))
    d.text((14, 10), 'NATIVE APP RUNNING', font=font(20), fill=(8, 12, 16))
    d.text((20, 70),  'This is an external/native plugin.', font=font(18), fill=(225, 232, 240))
    d.text((20, 100), 'It owns the screen + touch right now.', font=font(16), fill=(150, 165, 185))
    d.text((20, 130), 'Port C/C++/Rust/Flipper apps the same', font=font(16), fill=(150, 165, 185))
    d.text((20, 150), 'way - render fb, read touch, exit.', font=font(16), fill=(150, 165, 185))
    d.text((20, 195), 'uptime: %5.1fs' % (time.time() - t0), font=font(18), fill=(30, 200, 121))
    d.rectangle((W // 2 - 90, 250, W // 2 + 90, 295), fill=(210, 60, 60))
    d.text((W // 2 - 60, 263), 'TAP TO EXIT', font=font(18), fill=(255, 240, 240))
    try:
        with open(fbdev, 'wb') as f:
            f.write(rgb565(img))
    except Exception:
        pass

def main():
    fbdev = find_fb(); tdev = find_touch()
    t0 = time.time(); last = 0.0
    tf = None
    if tdev:
        try: tf = open(tdev, 'rb')
        except Exception: tf = None
    draw_frame(fbdev, t0)
    while True:
        now = time.time()
        if now - last >= 1.0:      # repaint uptime ~1/sec (low CPU)
            draw_frame(fbdev, t0); last = now
        if tf is not None:
            r, _, _ = select.select([tf], [], [], 0.2)
            if r:
                try: tf.read(16)   # any touch event -> exit
                except Exception: pass
                break
        else:
            time.sleep(0.2)
            if now - t0 > 8: break  # no touch device -> auto-exit after 8s
    try:
        if tf: tf.close()
    except Exception: pass
    return 0

if __name__ == '__main__':
    main()
