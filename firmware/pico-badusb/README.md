# Acid Zero — BadUSB co-processor (Raspberry Pi Pico 2 W)

A **WiFi-controlled Rubber Ducky**. The Pico 2 W is a USB HID keyboard plugged into
the **target**; it joins your WiFi as `acidducky.local`. The Pi (Acid Zero) sends a
**Flipper-compatible DuckyScript** over WiFi and the Pico types it into the target.

```
[Pi / Acid Zero]  --WiFi-->  [Pico 2 W: HID keyboard + WiFi server]  --USB-->  [TARGET]
   acid_badusb.py             code.py (DuckyScript interpreter)                keystrokes
```

> ⚠️ **AUTHORIZED USE ONLY** — inject keystrokes only into machines you own or are
> explicitly authorized to test. See [`../../ETHICS.md`](../../ETHICS.md).

---

## 1. Flash CircuitPython

Hold **BOOTSEL**, plug the Pico 2 W into any PC → `RPI-RP2` drive appears → drop the
**Pico 2 W CircuitPython `.uf2`** (from <https://circuitpython.org/board/raspberry_pi_pico2_w/>).
It reboots as a `CIRCUITPY` drive.

## 2. Copy the framework onto CIRCUITPY

Onto the `CIRCUITPY` drive:

| From | To (CIRCUITPY) |
|------|----------------|
| `code.py` | `code.py` |
| `settings.toml.example` → fill in WiFi | `settings.toml` |
| the **`adafruit_hid`** folder from the [CircuitPython library bundle](https://circuitpython.org/libraries) | `lib/adafruit_hid/` |
| `boot.py` *(optional — stealth, see the file)* | `boot.py` |

`wifi`, `socketpool`, `mdns`, `usb_hid` are built into CircuitPython — only
`adafruit_hid` needs copying.

## 3. Wire it up

- **Operation:** Pico 2 W → USB → the **target** machine (your own laptop for testing).
  On power it joins your WiFi and prints its IP on the serial console.
- The Pi must be on the **same WiFi**. It reaches the Pico at `acidducky.local:1337`.

## 4. Run a payload (from the Pi)

DuckyScripts live in **`/home/ella3/acid_badusb/`** (`*.txt`) — drop your Flipper
BadUSB scripts straight in. Then:

```
python3 /usr/local/bin/acid_badusb.py                       # ping + list scripts
python3 /usr/local/bin/acid_badusb.py /home/ella3/acid_badusb/demo-notepad.txt
```

…or from Python / the launcher app:

```python
from acid_badusb import BadUSB
bu = BadUSB()
bu.ping()                                  # is the Pico online?
bu.run_script('/home/ella3/acid_badusb/demo-notepad.txt')
```

## 5. DuckyScript reference (Flipper/Hak5 compatible)

| Command | Effect |
|---------|--------|
| `REM <text>` | comment (ignored) |
| `STRING <text>` | type the text |
| `STRINGLN <text>` | type the text + Enter |
| `DELAY <ms>` | wait |
| `DEFAULT_DELAY <ms>` | delay applied after every command |
| `REPEAT <n>` | repeat the previous line n times |
| `ID ...` | USB VID/PID line — ignored (already enumerated) |
| `GUI r` / `WINDOWS r` | Windows/Cmd + key |
| `CTRL ALT DELETE` / `CTRL-ALT-DEL` | modifier combo |
| named keys | `ENTER TAB ESC SPACE BACKSPACE DELETE HOME END PAGEUP PAGEDOWN INSERT UP DOWN LEFT RIGHT PRINTSCREEN MENU F1..F12 CAPSLOCK` |

Layout is **US** (`KeyboardLayoutUS`). For other layouts swap the layout import in
`code.py`.

## 6. Verify

Serial console (Mu / `screen /dev/ttyACM* 115200` on the target-side, or the Pi if
the Pico is on the Pi) shows:

```
acidducky: connecting to <ssid>
acidducky: IP <ip>
acidducky: BadUSB server up on acidducky.local:1337
```

From the Pi, `acid_badusb.py` → `OK - Pico BadUSB online`. Then run `demo-notepad.txt`
against your own machine to confirm the HID path end-to-end.
