# CircuitPython runtime for the Pico 2 W (Bad USB co-processor)

`circuitpython-pico2w.uf2` is the **CircuitPython** firmware image that the
Acid Zero on-device **Flasher** writes to a blank Raspberry Pi Pico 2 W before
copying the Bad USB `code.py` + `lib/`. It is bundled here so the whole flash
works from the handheld with **no laptop and nothing to download**.

| | |
|---|---|
| Board | Raspberry Pi Pico 2 W (RP2350, `raspberry_pi_pico2_w`) |
| Version | CircuitPython **10.2.1** (en_US) |
| Size | 2,937,344 bytes (5737 × 512-byte UF2 blocks) |
| Source | Official CircuitPython CDN — https://downloads.circuitpython.org/bin/raspberry_pi_pico2_w/en_US/adafruit-circuitpython-raspberry_pi_pico2_w-en_US-10.2.1.uf2 |
| License | MIT — © Adafruit Industries and CircuitPython contributors |

This is the **unmodified** upstream binary, redistributed under the MIT license.
CircuitPython is a trademark of Adafruit Industries. Project: https://circuitpython.org

To update: download a newer `raspberry_pi_pico2_w` `.uf2` from the link above,
replace this file, and keep the version note in sync. The Flasher only needs the
`.uf2` for a **virgin** Pico (BOOTSEL); a Pico already running CircuitPython is
updated in place (code + `settings.toml`) without it.
