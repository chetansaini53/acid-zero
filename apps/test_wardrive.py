# Tests for the Wardrive plugin's pure helpers - no bettercap/GPS hardware needed.
# Run: cd apps && python -m unittest test_wardrive
import os
import tempfile
import shutil
import time
import unittest
import wardrive


class TestChanToFreq(unittest.TestCase):
    def test_24ghz(self):
        self.assertEqual(wardrive._chan_to_freq(1), 2412)
        self.assertEqual(wardrive._chan_to_freq(6), 2437)
        self.assertEqual(wardrive._chan_to_freq(11), 2462)

    def test_14_special_case(self):
        self.assertEqual(wardrive._chan_to_freq(14), 2484)

    def test_5ghz(self):
        self.assertEqual(wardrive._chan_to_freq(36), 5180)
        self.assertEqual(wardrive._chan_to_freq(149), 5745)
        self.assertEqual(wardrive._chan_to_freq(165), 5825)

    def test_unknown_channel_blank(self):
        self.assertEqual(wardrive._chan_to_freq(0), '')
        self.assertEqual(wardrive._chan_to_freq(200), '')


class TestWigleRow(unittest.TestCase):
    def _ap(self, ssid, mac='aa:bb:cc:dd:ee:ff', enc='OPEN', channel=6, rssi=-50):
        return {'mac': mac, 'ssid': ssid, 'enc': enc, 'channel': channel, 'rssi': rssi}

    def _fix(self, lat=48.1173, lon=11.5166, alt=100.0):
        return {'lat': lat, 'lon': lon, 'alt_m': alt}

    def test_comma_in_ssid_is_escaped_not_corrupting_columns(self):
        row = wardrive._wigle_row(self._ap('Bob, Free WiFi'), self._fix(), '2026-01-01 00:00:00')
        parsed = next(wardrive.csv.reader([row]))
        self.assertEqual(parsed[1], 'Bob, Free WiFi')   # SSID stayed ONE field, not split
        self.assertEqual(len(parsed), 14)                # full WigleWifi-1.6 column count

    def test_quote_in_ssid_is_escaped(self):
        row = wardrive._wigle_row(self._ap('Joe"s Router'), self._fix(), '2026-01-01 00:00:00')
        parsed = next(wardrive.csv.reader([row]))
        self.assertEqual(parsed[1], 'Joe"s Router')

    def test_column_order_and_count(self):
        row = wardrive._wigle_row(self._ap('Home'), self._fix(), '2026-01-01 00:00:00')
        f = next(wardrive.csv.reader([row]))
        self.assertEqual(f[0], 'aa:bb:cc:dd:ee:ff')   # MAC
        self.assertEqual(f[1], 'Home')                 # SSID
        self.assertEqual(f[2], 'OPEN')                 # AuthMode
        self.assertEqual(f[4], '6')                    # Channel
        self.assertEqual(f[5], '2437')                  # Frequency
        self.assertEqual(f[6], '-50')                   # RSSI
        self.assertEqual(f[13], 'WIFI')                 # Type (last column)

    def test_header_matches_column_count(self):
        hdr = next(wardrive.csv.reader([wardrive._csv_line(wardrive.WIGLE_HDR2)]))
        row = next(wardrive.csv.reader([wardrive._wigle_row(self._ap('x'), self._fix(), 'now')]))
        self.assertEqual(len(hdr), len(row))


class TestGpsOptionalScanning(unittest.TestCase):
    """The user's explicit ask: scanning must work whether GPS is connected or
    not, so the WiFi/bettercap side is testable before GPS hardware is wired."""

    def test_ensure_gps_returns_false_when_module_missing(self):
        orig = wardrive.Gps
        try:
            wardrive.Gps = None
            self.assertFalse(wardrive._ensure_gps())
        finally:
            wardrive.Gps = orig

    def test_bc_scan_returns_empty_not_exception_when_unreachable(self):
        orig = wardrive.BC_URL
        try:
            wardrive.BC_URL = 'http://127.0.0.1:1/unreachable'   # nothing listens here
            iface, aps = wardrive._bc_scan()
            self.assertEqual(iface, '')
            self.assertEqual(aps, [])
        finally:
            wardrive.BC_URL = orig


class TestConsoleLog(unittest.TestCase):
    """The console feed the user asked for: SSID/MAC/channel/RSSI/enc per line,
    tagged LOG (saved to CSV) vs SCAN (GPS-less, display only)."""

    def setUp(self):
        wardrive._log_lines.clear()

    def _ap(self, mac='aa:bb:cc:dd:ee:ff', ssid='HomeNet', enc='WPA2', channel=6, rssi=-50):
        return {'mac': mac, 'ssid': ssid, 'enc': enc, 'channel': channel, 'rssi': rssi}

    def test_push_log_line_contains_key_fields(self):
        wardrive._push_log(self._ap(), 'SCAN')
        self.assertEqual(len(wardrive._log_lines), 1)
        line = wardrive._log_lines[0]
        self.assertIn('aa:bb:cc:dd:ee:ff', line)
        self.assertIn('HomeNet', line)
        self.assertIn('ch6', line)
        self.assertIn('-50dBm', line)
        self.assertIn('WPA2', line)
        self.assertIn('[SCAN]', line)

    def test_push_log_tags_logged_vs_scan(self):
        wardrive._push_log(self._ap(mac='11:11:11:11:11:11'), 'LOG')
        self.assertIn('[LOG]', wardrive._log_lines[-1])

    def test_hidden_ssid_shown_as_placeholder(self):
        wardrive._push_log(self._ap(ssid=''), 'SCAN')
        self.assertIn('<hidden>', wardrive._log_lines[-1])

    def test_log_buffer_trimmed_to_max_lines(self):
        for i in range(wardrive.MAX_LOG_LINES + 50):
            wardrive._push_log(self._ap(mac='%02x:00:00:00:00:00' % (i % 256)), 'SCAN')
        self.assertEqual(len(wardrive._log_lines), wardrive.MAX_LOG_LINES)


class TestSavedLogsBrowser(unittest.TestCase):
    """The 'View Saved' list: auto-saved, timestamped wardrive_*.csv files,
    newest first, with a row count and a working delete."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_dir = wardrive.LOG_DIR
        wardrive.LOG_DIR = self._tmp

    def tearDown(self):
        wardrive.LOG_DIR = self._orig_dir
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_log(self, ts, n_rows):
        path = os.path.join(self._tmp, 'wardrive_%s.csv' % ts)
        with open(path, 'w') as f:
            f.write(wardrive.WIGLE_HDR1 + '\n')
            f.write(wardrive._csv_line(wardrive.WIGLE_HDR2))
            for i in range(n_rows):
                f.write(wardrive._wigle_row(
                    {'mac': '00:00:00:00:00:%02x' % i, 'ssid': 'x', 'enc': 'OPEN', 'channel': 1, 'rssi': -50},
                    {'lat': 1.0, 'lon': 2.0, 'alt_m': None}, 'now'))
        return path

    def test_refresh_lists_newest_first_with_row_counts(self):
        self._write_log('20260101_100000', 3)
        self._write_log('20260102_100000', 5)
        wardrive._refresh_saved()
        self.assertEqual(len(wardrive._saved), 2)
        self.assertIn('2026-01-02', wardrive._saved[0][1])   # newest first
        self.assertEqual(wardrive._saved[0][2], 5)
        self.assertEqual(wardrive._saved[1][2], 3)

    def test_delete_removes_file_and_refreshes(self):
        p = self._write_log('20260101_120000', 1)
        wardrive._refresh_saved()
        self.assertEqual(len(wardrive._saved), 1)
        wardrive._delete_saved(p)
        self.assertEqual(len(wardrive._saved), 0)
        self.assertFalse(os.path.exists(p))

    def test_empty_dir_gives_empty_list(self):
        wardrive._refresh_saved()
        self.assertEqual(wardrive._saved, [])

    def test_malformed_timestamp_falls_back_to_raw_name(self):
        path = os.path.join(self._tmp, 'wardrive_notatimestamp.csv')
        with open(path, 'w') as f:
            f.write(wardrive.WIGLE_HDR1 + '\n' + wardrive._csv_line(wardrive.WIGLE_HDR2))
        wardrive._refresh_saved()   # must not raise
        self.assertEqual(len(wardrive._saved), 1)
        self.assertEqual(wardrive._saved[0][1], 'notatimestamp')


if __name__ == '__main__':
    unittest.main()
