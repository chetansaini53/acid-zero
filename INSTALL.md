# Install / Setup

> ⚠️ For **authorized, own-lab, educational** use only. See [ETHICS.md](ETHICS.md).

Acid Zero runs as a touchscreen UI layer on top of a
[jayofelony pwnagotchi](https://github.com/jayofelony/pwnagotchi) install on a
**Raspberry Pi 3B+** with a **3.5" ILI9486 SPI TFT + ADS7846 touch**.

Everything below is a clean, reproducible path: flash a fresh card, follow the steps
in order, and the Pi boots straight into the launcher. All commands run **on the Pi**.

## 1. Base OS

Flash the jayofelony pwnagotchi image to the Pi 3B+ and complete its first boot.
The launcher reuses pwnagotchi's bettercap REST API for Wi-Fi recon, so a working
pwnagotchi is the foundation.

The image builds pwnagotchi inside a Python **venv at `/home/pi/.pwn`** (created with
`--system-site-packages`). Acid Zero runs its launcher through that same interpreter —
remember this path, step 6 depends on it.

> **Custom username?** If you set a login other than `pi` when flashing, the venv is at
> `/home/<youruser>/.pwn`. Edit the `ExecStart=` line in `systemd/acidzero.service`
> (step 4) to match **before** you copy it.

## 2. Get the code

On the booted Pi:

```
git clone https://github.com/chetansaini53/acid-zero.git
cd acid-zero          # every path below is relative to this repo root
```

## 3. Display + touch (device tree)

Add to `/boot/firmware/config.txt` (paths/values from a working build):

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
boot-order reshuffles don't break it. Reboot after editing `config.txt`.

> SPI0 is fully used by the display + touch. For a future **CC1101 sub-GHz** add-on
> use **SPI1**; for a **PN532 NFC/RFID** add-on use the free **I2C-1** bus.
> See [docs/hardware-reference.pdf](docs/hardware-reference.pdf) for the full porting map.

## 4. Dependencies

```
sudo apt update
sudo apt install -y python3-pil python3-numpy aircrack-ng hcxtools hostapd dnsmasq bluez
```

- `python3-pil` (Pillow) + `python3-numpy` — UI rendering + touch calibration
- `aircrack-ng` (airodump-ng / aireplay-ng) + `hcxtools` (hcxpcapngtool) — handshake capture/convert
- `hostapd` + `dnsmasq` — Evil Portal rogue AP + captive portal
- `bluez` (btmgmt / btmon) — BLE scan + spam
- `bettercap` — already provided by pwnagotchi

Installed via `apt`, these land in the system site-packages — and because the `.pwn`
venv is `--system-site-packages`, the launcher (which runs through that venv) sees
them without a separate `pip install`.

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

Everything lives in system paths and the service runs as **root** — the only
per-user assumption is the `.pwn` venv path in `acidzero.service` (step 1's note).

## 6. Enable services

```
sudo systemctl daemon-reload
sudo systemctl enable --now acidzero.service          # the touchscreen UI
sudo systemctl enable --now acid-hs-clean.timer       # periodic handshake validation
```

`acidzero.service` launches the UI via `/home/pi/.pwn/bin/python3 /usr/local/bin/acidzero.py`
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
# esptool for the ESP32 flash - install where the launcher (root) can see it.
# The launcher runs through the .pwn venv, which is --system-site-packages, so a
# SYSTEM-wide install is visible to it; a plain "pip install --user" in your login
# account is NOT. Install system-wide:
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
- **`ModuleNotFoundError: PIL` / `numpy` in the log** — the `ExecStart` isn't using
  the `.pwn` venv, or the venv wasn't built `--system-site-packages`. Check the
  `ExecStart=` path and `grep system-site /home/pi/.pwn/pyvenv.cfg`.
- **Flasher: "esptool not installed"** — it was pip-installed into your *login*
  account, not the system, so the root launcher can't see it. Reinstall system-wide
  (step 8).
- **Bad USB CONNECT: "AP connected but Pico not responding"** — the Pi and Pico radios
  are too close and saturate the RX front-end. Power the Pico from its own source
  ~2–3 ft away. (The Pico + firmware are fine — it's an RF-proximity issue.)

## Notes

- The launcher uses the pwnagotchi default bettercap credentials
  (`pwnagotchi:pwnagotchi`) — change them in your pwnagotchi config and update the
  constant if you harden the device.
- Code lives in system paths (`/usr/local/bin`, `/usr/local/lib/acid-apps`,
  `/usr/local/lib/acid-ble`, `/usr/local/share/acid-firmware`) and runs as **root**
  under systemd. The only per-user value is the `.pwn` venv path in `acidzero.service`.
- Runtime data is written under the pwnagotchi user's home: IR captures in
  `~/acid_ir_saved/`, wardrive CSVs in `~/acid_wardrive/`, Bad USB payloads in
  `~/acid_badusb/`, and the shared Pico AP creds in `~/.acid_ap.json` (0600).
