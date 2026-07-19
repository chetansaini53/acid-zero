# Acid Zero - Pico 2 W BadUSB boot config (OPTIONAL - stealth mode).
# ---------------------------------------------------------------------------
# By default CircuitPython exposes a USB drive (CIRCUITPY) + a serial console.
# On a BadUSB you usually want the target to see ONLY a keyboard - no drive
# popup, no extra COM port. Uncomment the lines below to hide them.
#
# WARNING: once the drive is hidden you can no longer edit files by drag-drop.
# To re-enable for editing, hold the BOOTSEL button while plugging in, delete /
# rename this boot.py (or reflash), then it's a normal drive again. Keep the
# drive VISIBLE while developing/tuning payloads; enable stealth only for a real
# authorized engagement.
#
# import storage, usb_cdc, usb_hid
# storage.disable_usb_drive()          # hide the CIRCUITPY mass-storage drive
# usb_cdc.disable()                    # hide the serial console COM port
# usb_hid.enable((usb_hid.Device.KEYBOARD,))   # present ONLY a keyboard
