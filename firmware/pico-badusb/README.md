# Acid Zero — BadUSB co-processor (Raspberry Pi Pico 2 W)

A **self-contained WiFi Rubber Ducky**. The Pico 2 W is a USB HID keyboard plugged
into the **target**, and it **hosts its own WiFi access point** — it needs no
external network, so it works **anywhere** (home, the field, a client site). The
Pi (Acid Zero) joins that AP on a dedicated adapter, sends **Flipper-compatible
DuckyScript**, and the Pico types it into the target.

```
[Pi / Acid Zero]  --joins Pico's AP-->  [Pico 2 W: HID keyboard + AP + server]  --USB-->  [TARGET]
   acid_badusb.py   AcidZero-Duck (WPA2)   code.py @ 192.168.4.1:1337                     keystrokes
```

> ⚠️ **AUTHORIZED USE ONLY** — inject keystrokes only into machines you own or are
> explicitly authorized to test. See [`../../ETHICS.md`](../../ETHICS.md).

---

## 1. Flash CircuitPython

Hold **BOOTSEL**, plug the Pico 2 W into any PC → `RPI-RP2` drive appears → drop the
**Pico 2 W CircuitPython `.uf2`** — use **CircuitPython 10.x** (the bundled `adafruit_hid`
is built for it) — from <https://circuitpython.org/board/raspberry_pi_pico2_w/>.
It reboots as a `CIRCUITPY` drive.

## 2. Copy the framework onto CIRCUITPY

| From | To (CIRCUITPY) |
|------|----------------|
| `code.py` | `code.py` |
| the **`lib/`** folder **bundled in this repo** (contains `adafruit_hid/`, already the right version) | `lib/` |
| `settings.toml.example` *(optional — only to rename the AP / change its password)* | `settings.toml` |
| `boot.py` *(optional — stealth, see the file)* | `boot.py` |

`wifi`, `socketpool`, `usb_hid` are built into CircuitPython. The one external library,
`adafruit_hid`, is **bundled in this repo** at [`lib/adafruit_hid/`](lib/) (compiled `.mpy`
for **CircuitPython 10.x** — see [`lib/README.md`](lib/README.md)), so you can flash the
Pico straight from the repo, no library-bundle hunt. **No WiFi credentials are required** —
the Pico makes its own AP.

Default AP: **SSID `AcidZero-Duck`**, **password `acidzero1337`** (WPA2). Change them
in `settings.toml` (and keep `AP_SSID`/`AP_PSK` in the Pi's `acid_badusb.py` in sync).

## 3. Operate

- Pico 2 W → USB → the **target** machine (your own laptop for testing). On power it
  brings up the `AcidZero-Duck` AP at **192.168.4.1** and starts the BadUSB server.
- On the Pi, open the **Bad USB** app → **CONNECT**. The Pi joins the AP on a
  **dedicated spare adapter** (static `192.168.4.2`, no default route), so its main
  uplink keeps SSH + internet the whole time. **DISCONNECT** releases that adapter.

## 4. Run a payload (from the Pi)

DuckyScripts live in **`/home/ella3/acid_badusb/`** (`*.txt`) — drop your Flipper
BadUSB scripts straight in. After CONNECT:

```
python3 /usr/local/bin/acid_badusb.py connect                # join the Pico AP (wlan2)
python3 /usr/local/bin/acid_badusb.py                        # ping + list scripts
python3 /usr/local/bin/acid_badusb.py disconnect             # release the adapter
```

…or from Python / the launcher app:

```python
from acid_badusb import BadUSB, link_connect, link_disconnect
link_connect()                             # join the Pico's AP on the worker adapter
bu = BadUSB()
bu.ping()                                  # is the Pico reachable @ 192.168.4.1:1337?
bu.run_script('/home/ella3/acid_badusb/demo-notepad.txt')
link_disconnect()
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

Serial console (Mu / `screen /dev/ttyACM* 115200`) on the target side shows:

```
acidducky: starting AP "AcidZero-Duck" (attempt 1)
acidducky: AP up at 192.168.4.1
acidducky: BadUSB server up on 192.168.4.1:1337 (AP "AcidZero-Duck")
```

From the Pi: **CONNECT** in the app → `LINK: ONLINE`. Then run `demo-notepad.txt`
against your own machine to confirm the HID path end-to-end.

> **Note (Pico W radio):** the CYW43 can flake on its first association/AP-start after a
> cold boot — `code.py` retries, so give it ~10–20 s to come up before CONNECT.
