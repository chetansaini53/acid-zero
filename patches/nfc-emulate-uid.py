#!/usr/bin/env python3
"""Patch libnfc 1.8.0's examples/nfc-emulate-uid.c to accept two extra options:

    -a ATQA   ATQA to present (4 hex digits, nfc-list display order, e.g. 0044)
    -s SAK    SAK  to present (2 hex digits, e.g. 00 for NTAG, 08 for Classic 1K)

Stock nfc-emulate-uid hard-codes ATQA 0x0004 + SAK 0x08 (Mifare Classic 1K), so an
emulated tag always advertises "Classic" regardless of the real card - which makes a
reader/Flipper report "multiple protocols" when the card is really an NTAG etc. With
these options the Acid Zero NFC app presents the original card's protocol signature so
the reader identifies the correct type. The SAK's ISO14443-A CRC is recomputed with
libnfc's own iso14443a_crc_append() (public API in nfc/nfc.h).

Usage:  python3 nfc-emulate-uid.py path/to/examples/nfc-emulate-uid.c
Idempotency/safety: asserts each anchor is present exactly once, so it fails loudly if
run twice or against a different libnfc version (install.sh treats that as a build skip).
"""
import sys

src = sys.argv[1]
with open(src) as f:
    code = f.read()

# 1) usage text: document the two new options right before the [UID] line
ua = ('  printf("\\t[UID]\\tUID to emulate, specified as 8 HEX digits '
      '(default is DEADBEEF).\\n");')
uadd = (
    '  printf("\\t-a ATQA\\tATQA to present, 4 HEX digits in nfc-list display order '
    '(e.g. 0044). Default 0004.\\n");\n'
    '  printf("\\t-s SAK\\tSAK to present, 2 HEX digits (00=NTAG/Ultralight, 08=Classic 1K, '
    '20=ISO14443-4). Default 08.\\n");\n'
    + ua)
assert code.count(ua) == 1, 'usage anchor not found exactly once'
code = code.replace(ua, uadd)

# 2) argument loop: add -a / -s branches before the UID branch
xa = ('    } else if ((arg == argc - 1) && (strlen(argv[arg]) == 8)) '
      '{         // See if UID was specified as HEX string')
xadd = (
    '    } else if ((0 == strcmp(argv[arg], "-a")) && (arg + 1 < argc) && '
    '(strlen(argv[arg + 1]) == 4)) {\n'
    '      // ATQA given in nfc-list display order (e.g. 0044); the anti-collision wire\n'
    '      // order is byte-reversed, so swap the two bytes into abtAtqa.\n'
    '      char *pa = argv[++arg];\n'
    '      uint8_t abtT[3] = { 0x00, 0x00, 0x00 };\n'
    '      uint8_t b0, b1;\n'
    '      memcpy(abtT, pa, 2);     b0 = (uint8_t) strtol((char *) abtT, NULL, 16);\n'
    '      memcpy(abtT, pa + 2, 2); b1 = (uint8_t) strtol((char *) abtT, NULL, 16);\n'
    '      abtAtqa[0] = b1; abtAtqa[1] = b0;\n'
    '      printf("[+] Using ATQA: %s\\n", pa);\n'
    '    } else if ((0 == strcmp(argv[arg], "-s")) && (arg + 1 < argc) && '
    '(strlen(argv[arg + 1]) == 2)) {\n'
    '      // SAK byte; recompute its ISO14443-A CRC for the Select-Tag response.\n'
    '      char *ps = argv[++arg];\n'
    '      uint8_t abtT[3] = { 0x00, 0x00, 0x00 };\n'
    '      memcpy(abtT, ps, 2);\n'
    '      abtSak[0] = (uint8_t) strtol((char *) abtT, NULL, 16);\n'
    '      iso14443a_crc_append(abtSak, 1);\n'
    '      printf("[+] Using SAK: %s\\n", ps);\n'
    + xa)
assert code.count(xa) == 1, 'uid-branch anchor not found exactly once'
code = code.replace(xa, xadd)

with open(src, 'w') as f:
    f.write(code)
print('nfc-emulate-uid patched (ATQA/SAK options)')
