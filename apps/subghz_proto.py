# Acid Zero - Sub-GHz OOK protocol codec (pure Python, no radio / no PIL / no I/O).
#
# Decodes a captured raw OOK pulse train -> protocol + key, encodes a known key
# back into a replayable pulse train, and round-trip-verifies decode fidelity.
#
# Pulse-train contract (matches the ESP32 firmware capture + replay):
#   list of durations in microseconds, ALTERNATING starting with carrier-ON (HIGH):
#   [hi0, lo0, hi1, lo1, ...]. Replay bit-bangs the same list starting HIGH.
#
# Scope (deliberately honest - see ARCHITECTURE / the design review):
#   * EV1527 / PT2262 "Princeton" 24-bit PWM  -> full decode + encode + verify.
#   * Any other clean PWM frame                -> "PWM Nbit" (decode-only label).
#   * FSK / Manchester / uniform-cell signals  -> not PWM, returns raw-only note.
# We do NOT name protocols we cannot faithfully distinguish or re-transmit
# (CAME vs Nice FLO are indistinguishable on bit-count; KeeLoq is rolling-code).
#
# Educational / own-lab use only.
from collections import Counter, namedtuple

# Canonical EV1527/Princeton timing (microseconds). te = base unit; a "short"
# pulse is te, a "long" pulse is 3*te; the inter-frame sync gap is ~31*te.
EV1527_BITS = 24
DEFAULT_TE = 350
SYNC_MULT = 31
LONG_MULT = 3

# Decode tolerances.
_MIN_PULSES = 16          # below this there is nothing to decode
_SYNC_GAP_MULT = 8        # a LOW >= 8*te delimits frames (inter-frame gap)
_LONG_THR_MULT = 2        # a pulse >= 2*te counts as "long" (vs short ~te)
_UNIFORM_RATIO = 1.7      # if long_cluster < 1.7*te the cells are ~uniform -> not PWM
_ABS_MIN = 30             # ignore sub-30us slivers (noise)
_ABS_MAX = 60000          # ignore absurd > 60ms outliers

ProtoResult = namedtuple(
    'ProtoResult',
    'protocol bits key_hex key_int nbits te repeats confidence note')


def _unknown(note, te=None):
    return ProtoResult('UNKNOWN', '', '', 0, 0, te, 0, 0.0, note)


def normalize(pulses):
    """Coerce to a clean list of positive ints, dropping noise slivers/outliers."""
    out = []
    if not pulses:
        return out
    for x in pulses:
        try:
            v = int(x)
        except (TypeError, ValueError):
            continue
        if _ABS_MIN < v < _ABS_MAX:
            out.append(v)
    return out


def estimate_te(pulses):
    """Estimate the base pulse unit te via a 2-means split (short vs long).

    Robust to the contaminated capture (sync gaps, dead-carrier spikes, the
    400-element truncation): excludes sync-sized gaps, then clusters the core
    durations into two groups and returns the SHORT centroid = te.
    """
    ds = sorted(p for p in pulses if _ABS_MIN < p < _ABS_MAX)
    if len(ds) < 8:
        return None
    lq = ds[len(ds) // 4] or ds[0]            # lower-quartile (robust scale)
    core = [x for x in ds if x <= lq * 6] or ds   # drop inter-frame sync gaps
    lo_c, hi_c = core[0], core[-1]
    if hi_c <= lo_c:
        return float(lo_c)
    for _ in range(20):                       # 2-means
        los = [x for x in core if abs(x - lo_c) <= abs(x - hi_c)]
        his = [x for x in core if abs(x - lo_c) > abs(x - hi_c)]
        if los:
            lo_c = sum(los) / len(los)
        if his:
            hi_c = sum(his) / len(his)
    return float(lo_c)


def _bit_of(hi, lo, long_thr):
    """PWM bit: long-high+short-low = '1', short-high+long-low = '0', else '?'."""
    hi_long = hi >= long_thr
    lo_long = lo >= long_thr
    if hi_long and not lo_long:
        return '1'
    if lo_long and not hi_long:
        return '0'
    return '?'


def _to_frames(pulses, te):
    """Split the alternating stream into per-frame bit strings.

    Cuts on a sync-sized LOW; drops the lone preamble/sync HIGH adjacent to it.
    Works whether the sync leads (EV1527) or trails (PT2262) the data bits.
    """
    long_thr = max(int(round(te * _LONG_THR_MULT)), te + 1)
    sync_thr = int(round(te * _SYNC_GAP_MULT))
    frames, cur = [], ''
    i, n = 0, len(pulses)
    while i + 1 < n:
        hi, lo = pulses[i], pulses[i + 1]
        if lo >= sync_thr:                    # frame boundary
            if cur:
                frames.append(cur)
                cur = ''
            i += 2                            # drop the lone preamble/sync high
            continue
        cur += _bit_of(hi, lo, long_thr)
        i += 2
    if cur:
        frames.append(cur)
    return frames


def _vote(frames):
    """Pick the modal clean frame length, majority-vote each bit, score confidence."""
    clean = [f for f in frames if '?' not in f and len(f) >= 8]
    if not clean:
        return None, 0.0
    modal_len = Counter(len(f) for f in clean).most_common(1)[0][0]
    group = [f for f in clean if len(f) == modal_len]
    bits = ''
    for i in range(modal_len):
        ones = sum(1 for f in group if f[i] == '1')
        bits += '1' if ones * 2 >= len(group) else '0'
    agree = sum(1 for f in group if f == bits)
    return bits, agree / float(len(group))


def _classify(nbits):
    if nbits == EV1527_BITS:
        return 'EV1527'
    if nbits in (64, 66, 67, 68, 69):
        return 'PWM %dbit (rolling? replay may not re-trigger)' % nbits
    return 'PWM %dbit' % nbits


def decode(pulses, profile='AM_NARROW'):
    """Decode a raw OOK pulse list -> ProtoResult (never raises into the caller)."""
    try:
        prof = (profile or '').upper()
        if 'FSK' in prof or 'FM' in prof:
            return _unknown('FSK - raw replay only (not PWM)')
        p = normalize(pulses)
        if len(p) < _MIN_PULSES:
            return _unknown('too short to decode')
        te = estimate_te(p)
        if not te:
            return _unknown('could not estimate base timing')
        # Uniform-cell guard: 1:3 PWM has a clear short/long split; ~equal cells
        # are Manchester/biphase/FSK and must not be force-decoded to a fake key.
        longs = [x for x in p if x >= te * _LONG_THR_MULT and x < te * _SYNC_GAP_MULT]
        if not longs or (sum(longs) / len(longs)) < te * _UNIFORM_RATIO:
            return _unknown('uniform cells - raw only (Manchester/FSK?)', te=int(te))
        frames = _to_frames(p, te)
        if len(frames) >= 3:                  # first/last are usually partial
            frames = frames[1:-1]
        repeats = len(frames)
        bits, conf = _vote(frames)
        if not bits:
            return _unknown('inconsistent frames - no clean decode', te=int(te))
        nbits = len(bits)
        key_int = int(bits, 2)
        key_hex = format(key_int, '0%dX' % ((nbits + 3) // 4))
        proto = _classify(nbits)
        note = '' if proto == 'EV1527' else 'generic PWM (decode-only)'
        return ProtoResult(proto, bits, key_hex, key_int, nbits,
                           int(round(te)), repeats, round(conf, 3), note)
    except Exception as e:                     # render-thread safety: never throw
        return _unknown('decode error: %s' % str(e)[:24])


def encode(key_hex, nbits=EV1527_BITS, te=DEFAULT_TE, repeats=1):
    """Build a replayable EV1527/Princeton pulse train from a hex key.

    Returns a flat list of microsecond durations, alternating, starting HIGH.
    Emits ONE frame per repeat, each ending in the sync gap, so the firmware's
    REPLAY(reps) reproduces a real remote's frame+gap+frame pattern.

    Raises ValueError on invalid input (bad hex, key wider than nbits).
    """
    if isinstance(key_hex, int):
        key = key_hex
    else:
        s = str(key_hex).strip().upper().replace('0X', '')
        if not s or any(c not in '0123456789ABCDEF' for c in s):
            raise ValueError('key must be hexadecimal')
        key = int(s, 16)
    nbits = int(nbits)
    if not (1 <= nbits <= 64):
        raise ValueError('nbits out of range')
    if key >= (1 << nbits):
        raise ValueError('key too large for %d bits' % nbits)
    te = int(te) or DEFAULT_TE
    short, lng, sync = te, te * LONG_MULT, te * SYNC_MULT
    bits = format(key, '0%db' % nbits)
    out = []
    for _ in range(max(1, int(repeats))):
        out.append(short)                      # preamble high
        out.append(sync)                       # inter-frame sync gap (low)
        for b in bits:
            if b == '1':
                out += [lng, short]
            else:
                out += [short, lng]
    # Hard invariants (a violation silently inverts replay polarity):
    if len(out) % 2 != 0:
        raise ValueError('internal: odd-length pulse train')
    return out


def verify(pulses, profile='AM_NARROW'):
    """Round-trip self-test: decode, re-encode, re-decode -> bit-level fidelity.

    Returns (ok: bool, detail: dict). ok=True means the decoded key survives a
    clean encode/decode round-trip and the captured repeats agreed -> "verified".
    """
    d = decode(pulses, profile=profile)
    if d.protocol != 'EV1527':
        return False, {'reason': 'not a re-encodable protocol (%s)' % d.protocol,
                       'decoded': d}
    try:
        re = encode(d.key_hex, d.nbits, d.te or DEFAULT_TE, repeats=1)
    except ValueError as e:
        return False, {'reason': 're-encode failed: %s' % e, 'decoded': d}
    d2 = decode(re, profile=profile)
    ok = (d2.protocol == 'EV1527' and d2.key_hex == d.key_hex and d.confidence >= 0.99)
    return ok, {'key_hex': d.key_hex, 'nbits': d.nbits, 'te': d.te,
                'confidence': d.confidence, 'roundtrip': d2.key_hex, 'decoded': d}


def make_capture(key_hex, nbits=EV1527_BITS, te=DEFAULT_TE, frames=5,
                 jitter=0.0, spikes=0, clip=None, drop_lead=0):
    """Synthetic capture generator for tests (NOT used at runtime).

    Builds `frames` repeats of an EV1527 frame with optional per-edge jitter,
    random-but-deterministic noise spikes in gaps, a clipped tail, and a
    partial leading frame - i.e. what the real capture pipeline produces.
    """
    base = encode(key_hex, nbits, te, repeats=frames)
    out = []
    seed = (int(str(key_hex), 16) if not isinstance(key_hex, int) else key_hex) or 1
    for idx, d in enumerate(base):
        if jitter:
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            frac = (seed / 0x7FFFFFFF) * 2.0 - 1.0          # -1..1
            d = max(_ABS_MIN + 1, int(d * (1.0 + jitter * frac)))
        out.append(d)
    for _ in range(spikes):                                  # dead-carrier noise
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        pos = seed % (len(out) + 1)
        out.insert(pos, _ABS_MIN + 5)
    if drop_lead > 0:
        out = out[drop_lead:]
    if clip is not None:
        out = out[:clip]
    return out
