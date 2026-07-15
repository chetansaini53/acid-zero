# Tests for ir_proto - pure logic, NO radio. Run: cd apps && python -m unittest test_ir_proto
import unittest
import ir_proto as ir

# a real-shaped Flipper .ir file (parsed + raw signals)
FLIPPER_SAMPLE = """Filetype: IR signals file
Version: 1
#
name: Power
type: parsed
protocol: NEC
address: 04 00 00 00
command: 08 00 00 00
#
name: Vol_up
type: raw
frequency: 38000
duty_cycle: 0.330000
data: 9000 4500 560 560 560 1690 560 560
"""


class TestHexBytes(unittest.TestCase):
    def test_le_parse(self):
        self.assertEqual(ir.hexbytes_to_int('04 00 00 00'), 0x04)
        self.assertEqual(ir.hexbytes_to_int('E0 E0 00 00'), 0xE0E0)

    def test_roundtrip(self):
        for v in (0x04, 0xE0E0, 0xABCD):
            self.assertEqual(ir.hexbytes_to_int(ir.int_to_hexbytes(v)), v)


class TestFlipperIO(unittest.TestCase):
    def test_parse_flipper(self):
        sigs = ir.parse_ir(FLIPPER_SAMPLE)
        self.assertEqual(len(sigs), 2)
        self.assertEqual(sigs[0]['name'], 'Power')
        self.assertEqual(sigs[0]['type'], 'parsed')
        self.assertEqual(sigs[0]['protocol'], 'NEC')
        self.assertEqual(sigs[0]['address'], 0x04)
        self.assertEqual(sigs[0]['command'], 0x08)
        self.assertEqual(sigs[1]['type'], 'raw')
        self.assertEqual(sigs[1]['frequency'], 38000)
        self.assertEqual(sigs[1]['data'][:2], [9000, 4500])

    def test_dump_roundtrip(self):
        sigs = ir.parse_ir(FLIPPER_SAMPLE)
        text = ir.dump_ir(sigs)
        sigs2 = ir.parse_ir(text)
        self.assertEqual(len(sigs), len(sigs2))
        self.assertEqual(sigs2[0]['address'], 0x04)
        self.assertEqual(sigs2[0]['command'], 0x08)
        self.assertEqual(sigs2[1]['data'], sigs[1]['data'])

    def test_flipper_written_is_readable(self):
        # a captured raw signal written our way must parse back identically
        cap = {'name': 'MyRemote', 'type': 'raw', 'frequency': 38000,
               'data': [9000, 4500, 560, 1690, 560, 560]}
        back = ir.parse_ir(ir.dump_ir([cap]))[0]
        self.assertEqual(back['data'], cap['data'])
        self.assertEqual(back['frequency'], 38000)


class TestEncode(unittest.TestCase):
    def test_nec_shape(self):
        raw = ir.nec_encode(0x04, 0x08)
        self.assertEqual(raw[0:2], [ir.NEC_HDR_MARK, ir.NEC_HDR_SPACE])   # leader
        # 32 data bits => 64 elems + 2 leader + 1 stop mark = 67
        self.assertEqual(len(raw), 2 + 64 + 1)
        self.assertEqual(len(raw) % 2, 1)   # ends on a mark
        self.assertEqual(raw[-1], ir.NEC_BIT_MARK)

    def test_nec_bit_values(self):
        # command 0x08 = 00001000b, LSB-first bit3 set -> one '1' space in cmd byte
        raw = ir.nec_encode(0x04, 0x08)
        spaces = raw[3:len(raw)-1:2]     # the space of each bit
        ones = sum(1 for s in spaces if s == ir.NEC_ONE_SPACE)
        # addr 0x04 -> 1 one, ~addr -> 7 ones, cmd 0x08 -> 1 one, ~cmd -> 7 ones = 16
        self.assertEqual(ones, 16)

    def test_signal_to_raw_parsed(self):
        f, raw = ir.signal_to_raw({'type': 'parsed', 'protocol': 'NEC', 'address': 4, 'command': 8})
        self.assertEqual(f, 38000)
        self.assertEqual(raw, ir.nec_encode(4, 8))

    def test_signal_to_raw_raw(self):
        f, raw = ir.signal_to_raw({'type': 'raw', 'frequency': 40000, 'data': [100, 200]})
        self.assertEqual((f, raw), (40000, [100, 200]))

    def test_samsung_shape(self):
        raw = ir.samsung_encode(0x07, 0x02)
        self.assertEqual(raw[0:2], [ir.SAM_HDR_MARK, ir.SAM_HDR_SPACE])


class TestPresets(unittest.TestCase):
    def test_presets_all_encodable(self):
        self.assertTrue(len(ir.PRESETS) >= 4)
        for p in ir.PRESETS:
            res = ir.signal_to_raw(p)
            self.assertIsNotNone(res, 'preset not encodable: %s' % p['name'])
            f, raw = res
            self.assertGreater(len(raw), 10)


if __name__ == '__main__':
    unittest.main()
