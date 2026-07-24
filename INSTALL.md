# Install / Setup

> ⚠️ For **authorized, own-lab, educational** use only. See [ETHICS.md](ETHICS.md).

Acid Zero runs as a touchscreen UI layer on top of a
[jayofelony pwnagotchi](https://github.com/jayofelony/pwnagotchi) install on a
**Raspberry Pi 3B+** with a **3.5" ILI9486 SPI TFT + ADS7846 touch**.

Follow the steps in order on a fresh SD card and the Pi boots straight into the
launcher. Step 1 (flashing the base image) is done on **Windows**; everything from
step 2 on is run **on the Pi** over SSH.

## 1. Base OS — flash jayofelony pwnagotchi

Acid Zero doesn't replace pwnagotchi; it sits on top of a stock install and reuses
its bettercap REST API for Wi-Fi recon. So first get a working pwnagotchi you can SSH
into.

### 1.1 Download the right image

Open the releases page and grab the **64-bit** asset (the Pi 3B+ is a 64-bit board —
the 32-bit image is for the Pi Zero W and is the #1 first mistake):

- https://github.com/jayofelony/pwnagotchi/releases/latest → `pwnagotchi-64bit-<version>.img.xz`
  (currently `pwnagotchi-64bit-2.9.5.4.img.xz`, ~1.6 GB)

No need to decompress — the flasher writes the `.img.xz` directly.

### 1.2 Flash to the SD card (Windows)

Card is mounted at `I:`. Use **Raspberry Pi Imager** (or balenaEtcher):

1. Raspberry Pi Imager → **Choose OS → Use custom** → select the `.img.xz` you downloaded.
2. **Choose storage** → pick the SD card. **Confirm it's the removable card by size, not
   by the letter `I:`** — picking the wrong disk wipes it.
3. Click **Write**.
4. When Imager asks *"Would you like to apply OS customisation settings?"* → click
   **NO** (or **"NO, CLEAR SETTINGS"**).

> ⚠️ **Do not set a username/password/SSH/Wi-Fi/hostname in Imager.** The pre-built image
> already has them baked in; overriding breaks it and can lock you out. balenaEtcher has
> no customisation dialog, so with Etcher there's nothing to disable.

### 1.3 First boot

Insert the card, power the Pi from a solid **5V / 2.5A+** supply, and **leave it powered
and untouched for ~5–10 minutes** — first boot generates SSH keys and initialises. Pulling
power early (or a cheap/failing SD card, or an undervolting supply) is the top cause of
boot loops and corruption.

> ⚠️ **Never run `sudo apt-get upgrade` on this image** — it pins kernel/driver/bettercap
> versions; upgrading forces a full reflash.

### 1.4 SSH in

Default login is **`pi` / `raspberry`** (unchanged in the jayofelony fork; this is why
you must *not* override it in Imager). Default hostname is `pwnagotchi`.

- **Over USB (Pi 3B+):** connect the Pi's **USB data port** to the PC with a
  **USB-A ↔ USB-A *data* cable** (not charge-only). On Windows, install the bundled
  USB Ethernet/RNDIS gadget driver first (see the wiki's *Connecting* page — remove any
  old RNDIS driver and reboot Windows), then:
  ```
  ssh pi@pwnagotchi.local
  ```
  Don't rely on a fixed gadget IP — it varies by host. If `pwnagotchi.local` doesn't
  resolve, read the real address on the Pi (HDMI/keyboard or serial console) with
  `ip addr show usb0` and SSH to that.
- **Over your network:** put a second USB Wi-Fi adapter / Ethernet on the Pi, then
  `ssh pi@pwnagotchi.local` from any machine on the same LAN.

Plugged into a computer the pwnagotchi is in **MANU** (manual) mode — sshd runs but it
does **not** capture; on battery/power-only it runs the **AUTO** capture loop. SSH works
in both.

> The web UI is on by default at `http://pwnagotchi.local:8080` with creds
> `changeme` / `changeme` — change them (`ui.web.username` / `ui.web.password` in the
> config below) once you're in.

Optional pwnagotchi config lives in `/etc/pwnagotchi/config.toml` (user-editable;
`defaults.toml` is read-only and reverts on reboot). TOML is strict — a stray comma
silently fails the config load. You don't need to touch it for Acid Zero.

## 2. Get the code

On the Pi:

```
git clone https://github.com/chetansaini53/acid-zero.git
cd acid-zero          # every path below is relative to this repo root
```

## 3. Display + touch (device tree)

Add to `/boot/firmware/config.txt`:

```
dtparam=spi=on
dtparam=i2c1=on
dtparam=i2c_arm=on
dtoverlay=spi0-2cs
dtoverlay=piscreen,speed=16000000,rotate=270
```

This drives the ILI9486 panel on **SPI0** (framebuffer appears as `/dev/fb1`,
480×320, RGB565) and the ADS7846 touch on the second chip-select. The launcher
finds the framebuffer and the touch input device by **name**, not by number, so
boot-order reshuffles don't break it. `sudo reboot` after editing `config.txt`.

> SPI0 is fully used by the display + touch. For a future **CC1101 sub-GHz** add-on
> use **SPI1**; for a **PN532 NFC/RFID** add-on use the free **I2C-1** bus.
> See [docs/hardware-reference.pdf](docs/hardware-reference.pdf) for the full porting map.

## 4. Dependencies

```
sudo apt update
sudo apt install -y python3-pil python3-numpy python3-serial \
                    aircrack-ng hcxtools hostapd dnsmasq bluez
```

- `python3-pil` (Pillow) + `python3-numpy` — UI rendering + touch calibration (**required**)
- `python3-serial` (pyserial) — USB-serial to the ESP32/Pico/GPS co-processors (the
  IR / Sub-GHz / GPS plugins fall back gracefully if it's missing, but need it to work)
- `aircrack-ng` (airodump-ng / aireplay-ng) + `hcxtools` (hcxpcapngtool) — handshake capture/convert
- `hostapd` + `dnsmasq` — Evil Portal rogue AP + captive portal
- `bluez` (btmgmt / btmon) — BLE scan + spam
- `bettercap` — already provided by pwnagotchi

The launcher runs under the **system** `python3`, so these apt packages are all it needs
— there is no separate venv or `pip install` step for the UI.

## 5. Deploy the files

```
# launcher (acidzero.py + its sibling client libs: acid_ir.py, acid_subghz.py,
# acid_gps.py, acid_badusb.py, acid_wifiroles.py, acid_apcreds.py, acid_kbd.py,
# acid_flash.py - plugins import these by name, expecting them next to acidzero.py)
sudo cp launcher/*.py                    /usr/local/bin/
# helper scripts
sudo cp scripts/*.sh scripts/*.py       /usr/local/bin/
sudo chmod +x /usr/local/bin/acid-*.sh /usr/local/bin/acid-*.py /usr/local/bin/acidzero.py
# BLE library
sudo mkdir -p /usr/local/lib/acid-ble
sudo cp -r lib/acid-ble/*               /usr/local/lib/acid-ble/
# apps (plugins). Also copies the proto codecs ir_proto.py / subghz_proto.py that
# ir.py / subghz.py import - they must sit alongside the plugins. The bundled
# test_*.py have no META, so the launcher ignores them (harmless).
sudo mkdir -p /usr/local/lib/acid-apps
sudo cp -r apps/*                        /usr/local/lib/acid-apps/
# native-app executables (hello-native, wardrive-csv, ...) must be runnable
sudo chmod +x /usr/local/lib/acid-apps/*/*  2>/dev/null || true
# systemd units
sudo cp systemd/*                        /etc/systemd/system/
```

Everything lives in system paths and the service runs as **root** under systemd —
no per-user paths, so this reproduces identically on any user account.

## 6. Enable services

```
sudo systemctl daemon-reload
sudo systemctl enable --now acidzero.service          # the touchscreen UI
sudo systemctl enable --now acid-hs-clean.timer       # periodic handshake validation
```

`acidzero.service` launches the UI via `/usr/bin/python3 /usr/local/bin/acidzero.py`
and restarts it on crash. `acid-hs-clean.timer` periodically prunes invalid WPA
handshakes before wpa-sec upload (its `.service` is `oneshot`, triggered by the timer —
you don't enable it directly).

## 7. Verify

```
# UI service is up and stays up (Active: active (running), no restart loop)
systemctl status acidzero.service --no-pager

# live launcher log - watch for a Python traceback on boot (Ctrl-C to exit)
journalctl -u acidzero.service -f

# panel + touch were detected (panel is name-matched, usually /dev/fb1)
ls /dev/fb* /dev/input/event*
```

The TFT should show the home screen (Ella's face + clock + CPU/mem/temp stats). If the
service is `active` but the panel is **blank/white**, the display overlay in step 3 is
missing or wrong — fix `config.txt` and `sudo reboot`.

## 8. Co-processors (Sub-GHz / IR + Bad USB)

Two optional co-processors add the RF and HID tooling — both ship with **everything
needed to flash straight from this repo**:

- **Sub-GHz + IR (ESP32):** CC1101 + IR TX/RX on one ESP32. Wiring + one-command flash
  (prebuilt binary or build-from-source): **[firmware/README.md](firmware/README.md)**.
- **Bad USB (Raspberry Pi Pico 2 W):** a self-hosted-AP USB HID injector. Flash guide —
  CircuitPython + the **bundled `adafruit_hid`** library (no separate download):
  **[firmware/pico-badusb/README.md](firmware/pico-badusb/README.md)**. The Pi joins the
  Pico's own Wi-Fi AP on a **dedicated spare 2.4 GHz adapter** (so SSH + internet stay on
  the main uplink); the Bad USB app's **CONNECT** button runs the join. Full link diagram:
  [docs/badusb-architecture.svg](docs/badusb-architecture.svg).

### On-device Flasher (no laptop)

The **Flasher** app flashes both co-processors straight from the handheld — SCAN
(verify the right board) then FLASH. It ships the firmware it needs:

```
# esptool for the ESP32 flash - install into the SYSTEM python so the root launcher
# (which runs under /usr/bin/python3) can see it. A "pip install --user" in your login
# account is NOT visible to it.
sudo python3 -m pip install --break-system-packages esptool

# bundle the flashable firmware for the Flasher
sudo mkdir -p /usr/local/share/acid-firmware/pico-badusb
sudo cp firmware/esp32-allinone/prebuilt/esp32-allinone.merged.bin /usr/local/share/acid-firmware/
sudo cp firmware/circuitpython/circuitpython-pico2w.uf2            /usr/local/share/acid-firmware/
sudo cp firmware/pico-badusb/code.py firmware/pico-badusb/boot.py  /usr/local/share/acid-firmware/pico-badusb/
sudo cp -r firmware/pico-badusb/lib                                /usr/local/share/acid-firmware/pico-badusb/
```

The Pico's AP **SSID + password** are set in the Flasher (or the Bad USB app's
**AP creds** screen) — they are written onto the Pico *and* saved to a shared store
(`~/.acid_ap.json`, 0600), so the Bad USB **CONNECT** joins exactly what you flashed.
A blank Pico gets the bundled CircuitPython `.uf2` (hold BOOTSEL while plugging in);
a Pico already on CircuitPython is updated in place. See
[firmware/circuitpython/README.md](firmware/circuitpython/README.md) and
[THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md) for the bundled-binary provenance.

## 9. Adding apps (plugins)

- **Python plugin:** drop a `.py` with a `META = {name, icon, color}` dict and a
  `draw(d, ctx)` function into `/usr/local/lib/acid-apps/` (optionally `on_enter`,
  `handle_touch`). See [apps/packets.py](apps/packets.py).
- **Native plugin (any language):** drop a folder with an `app.json` manifest +
  an executable into `/usr/local/lib/acid-apps/`. See
  [apps/hello-native/](apps/hello-native/) for the contract and a template.

## Troubleshooting

- **Service `active` but TFT blank** — display overlay missing/wrong in step 3;
  fix `config.txt`, `sudo reboot`.
- **`ModuleNotFoundError: PIL` / `numpy` in the log** — the apt deps (step 4) aren't
  installed for the system python. `sudo apt install python3-pil python3-numpy`.
- **IR / Sub-GHz / GPS plugin says "pyserial missing"** — `sudo apt install python3-serial`.
- **Flasher: "esptool not installed"** — it was pip-installed into your *login* account,
  not the system, so the root launcher can't see it. Reinstall system-wide (step 8).
- **Bad USB CONNECT: "AP connected but Pico not responding"** — the Pi and Pico radios
  are too close and saturate the RX front-end. Power the Pico from its own source
  ~2–3 ft away. (The Pico + firmware are fine — it's an RF-proximity issue.)
- **First boot never comes up / boot loops** — reflash (step 1) with a known-good SD card
  and a 5V/2.5A+ supply; confirm you flashed the **64-bit** image and did **not** run
  `apt-get upgrade`.

## Notes

- The launcher uses the pwnagotchi default bettercap credentials
  (`pwnagotchi:pwnagotchi`) — change them in your pwnagotchi config and update the
  constant if you harden the device.
- Code lives in system paths (`/usr/local/bin`, `/usr/local/lib/acid-apps`,
  `/usr/local/lib/acid-ble`, `/usr/local/share/acid-firmware`) and runs as **root**
  under systemd via the system `python3` — nothing depends on a per-user home or venv.
- Runtime data is written under the login user's home: IR captures in `~/acid_ir_saved/`,
  wardrive CSVs in `~/acid_wardrive/`, Bad USB payloads in `~/acid_badusb/`, and the
  shared Pico AP creds in `~/.acid_ap.json` (0600).
