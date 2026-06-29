# Samsung EasySetup / Buds-Watch popups (manufacturer 0x0075).
# EXTEND: add a device id (2 bytes) + label to DEVICES.
import random

DEVICES = [
    (0xe625, "Galaxy Buds"), (0x9125, "Buds Live"), (0x012a, "Buds Pro"),
    (0x01a5, "Watch4"),      (0x0a02, "Watch5"),
]

def _rb(n):
    return bytes([random.randint(0, 255) for _ in range(n)])

def random_packet():
    d, name = random.choice(DEVICES)
    # Samsung EasySetup BLE frame (manufacturer 75 00) advertising a watch/buds setup
    adv = bytes([0x02, 0x01, 0x18, 0x1b, 0xff, 0x75, 0x00, 0x42, 0x09, 0x81, 0x02, 0x14,
                 0x15, 0x03, 0x21, 0x01, 0x09, (d >> 8) & 0xff, d & 0xff, 0x01]) + _rb(4) + bytes([0x06, 0x3c, 0x94, 0x8e])
    return ('Samsung/' + name, adv)
