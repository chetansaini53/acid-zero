# Acid Zero — ESP32 Sub-GHz Co-Processor (CC1101)

This folder is the **radio brain** of Acid Zero. The Raspberry Pi owns the UI; a dedicated
**ESP32-WROOM-32** owns the **CC1101** sub-GHz transceiver and talks to the Pi over **USB
serial @ 115200**. Moving the radio off the Pi is deliberate — raw OOK timing needs the
ESP32's **RMT peripheral** for microsecond-precise edge capture, which a preempted Linux
userspace process cannot guarantee. See [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for the
full rationale.

```
firmware/
├── esp32-cc1101/
│   ├── esp32-cc1101.ino                 # the firmware source (build from this)
│   └── prebuilt/
│       └── esp32-cc1101.merged.bin      # ready-to-flash image (flash at 0x0)
├── flash-windows.bat                    # one-command flash (Windows)
├── flash-pi.sh                          # one-command flash (Raspberry Pi / Linux)
└── README.md                            # this file
```

---

## 1. Wiring — CC1101 → ESP32

Connect the CC1101 to the ESP32 **before** powering up. The ESP32 drives the CC1101 on its
own SPI bus (no display to contend with).

| CC1101 pin | ESP32 board label | ESP32 GPIO |
|-----------|-------------------|-----------|
| VCC       | **3V3** (never 5V) | — |
| GND       | GND               | — |
| SCK       | D18               | GPIO18 |
| **MOSI / SI** | **D19**       | **GPIO19** |
| **MISO / SO** | **D23**       | **GPIO23** |
| CSN       | D5                | GPIO5  |
| GDO0      | D4                | GPIO4  |
| GDO2      | — (not connected) | — |

> ⚠️ **MOSI=D19, MISO=D23** — these two look "crossed" versus the naïve mapping. Swapping
> them is the classic failure where `VER` reads `0x00`. This pin map is brute-force verified
> and matches the constants in the firmware. Wire it exactly.

---

## 2. Flash the prebuilt firmware (fastest)

No toolchain needed — just [esptool](https://github.com/espressif/esptool) and the merged
binary in `prebuilt/`. The merged image is a full flash image; write it at offset `0x0`.

```
pip install esptool
```

**Windows** (replace `COM6` with your port — check Device Manager → Ports):

```
flash-windows.bat COM6
```

…or directly:

```
esptool --chip esp32 -p COM6 -b 921600 write_flash 0x0 esp32-cc1101\prebuilt\esp32-cc1101.merged.bin
```

**Raspberry Pi / Linux** (replace `/dev/ttyUSB0` with your port — `ls /dev/ttyUSB*`):

```
./flash-pi.sh /dev/ttyUSB0
```

…or directly:

```
esptool --chip esp32 -p /dev/ttyUSB0 -b 921600 write_flash 0x0 esp32-cc1101/prebuilt/esp32-cc1101.merged.bin
```

> If `esptool` isn't on your PATH, use `python -m esptool ...` with the same arguments.

---

## 3. Build from source (optional)

Uses [`arduino-cli`](https://arduino.github.io/arduino-cli/). One-time setup, then compile +
upload.

```
arduino-cli core install esp32:esp32
arduino-cli lib install "SmartRC-CC1101-Driver-Lib"
```

Compile and upload (**Windows** — use `COM6`):

```
arduino-cli compile --fqbn esp32:esp32:esp32 esp32-cc1101
arduino-cli upload -p COM6 --fqbn esp32:esp32:esp32 esp32-cc1101
```

Compile and upload (**Raspberry Pi / Linux** — use `/dev/ttyUSB0`):

```
arduino-cli compile --fqbn esp32:esp32:esp32 esp32-cc1101
arduino-cli upload -p /dev/ttyUSB0 --fqbn esp32:esp32:esp32 esp32-cc1101
```

Build settings (already encoded in the prebuilt image): `flash-mode dio · flash-freq 80m ·
flash-size 4MB`, default partition scheme.

---

## 4. Verify it's alive

Open a serial monitor at **115200 baud** (`arduino-cli monitor -p COM6 -c baudrate=115200`,
or any terminal). On boot the firmware prints a banner; then type:

```
VER
```

A working board replies with the CC1101 chip id:

```
VER partnum=0x00 version=0x14 present=YES
```

`version=0x14` (or `0x04`) + `present=YES` = the CC1101 is wired and alive. `0x00`/`0xFF` +
`present=NO` ⇒ recheck **3.3 V power** and the **four SPI wires** (most often MOSI/MISO).

---

## 5. Connect to the Raspberry Pi

Plug the ESP32 into the Pi over USB. The Pi-side client
([`../launcher/acid_subghz.py`](../launcher/acid_subghz.py)) **auto-detects** the port — it
probes each `/dev/ttyUSB*` with `PING` and keeps the one that answers `PONG`, opening it with
DTR/RTS de-asserted so the ESP32 isn't reset on connect. Nothing to configure; the **Sub-GHz**
app in the launcher drives everything from the touch UI.

---

## 6. Serial command reference

Line-based ASCII, one command per line, 115200 baud. Every command returns a one-line (or
short multi-line) reply — human-debuggable from any serial monitor.

| Command | Reply | Purpose |
|---------|-------|---------|
| `PING` | `PONG` | liveness / port auto-detection |
| `VER` | `VER partnum=.. version=0x14 present=YES` | confirm the CC1101 is alive |
| `INFO` | pins · freq · profile · mod · rxbw · drate | current config |
| `FREQ <mhz>` | `FREQ set <mhz>` | set frequency (280–950 MHz) |
| `RSSI` | `RSSI <mhz> = <dbm>` | one RSSI reading |
| `SCAN` | per-freq RSSI across 315/433.92/868/915 | quick band check |
| `ANALYZE` | per-freq peak RSSI + `peak=<mhz>` | frequency analyzer (peak-hold sweep) |
| `WATCH <sec>` | streamed RSSI + ASCII bar | live signal hunt |
| `MOD <profile>` | applied profile | switch modulation preset |
| `SET_CONFIG --freq --mod --drate --dev --rxbw --rssi` | echo of the new config | custom override |
| `CLASSIFY` | RSSI-swing heuristic → ASK/OOK vs FSK | identify modulation type |
| `CAPTURE [s]` | `CAP n=<count>` + `CAPDATA <us...>` | RMT raw-OOK capture (full timing) |
| `LOAD <us...>` | `LOAD n=<count>` | load a saved signal into the TX buffer |
| `REPLAY [x]` | `REPLAY done` | transmit the loaded/last signal x times |

### Modulation profiles

| Profile | Modulation | RX BW | Data rate | Use |
|---------|-----------|-------|-----------|-----|
| `AM_DEFAULT` | ASK/OOK | 162 kHz | 2.4 kbps | clean baseline |
| `AM_WIDE` | ASK/OOK | 650 kHz | 4.0 kbps | wide remotes (AM650) |
| `AM_NARROW` | ASK/OOK | 270 kHz | 3.8 kbps | AM270 remotes |
| `FM_FSK` | 2-FSK | 270 kHz | 5.0 kbps, dev 47.6 kHz | FM remotes |

---

## ⚠️ Authorized use only

`REPLAY` and `SET_TX` **transmit RF**. Transmit **only** on your own devices / authorized test
gear, in a controlled lab, on a frequency that is legal to transmit on in your region. See
[`../ETHICS.md`](../ETHICS.md). Educational / authorized-lab use only.
