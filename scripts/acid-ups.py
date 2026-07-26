#!/usr/bin/env python3
"""
Acid Zero - UPS monitor for the Waveshare UPS HAT (D).

Reads the on-board INA219 (I2C 0x43) every few seconds, publishes battery state
to /run/acid_ups (the launcher's home screen reads it), and does a safe auto
shutdown on low battery so an unattended field unit never corrupts its SD card
when the 21700 cell runs flat.

On low-battery shutdown it first sets the UPS MCU (0x2D) register 0x01 = 0x55, so
the pack auto-boots the Pi (via the GPIO3-low wake) once external power returns -
exactly the sequence in Waveshare's own INA219.py demo.

Runs as root under systemd (needs I2C + poweroff). Degrades quietly if the HAT
is absent (I2C errors) instead of crash-looping.
"""
import json
import os
import subprocess
import time

try:
    import smbus  # python3-smbus
except Exception:
    smbus = None

I2C_BUS = 1
INA219_ADDR = 0x43
MCU_ADDR = 0x2D
STATE_FILE = "/run/acid_ups"

# --- INA219 registers (subset; matches Waveshare UPS HAT (D) demo) ---
_REG_CONFIG = 0x00
_REG_BUSVOLTAGE = 0x02
_REG_CURRENT = 0x04
_REG_CALIBRATION = 0x05

# Low-battery safe-shutdown thresholds (from Waveshare's tested demo).
LOW_VOLT = 3.15          # V, load-side bus voltage
LOW_CUR = 50             # mA; below this = not meaningfully charging
POLL_SEC = 2
LOW_TICKS = 30           # 30 * 2s = ~60s of sustained low before shutdown


class INA219:
    """Minimal INA219 driver for the UPS HAT (D) (16V / 5A calibration)."""

    def __init__(self, bus, addr=INA219_ADDR):
        self.bus = bus
        self.addr = addr
        self._cal = 26868           # 16V/5A cal value (Waveshare)
        self._cur_lsb = 0.1524      # mA per bit
        self._calibrate()

    def _read(self, reg):
        d = self.bus.read_i2c_block_data(self.addr, reg, 2)
        return (d[0] << 8) | d[1]

    def _write(self, reg, val):
        self.bus.write_i2c_block_data(self.addr, reg, [(val >> 8) & 0xFF, val & 0xFF])

    def _calibrate(self):
        self._write(_REG_CALIBRATION, self._cal)
        # 16V range, gain /2 (80mV), 12-bit 32-sample, shunt+bus continuous
        cfg = (0x00 << 13) | (0x01 << 11) | (0x0D << 7) | (0x0D << 3) | 0x07
        self._write(_REG_CONFIG, cfg)

    def bus_voltage(self):
        self._write(_REG_CALIBRATION, self._cal)
        self._read(_REG_BUSVOLTAGE)
        return (self._read(_REG_BUSVOLTAGE) >> 3) * 0.004

    def current_mA(self):
        v = self._read(_REG_CURRENT)
        if v > 32767:
            v -= 65535
        return v * self._cur_lsb


def _percent(volt):
    p = (volt - 3.0) / 1.2 * 100.0     # 3.0V=0%, 4.2V=100% (Li 21700)
    return max(0, min(100, int(round(p))))


def _publish(pct, volt, charging, present):
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump({"pct": pct, "v": round(volt, 2),
                       "chg": bool(charging), "present": bool(present)}, f)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


def _enable_boot_on_power(bus):
    """Tell the UPS MCU to re-boot the Pi when external power returns."""
    try:
        bus.write_byte_data(MCU_ADDR, 0x01, 0x55)
    except Exception:
        pass


def main():
    if smbus is None:
        _publish(0, 0.0, False, False)
        return
    try:
        bus = smbus.SMBus(I2C_BUS)
    except Exception:
        _publish(0, 0.0, False, False)
        return

    ina = None
    low = 0
    while True:
        try:
            if ina is None:
                ina = INA219(bus)
            volt = ina.bus_voltage()
            cur = -ina.current_mA()                 # +ve = charging, -ve = load
            pct = _percent(volt)
            charging = cur > 30
            _publish(pct, volt, charging, True)

            if volt < LOW_VOLT and cur < LOW_CUR:
                low += 1
                if low >= LOW_TICKS:
                    _enable_boot_on_power(bus)      # auto-boot when power returns
                    time.sleep(1)
                    subprocess.run(["poweroff"], check=False)  # fixed argv, no shell
                    return
            else:
                low = 0
        except Exception:
            # HAT unplugged / I2C glitch: mark absent, retry (never crash-loop out).
            ina = None
            low = 0
            _publish(0, 0.0, False, False)
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
