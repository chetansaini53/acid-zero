# Install / Setup

> ⚠️ For **authorized, own-lab, educational** use only. See [ETHICS.md](ETHICS.md).

Acid Zero runs as a touchscreen UI layer on top of a
[jayofelony pwnagotchi](https://github.com/jayofelony/pwnagotchi) install on a
**Raspberry Pi 3B+** with a **3.5" ILI9486 SPI TFT + ADS7846 touch**.

## 1. Base OS

Flash the jayofelony pwnagotchi image to the Pi 3B+ and complete its first boot.
The launcher reuses pwnagotchi's bettercap REST API for Wi-Fi recon, so a working
pwnagotchi is the foundation.

## 2. Display + touch (device tree)

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
boot-order reshuffles don't break it.

> SPI0 is fully used by the display + touch. For a future **CC1101 sub-GHz** add-on
> use **SPI1**; for a **PN532 NFC/RFID** add-on use the free **I2C-1** bus.
> See [docs/hardware-reference.pdf](docs/hardware-reference.pdf) for the full porting map.

## 3. Dependencies

```
sudo apt update
sudo apt install -y python3-pil python3-numpy aircrack-ng hcxtools hostapd dnsmasq bluez
```

- `python3-pil` (Pillow) + `python3-numpy` — UI rendering + touch calibration
- `aircrack-ng` (airodump-ng / aireplay-ng) + `hcxtools` (hcxpcapngtool) — handshake capture/convert
- `hostapd` + `dnsmasq` — Evil Portal rogue AP + captive portal
- `bluez` (btmgmt / btmon) — BLE scan + spam
- `bettercap` — already provided by pwnagotchi

## 4. Deploy the files

```
# launcher (acidzero.py + its sibling client libs: acid_ir.py, acid_subghz.py,
# acid_gps.py, acid_badusb.py, acid_wifiroles.py - plugins import these by name,
# expecting them next to acidzero.py)
sudo cp launcher/*.py                    /usr/local/bin/
# helper scripts
sudo cp scripts/*.sh scripts/*.py       /usr/local/bin/
sudo chmod +x /usr/local/bin/acid-*.sh /usr/local/bin/acid-*.py /usr/local/bin/acidzero.py
# BLE library
sudo mkdir -p /usr/local/lib/acid-ble
sudo cp -r lib/acid-ble/*               /usr/local/lib/acid-ble/
# apps (plugins)
sudo mkdir -p /usr/local/lib/acid-apps
sudo cp -r apps/*                        /usr/local/lib/acid-apps/
# native-app executables (hello-native, wardrive-csv, ...) must be runnable
sudo chmod +x /usr/local/lib/acid-apps/*/*  2>/dev/null || true
# systemd units
sudo cp systemd/*                        /etc/systemd/system/
```

## 5. Enable services

```
sudo systemctl daemon-reload
sudo systemctl enable --now acidzero.service          # the touchscreen UI
sudo systemctl enable --now acid-hs-clean.timer       # periodic handshake validation
```

The TFT should now boot straight into the Acid Zero launcher.

## 6. Co-processors (Sub-GHz / IR + Bad USB)

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
# The launcher runs as root, so an "--user" install in your login account is NOT
# enough; install into the system site-packages:
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

## 7. Adding apps (plugins)

- **Python plugin:** drop a `.py` with a `META = {name, icon, color}` dict and a
  `draw(d, ctx)` function into `/usr/local/lib/acid-apps/` (optionally `on_enter`,
  `handle_touch`). See [apps/packets.py](apps/packets.py).
- **Native plugin (any language):** drop a folder with an `app.json` manifest +
  an executable into `/usr/local/lib/acid-apps/`. See
  [apps/hello-native/](apps/hello-native/) for the contract and a template.

## Notes

- The launcher uses the pwnagotchi default bettercap credentials
  (`pwnagotchi:pwnagotchi`) — change them in your pwnagotchi config and update the
  constant if you harden the device.
- Paths assume the pwnagotchi default user home `/home/pi`.
