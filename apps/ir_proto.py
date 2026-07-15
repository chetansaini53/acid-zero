# Acid Zero - IR codec + Flipper .ir interop (pure Python, no hardware / no serial).
#
# * Reads & writes Flipper Zero .ir files (parsed protocols + raw), so any Flipper
#   remote database drops straight into Acid Zero and vice-versa.
# * Encodes parsed protocols (NEC / NECext / Samsung) to raw microsecond timing so
#   EVERYTHING transmits via one reliable path: IR_TX_RAW (same lesson as Sub-GHz -
#   raw always works; protocol decode is a convenience label on top).
# * Ships a universal-remote PRESET library (common TV power/volume codes).
#
# Educational / own-lab use only.

FLIPPER_HEADER = "Filetype: IR signals file\nVersion: 1"

# ---- NEC family timing (microseconds), 38 kHz carrier ----
NEC_HDR_MARK, NEC_HDR_SPACE = 9000, 4500
NEC_BIT_MARK = 560
NEC_ONE_SPACE, NEC_ZERO_SPACE = 1690, 560
SAM_HDR_MARK, SAM_HDR_SPACE = 4500, 4500
DEFAULT_FREQ = 38000


# ---------------- Flipper hex-byte helpers ----------------
def hexbytes_to_int(s):
    """Flipper stores little-endian hex bytes: '04 00 00 00' -> 0x04."""
    parts = [p for p in str(s).split() if p]
    v = 0
    for i, p in enumerate(parts):
        v |= (int(p, 16) & 0xFF) << (8 * i)
    return v


def int_to_hexbytes(v, n=4):
    """int -> Flipper little-endian 4-byte string: 4 -> '04 00 00 00'."""
    return ' '.join('%02X' % ((int(v) >> (8 * i)) & 0xFF) for i in range(n))


# ---------------- protocol encoders (parsed -> raw us) ----------------
def _lsb_bits(byte):
    return [(byte >> i) & 1 for i in range(8)]   # LSB first (NEC order)


def nec_encode(address, command, ext=False):
    """NEC / NEC-extended -> raw microsecond pulse list (mark,space,mark,...)."""
    out = [NEC_HDR_MARK, NEC_HDR_SPACE]
    if ext:                                   # 16-bit addr, no inverse
        bits = _lsb_bits(address & 0xFF) + _lsb_bits((address >> 8) & 0xFF)
    else:                                     # 8-bit addr + inverse
        bits = _lsb_bits(address & 0xFF) + _lsb_bits((~address) & 0xFF)
    bits += _lsb_bits(command & 0xFF) + _lsb_bits((~command) & 0xFF)
    for b in bits:
        out.append(NEC_BIT_MARK)
        out.append(NEC_ONE_SPACE if b else NEC_ZERO_SPACE)
    out.append(NEC_BIT_MARK)                  # final stop mark
    return out


def samsung_encode(address, command):
    """Samsung 32-bit (4.5ms leader, addr+addr, cmd+~cmd) -> raw us."""
    out = [SAM_HDR_MARK, SAM_HDR_SPACE]
    bits = _lsb_bits(address & 0xFF) + _lsb_bits(address & 0xFF)
    bits += _lsb_bits(command & 0xFF) + _lsb_bits((~command) & 0xFF)
    for b in bits:
        out.append(NEC_BIT_MARK)
        out.append(NEC_ONE_SPACE if b else NEC_ZERO_SPACE)
    out.append(NEC_BIT_MARK)
    return out


# ---------------- signal model ----------------
# A signal is a dict:
#   {'name','type':'parsed', 'protocol', 'address', 'command'}   (address/command = int)
#   {'name','type':'raw',    'frequency', 'duty', 'data':[int,...]}
def signal_to_raw(sig):
    """Return (frequency, [us,...]) ready for IR_TX_RAW. None if not encodable."""
    t = sig.get('type')
    if t == 'raw':
        return sig.get('frequency', DEFAULT_FREQ), list(sig.get('data', []))
    if t == 'parsed':
        p = (sig.get('protocol') or '').upper()
        a, c = int(sig.get('address', 0)), int(sig.get('command', 0))
        if p == 'NEC':      return DEFAULT_FREQ, nec_encode(a, c)
        if p == 'NECEXT':   return DEFAULT_FREQ, nec_encode(a, c, ext=True)
        if p == 'SAMSUNG32': return DEFAULT_FREQ, samsung_encode(a, c)
    return None


# ---------------- Flipper .ir read / write ----------------
def parse_ir(text):
    """Parse Flipper .ir text -> list of signal dicts. Ignores unknown keys."""
    sigs, cur = [], None

    def flush():
        if cur and cur.get('name'):
            sigs.append(cur)

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('Filetype') or line.startswith('Version'):
            continue
        if line == '#':
            flush()
            cur = None
            continue
        if ':' not in line:
            continue
        k, v = line.split(':', 1)
        k, v = k.strip().lower(), v.strip()
        if k == 'name':
            flush()
            cur = {'name': v, 'type': 'raw'}
        elif cur is None:
            continue
        elif k == 'type':
            cur['type'] = 'parsed' if v.startswith('parsed') else 'raw'
        elif k == 'protocol':
            cur['protocol'] = v; cur['type'] = 'parsed'
        elif k == 'address':
            cur['address'] = hexbytes_to_int(v)
        elif k == 'command':
            cur['command'] = hexbytes_to_int(v)
        elif k == 'frequency':
            try: cur['frequency'] = int(v)
            except ValueError: cur['frequency'] = DEFAULT_FREQ
        elif k == 'duty_cycle':
            try: cur['duty'] = float(v)
            except ValueError: cur['duty'] = 0.33
        elif k == 'data':
            cur['data'] = [int(x) for x in v.split() if x.lstrip('-').isdigit()]
    flush()
    return sigs


def dump_ir(sigs):
    """Serialize signal dicts -> Flipper .ir text."""
    out = [FLIPPER_HEADER]
    for s in sigs:
        out.append('#')
        out.append('name: %s' % s.get('name', 'sig'))
        if s.get('type') == 'parsed':
            out.append('type: parsed')
            out.append('protocol: %s' % s.get('protocol', 'NEC'))
            out.append('address: %s' % int_to_hexbytes(s.get('address', 0)))
            out.append('command: %s' % int_to_hexbytes(s.get('command', 0)))
        else:
            out.append('type: raw')
            out.append('frequency: %d' % s.get('frequency', DEFAULT_FREQ))
            out.append('duty_cycle: %.6f' % s.get('duty', 0.330000))
            out.append('data: %s' % ' '.join(str(int(x)) for x in s.get('data', [])))
    return '\n'.join(out) + '\n'


# ---------------- universal-remote PRESET library ----------------
# Common TV/appliance codes (public remote codes). Parsed -> encoded to raw at TX.
PRESETS = [
    {'name': 'TV Power (NEC 0x04/0x08)',   'type': 'parsed', 'protocol': 'NEC', 'address': 0x04, 'command': 0x08},
    {'name': 'Samsung TV Power',           'type': 'parsed', 'protocol': 'Samsung32', 'address': 0x07, 'command': 0x02},
    {'name': 'LG TV Power (NEC)',          'type': 'parsed', 'protocol': 'NEC', 'address': 0x04, 'command': 0x08},
    {'name': 'Vol+ (NEC 0x04/0x02)',       'type': 'parsed', 'protocol': 'NEC', 'address': 0x04, 'command': 0x02},
    {'name': 'Vol- (NEC 0x04/0x03)',       'type': 'parsed', 'protocol': 'NEC', 'address': 0x04, 'command': 0x03},
    {'name': 'Mute (NEC 0x04/0x09)',       'type': 'parsed', 'protocol': 'NEC', 'address': 0x04, 'command': 0x09},
]


def preset_names():
    return [p['name'] for p in PRESETS]
