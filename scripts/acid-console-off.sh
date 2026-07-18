#!/bin/sh
# Acid Zero - give the UI SOLE ownership of the TFT framebuffer.
# Detaches the kernel framebuffer console (fbcon) from the display so getty /
# kernel messages / the blinking cursor never draw over the app (which writes
# straight to /dev/fb0). Also disables console blanking. Idempotent; run as a
# systemd ExecStartPre before acidzero.py.
for v in /sys/class/vtconsole/vtcon*; do
    if grep -q 'frame buffer' "$v/name" 2>/dev/null; then
        echo 0 > "$v/bind" 2>/dev/null || true
    fi
done
TERM=linux setterm -blank 0 -powerdown 0 </dev/tty1 >/dev/tty1 2>/dev/null || true
exit 0
