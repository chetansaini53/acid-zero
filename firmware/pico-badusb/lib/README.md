# Bundled CircuitPython libraries (`CIRCUITPY/lib/`)

These are the exact libraries that live on the Pico's `CIRCUITPY/lib/` — bundled here
so you can flash the Pico **straight from this repo**, without hunting the CircuitPython
library bundle for the right version. Copy this whole `lib/` folder onto the Pico.

## `adafruit_hid/`

Adafruit's CircuitPython HID library — the USB keyboard / mouse / consumer-control layer
`code.py` uses to type DuckyScript into the target.

- **Upstream:** [Adafruit_CircuitPython_HID](https://github.com/adafruit/Adafruit_CircuitPython_HID)
- **License:** **MIT** © Adafruit Industries — redistributed here under the MIT License.
- **Format:** compiled `.mpy`, built for **CircuitPython 10.x** (matches this project's Pico).

> ⚠️ **`.mpy` files are tied to the CircuitPython major version.** These are for
> **CircuitPython 10.x**. If your Pico runs a different major version (9.x, 11.x, …),
> replace this folder with the matching `adafruit_hid` from that version's bundle at
> <https://circuitpython.org/libraries>, or drop in the plain `.py` source (which is
> version-independent). A mismatch shows up as an `ImportError: incompatible .mpy file`.

Only `adafruit_hid` is needed — `wifi`, `socketpool`, `usb_hid` are built into
CircuitPython itself.
