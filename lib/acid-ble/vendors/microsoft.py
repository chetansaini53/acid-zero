# Microsoft Swift Pair popups (Windows "new Bluetooth device" toast). manufacturer 0x0006.
# This is the one that already worked. EXTEND: change NAMES (shown in the Windows toast).
import random

NAMES = ["ACID Mouse", "ACID Keyboard", "ACID Headset", "Surface Pen", "Xbox Controller"]

def _rb(n):
    return bytes([random.randint(0, 255) for _ in range(n)])

def random_packet():
    nm = random.choice(NAMES)
    name_b = nm.encode('ascii', 'ignore')[:18]
    # mfg-data (FF 06 00) Swift Pair (03 00 80) + display name
    body = bytes([0x06, 0x00, 0x03, 0x00, 0x80]) + name_b
    adv = bytes([len(body) + 1, 0xff]) + body
    return ('Windows/' + nm, adv)
