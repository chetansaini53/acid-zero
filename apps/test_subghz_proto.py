# Tests for subghz_proto - pure logic, NO radio / NO serial.
# Run:  cd apps && python -m unittest test_subghz_proto   (also pytest-compatible)
#
# These prove the OOK codec works without the physical CC1101: synthetic captures
# in -> known key out, plus encode/decode round-trip and fail-safe behaviour.
import random
import unittest

import subghz_proto as sp

KEY = 'A3F1C2'          # an arbitrary 24-bit EV1527 key for the happy-path tests


class TestEncode(unittest.TestCase):
    def test_even_length_and_starts_high(self):
        out = sp.encode(KEY, repeats=1)
        # one frame = preamble(2) + 24 bits * 2 elements = 50
        self.assertEqual(len(out), 2 + sp.EV1527_BITS * 2)
        self.assertEqual(len(out) % 2, 0)                 # invariant: even length
        self.assertEqual(out[0], sp.DEFAULT_TE)           # invariant: starts HIGH (short)

    def test_repeats_multiply(self):
        one = sp.encode(KEY, repeats=1)
        five = sp.encode(KEY, repeats=5)
        self.assertEqual(len(five), len(one) * 5)

    def test_bad_hex_raises(self):
        with self.assertRaises(ValueError):
            sp.encode('ZZ')

    def test_key_too_large_raises(self):
        with self.assertRaises(ValueError):
            sp.encode('FFFFFFF', nbits=24)                # 28 bits into 24

    def test_width_padding_roundtrips(self):
        d = sp.decode(sp.encode('5', nbits=24))           # tiny key -> zero padded
        self.assertEqual(d.protocol, 'EV1527')
        self.assertEqual(d.key_int, 5)
        self.assertEqual(d.key_hex, '000005')


class TestDecodeHappy(unittest.TestCase):
    def test_single_frame(self):
        d = sp.decode(sp.encode(KEY, repeats=1))
        self.assertEqual(d.protocol, 'EV1527')
        self.assertEqual(d.nbits, 24)
        self.assertEqual(d.key_hex, KEY)
        self.assertEqual(d.confidence, 1.0)

    def test_multi_frame_capture(self):
        cap = sp.make_capture(KEY, frames=5)
        d = sp.decode(cap)
        self.assertEqual(d.protocol, 'EV1527')
        self.assertEqual(d.key_hex, KEY)
        self.assertGreaterEqual(d.repeats, 3)

    def test_roundtrip_property_many_keys(self):
        rnd = random.Random(1234)
        for _ in range(300):
            k = rnd.randint(0, (1 << 24) - 1)
            hexk = format(k, '06X')
            d = sp.decode(sp.encode(hexk))
            self.assertEqual(d.key_int, k)

    def test_te_estimation_varied(self):
        for te in (200, 350, 500):
            est = sp.estimate_te(sp.encode(KEY, te=te, repeats=4))
            self.assertLessEqual(abs(est - te) / te, 0.15)   # within 15%


class TestDecodeRobustness(unittest.TestCase):
    def test_jitter_tolerated(self):
        cap = sp.make_capture(KEY, frames=5, jitter=0.25)
        d = sp.decode(cap)
        self.assertEqual(d.protocol, 'EV1527')
        self.assertEqual(d.key_hex, KEY)                  # 1:3 ratio survives +/-25%

    def test_partial_lead_and_clip(self):
        cap = sp.make_capture(KEY, frames=6, drop_lead=10, clip=260)
        d = sp.decode(cap)
        self.assertEqual(d.protocol, 'EV1527')
        self.assertEqual(d.key_hex, KEY)

    def test_spikes_in_gaps(self):
        cap = sp.make_capture(KEY, frames=5, spikes=4)
        d = sp.decode(cap)
        self.assertEqual(d.key_hex, KEY)

    def test_over_jitter_fails_safe(self):
        cap = sp.make_capture(KEY, frames=5, jitter=0.7)
        d = sp.decode(cap)                                 # must not raise...
        self.assertIsInstance(d, sp.ProtoResult)
        # ...and must not return a CONFIDENT wrong key
        if d.protocol == 'EV1527' and d.confidence >= 0.99:
            self.assertEqual(d.key_hex, KEY)


class TestDecodeFailSafe(unittest.TestCase):
    def test_too_short(self):
        self.assertEqual(sp.decode([350, 350, 350, 350]).protocol, 'UNKNOWN')

    def test_empty_and_none(self):
        self.assertEqual(sp.decode([]).protocol, 'UNKNOWN')
        self.assertEqual(sp.decode(None).protocol, 'UNKNOWN')

    def test_fsk_profile_gated(self):
        d = sp.decode(sp.encode(KEY), profile='FM_FSK')
        self.assertEqual(d.protocol, 'UNKNOWN')
        self.assertIn('FSK', d.note)

    def test_uniform_cells_not_decoded(self):
        uniform = [400, 400] * 40                          # 1:1 cells = Manchester/FSK
        d = sp.decode(uniform)
        self.assertEqual(d.protocol, 'UNKNOWN')

    def test_generic_pwm_fallback(self):
        d = sp.decode(sp.encode('1AB', nbits=12, repeats=5))   # 12-bit -> not named
        self.assertTrue(d.protocol.startswith('PWM'))
        self.assertEqual(d.nbits, 12)


class TestVerify(unittest.TestCase):
    def test_verify_pass(self):
        ok, detail = sp.verify(sp.make_capture(KEY, frames=5))
        self.assertTrue(ok)
        self.assertEqual(detail['key_hex'], KEY)

    def test_verify_non_encodable(self):
        ok, detail = sp.verify([400, 400] * 40)
        self.assertFalse(ok)
        self.assertIn('reason', detail)


if __name__ == '__main__':
    unittest.main()
