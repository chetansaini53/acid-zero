# Tests for acid_gps NMEA parsing - pure logic, NO hardware.
# Run: cd launcher && python -m unittest test_acid_gps
import unittest
from unittest.mock import patch
import acid_gps as gps


def _mk(body):
    """Build a valid NMEA sentence with a correctly computed checksum."""
    x = 0
    for c in body:
        x ^= ord(c)
    return '$%s*%02X' % (body, x)


class TestChecksum(unittest.TestCase):
    def test_valid_checksum_accepted(self):
        self.assertTrue(gps.nmea_checksum_ok(_mk('GPGGA,1,2,3')))

    def test_corrupted_checksum_rejected(self):
        line = _mk('GPGGA,1,2,3')
        bad = line[:-1] + ('0' if line[-1] != '0' else '1')
        self.assertFalse(gps.nmea_checksum_ok(bad))

    def test_missing_dollar_or_star_rejected(self):
        self.assertFalse(gps.nmea_checksum_ok('GPGGA,1,2,3*47'))
        self.assertFalse(gps.nmea_checksum_ok('$GPGGA,1,2,3'))

    def test_garbage_no_crash(self):
        self.assertFalse(gps.nmea_checksum_ok(''))
        self.assertFalse(gps.nmea_checksum_ok('not nmea at all'))


class TestCoordConversion(unittest.TestCase):
    def test_north_east_positive(self):
        # 4807.038 N -> 48 + 7.038/60 = 48.1173
        self.assertAlmostEqual(gps._nmea_to_deg('4807.038', 'N'), 48.1173, places=6)

    def test_south_negative(self):
        self.assertAlmostEqual(gps._nmea_to_deg('4807.038', 'S'), -48.1173, places=6)

    def test_east_positive(self):
        # 01131.000 E -> 11 + 31/60 = 11.51666...
        self.assertAlmostEqual(gps._nmea_to_deg('01131.000', 'E'), 11.0 + 31.0 / 60.0, places=6)

    def test_west_negative(self):
        self.assertAlmostEqual(gps._nmea_to_deg('01131.000', 'W'), -(11.0 + 31.0 / 60.0), places=6)

    def test_empty_returns_none(self):
        self.assertIsNone(gps._nmea_to_deg('', 'N'))
        self.assertIsNone(gps._nmea_to_deg('123.4', ''))

    def test_invalid_hemisphere_letter_rejected(self):
        self.assertIsNone(gps._nmea_to_deg('4807.038', 'X'))
        self.assertIsNone(gps._nmea_to_deg('4807.038', '1'))

    def test_minutes_60_or_more_rejected(self):
        # ddmm.mmmm where mm >= 60 is not a legal NMEA coordinate - must fail safe
        self.assertIsNone(gps._nmea_to_deg('4860.000', 'N'))
        self.assertIsNone(gps._nmea_to_deg('4899.999', 'N'))


class TestParseGGA(unittest.TestCase):
    def test_full_fix(self):
        # the well-known NMEA reference example: 48deg07.038'N 011deg31.000'E, fix=1, 8 sats
        line = _mk('GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,')
        r = gps.parse_gga(line)
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r['lat'], 48.1173, places=6)
        self.assertAlmostEqual(r['lon'], 11.0 + 31.0 / 60.0, places=6)
        self.assertEqual(r['fix_quality'], 1)
        self.assertEqual(r['sats'], 8)
        self.assertAlmostEqual(r['hdop'], 0.9, places=3)
        self.assertAlmostEqual(r['alt_m'], 545.4, places=3)
        self.assertEqual(r['time_utc'], '123519')

    def test_no_fix(self):
        line = _mk('GPGGA,123519,,,,,0,00,,,M,,M,,')
        r = gps.parse_gga(line)
        self.assertIsNotNone(r)
        self.assertEqual(r['fix_quality'], 0)
        self.assertIsNone(r['lat'])

    def test_gn_prefix_accepted(self):
        line = _mk('GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,')
        r = gps.parse_gga(line)
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r['lat'], 48.1173, places=6)

    def test_bad_checksum_rejected(self):
        line = _mk('GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,')
        corrupted = line[:-1] + '0'
        self.assertIsNone(gps.parse_gga(corrupted))

    def test_wrong_sentence_type_ignored(self):
        line = _mk('GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W')
        self.assertIsNone(gps.parse_gga(line))

    def test_short_line_no_crash(self):
        self.assertIsNone(gps.parse_gga(_mk('GPGGA,1,2')))
        self.assertIsNone(gps.parse_gga('not nmea'))


class TestParseRMC(unittest.TestCase):
    def test_valid_fix(self):
        line = _mk('GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W')
        r = gps.parse_rmc(line)
        self.assertIsNotNone(r)
        self.assertTrue(r['valid'])
        self.assertAlmostEqual(r['lat'], 48.1173, places=6)
        self.assertAlmostEqual(r['lon'], 11.0 + 31.0 / 60.0, places=6)
        self.assertAlmostEqual(r['speed_kn'], 22.4, places=3)
        self.assertAlmostEqual(r['course'], 84.4, places=3)
        self.assertEqual(r['date'], '230394')

    def test_invalid_status_flag(self):
        line = _mk('GPRMC,123519,V,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W')
        r = gps.parse_rmc(line)
        self.assertIsNotNone(r)
        self.assertFalse(r['valid'])

    def test_short_line_no_crash(self):
        self.assertIsNone(gps.parse_rmc(_mk('GPRMC,1,2')))


class TestGpsFixState(unittest.TestCase):
    def test_has_fix_false_before_any_data(self):
        g = gps.Gps.__new__(gps.Gps)   # bypass __init__'s pyserial requirement
        g._fix = {'lat': None, 'lon': None, 'fix_quality': 0, 'sats': 0,
                  'hdop': None, 'alt_m': None, 'time_utc': None, 'updated': 0.0}
        g._lock = __import__('threading').Lock()
        self.assertFalse(g.has_fix())

    def test_apply_gga_sets_fix(self):
        g = gps.Gps.__new__(gps.Gps)
        g._fix = {'lat': None, 'lon': None, 'fix_quality': 0, 'sats': 0,
                  'hdop': None, 'alt_m': None, 'time_utc': None, 'updated': 0.0}
        g._lock = __import__('threading').Lock()
        parsed = gps.parse_gga(_mk('GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,'))
        g._apply(parsed, 'gga')
        self.assertTrue(g.has_fix())
        self.assertAlmostEqual(g.fix()['lat'], 48.1173, places=6)

    def test_apply_gga_no_fix_does_not_set_has_fix(self):
        g = gps.Gps.__new__(gps.Gps)
        g._fix = {'lat': None, 'lon': None, 'fix_quality': 0, 'sats': 0,
                  'hdop': None, 'alt_m': None, 'time_utc': None, 'updated': 0.0}
        g._lock = __import__('threading').Lock()
        parsed = gps.parse_gga(_mk('GPGGA,123519,,,,,0,00,,,M,,M,,'))
        g._apply(parsed, 'gga')
        self.assertFalse(g.has_fix())

    def test_apply_rmc_invalid_ignored(self):
        g = gps.Gps.__new__(gps.Gps)
        g._fix = {'lat': None, 'lon': None, 'fix_quality': 0, 'sats': 0,
                  'hdop': None, 'alt_m': None, 'time_utc': None, 'updated': 0.0}
        g._lock = __import__('threading').Lock()
        parsed = gps.parse_rmc(_mk('GPRMC,123519,V,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W'))
        g._apply(parsed, 'rmc')
        self.assertIsNone(g.fix()['lat'])


class TestCandidatePorts(unittest.TestCase):
    """candidate_ports() must find BOTH a bare TTL module on the Pi's own GPIO
    UART (NEO-6M/7M via /dev/serial0) AND a USB dongle (VK-162 class), whichever
    is actually plugged in - the user's ask this session was 'auto-detect
    whatever's there', covering both hardware paths."""

    @patch('acid_gps.glob.glob')
    @patch('acid_gps.os.path.realpath')
    @patch('acid_gps.os.path.exists')
    def test_onboard_uart_found_and_preferred_first(self, mock_exists, mock_realpath, mock_glob):
        mock_exists.side_effect = lambda p: p == '/dev/serial0'
        mock_realpath.side_effect = lambda p: p
        mock_glob.side_effect = lambda pat: ['/dev/ttyUSB0'] if 'ttyUSB' in pat else []
        ports = gps.Gps.candidate_ports()
        self.assertEqual(ports[0], '/dev/serial0')
        self.assertIn('/dev/ttyUSB0', ports)

    @patch('acid_gps.glob.glob')
    @patch('acid_gps.os.path.realpath')
    @patch('acid_gps.os.path.exists')
    def test_serial0_symlink_to_ttyS0_not_double_counted(self, mock_exists, mock_realpath, mock_glob):
        mock_exists.side_effect = lambda p: p in ('/dev/serial0', '/dev/ttyS0')
        mock_realpath.side_effect = lambda p: '/dev/ttyS0'   # serial0 resolves to the same device
        mock_glob.return_value = []
        ports = gps.Gps.candidate_ports()
        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0], '/dev/serial0')

    @patch('acid_gps.glob.glob')
    @patch('acid_gps.os.path.realpath')
    @patch('acid_gps.os.path.exists')
    def test_no_onboard_uart_falls_back_to_usb_only(self, mock_exists, mock_realpath, mock_glob):
        mock_exists.return_value = False
        mock_realpath.side_effect = lambda p: p
        mock_glob.side_effect = lambda pat: ['/dev/ttyUSB0'] if 'ttyUSB' in pat else []
        ports = gps.Gps.candidate_ports()
        self.assertEqual(ports, ['/dev/ttyUSB0'])

    @patch('acid_gps.glob.glob')
    @patch('acid_gps.os.path.exists')
    def test_nothing_present_returns_empty(self, mock_exists, mock_glob):
        mock_exists.return_value = False
        mock_glob.return_value = []
        self.assertEqual(gps.Gps.candidate_ports(), [])


if __name__ == '__main__':
    unittest.main()
