# Tests for the IR plugin's remote/button file-management logic - the Flipper-
# style hierarchy (one .ir file = a "remote" holding multiple named buttons).
# No hardware/ESP32 needed - pure file read/write against a temp directory.
# Run: cd apps && python -m unittest test_ir
import os
import tempfile
import shutil
import unittest
import ir


class TestSanitizeAndUniquePath(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_dir = ir.SAVE_DIR
        ir.SAVE_DIR = self._tmp

    def tearDown(self):
        ir.SAVE_DIR = self._orig_dir
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_rel_join_from_root(self):
        self.assertEqual(ir._rel_join('', 'TVs'), 'TVs')

    def test_rel_join_nested(self):
        self.assertEqual(ir._rel_join('TVs', 'Samsung'), 'TVs/Samsung')

    def test_rel_up_from_nested_goes_up_one_level(self):
        self.assertEqual(ir._rel_up('ACs/Split/Voltas'), 'ACs/Split')

    def test_rel_up_from_top_level_reaches_root(self):
        self.assertEqual(ir._rel_up('TVs'), '')

    def test_paged_clamps_to_last_valid_page(self):
        """Deleting entries (or a page tap racing a refresh) while parked on a
        later page must not leave an out-of-range page/start index."""
        page, total, start = ir._paged(97, 99, 6)   # 97 items, page 99 is way past the end
        self.assertLess(page, total)
        self.assertLessEqual(start, 97)

    def test_sanitize_strips_illegal_chars(self):
        self.assertEqual(ir._sanitize('Living Room TV!!'), 'LivingRoomTV')
        self.assertEqual(ir._sanitize('a/b\\c'), 'abc')

    def test_sanitize_truncates_to_16(self):
        self.assertEqual(len(ir._sanitize('x' * 40)), 16)

    def test_unique_path_avoids_collision(self):
        open(os.path.join(self._tmp, 'tv.ir'), 'w').close()
        p = ir._unique_path('tv')
        self.assertTrue(os.path.basename(p).startswith('tv_1'))


class TestRemoteFileManagement(unittest.TestCase):
    """The Flipper-style hierarchy this whole feature is about: a remote (one
    .ir file) holds multiple named buttons, not one signal per file."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_dir = ir.SAVE_DIR
        ir.SAVE_DIR = self._tmp
        ir._last = None
        ir._remote_path = None

    def tearDown(self):
        ir.SAVE_DIR = self._orig_dir
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _sig(self, name='x'):
        return {'name': name, 'type': 'parsed', 'protocol': 'NEC', 'address': 4, 'command': 8}

    def test_create_remote_with_pending_capture_becomes_first_button(self):
        ir._last = self._sig()
        ir._create_remote(None, 'LivingRoomTV')
        self.assertEqual(len(ir._remote_buttons), 1)
        self.assertEqual(ir._remote_buttons[0][1], 'LivingRoomTV')   # first button named like the remote

    def test_create_remote_without_capture_is_empty(self):
        ir._last = None
        ir._create_remote(None, 'AC')
        self.assertEqual(len(ir._remote_buttons), 0)
        # the root folder listing must still show this new (empty) remote
        ir._browse_rel = ''
        ir._refresh_browse()
        names = [name for (is_dir, _p, name, _n) in ir._browse_entries if not is_dir]
        self.assertIn('AC', names)

    def test_add_button_appends_not_overwrites(self):
        ir._last = self._sig()
        ir._create_remote(None, 'TV')
        path = ir._remote_path
        ir._last = self._sig()
        ir._add_button(None, path, 'VolUp')
        ir._last = self._sig()
        ir._add_button(None, path, 'VolDown')
        sigs = ir._load_sigs(path)
        self.assertEqual(len(sigs), 3)
        self.assertEqual([s['name'] for s in sigs], ['TV', 'VolUp', 'VolDown'])

    def test_remotes_list_shows_per_file_button_count_not_flattened(self):
        """The original bug: every signal across every file was flattened
        into ONE list. Each remote (file) must report its OWN button count."""
        ir._last = self._sig('Power')
        ir._create_remote(None, 'TV')
        tv_path = ir._remote_path
        ir._last = self._sig('VolUp')
        ir._add_button(None, tv_path, 'VolUp')

        ir._last = self._sig('On')
        ir._create_remote(None, 'AC')

        ir._browse_rel = ''
        ir._refresh_browse()
        counts = {name: n for (is_dir, _p, name, n) in ir._browse_entries if not is_dir}
        self.assertEqual(counts['TV'], 2)
        self.assertEqual(counts['AC'], 1)
        self.assertEqual(len(ir._browse_entries), 2)   # exactly 2 remotes, not 3 flattened signals

    def test_browse_root_shows_folders_not_flattened_nested_files(self):
        """The actual bug: Flipper exports its Infrared app as nested category
        folders (e.g. TVs/Samsung.ir), not a flat directory. The browser must
        show FOLDERS at the root - not eagerly flatten/walk the whole tree."""
        import ir_proto
        os.makedirs(os.path.join(self._tmp, 'TVs'))
        with open(os.path.join(self._tmp, 'TVs', 'Samsung.ir'), 'w') as f:
            f.write(ir_proto.dump_ir([self._sig('Power'), self._sig('VolUp')]))
        ir._browse_rel = ''
        ir._refresh_browse()
        self.assertEqual(len(ir._browse_entries), 1)
        is_dir, path, name, n = ir._browse_entries[0]
        self.assertTrue(is_dir)
        self.assertEqual(name, 'TVs')
        self.assertEqual(n, 1)   # 1 item inside (Samsung.ir)

    def test_browse_descends_into_folder_and_finds_the_file(self):
        import ir_proto
        os.makedirs(os.path.join(self._tmp, 'TVs'))
        with open(os.path.join(self._tmp, 'TVs', 'Samsung.ir'), 'w') as f:
            f.write(ir_proto.dump_ir([self._sig('Power'), self._sig('VolUp')]))
        ir._browse_rel = 'TVs'
        ir._refresh_browse()
        self.assertEqual(len(ir._browse_entries), 1)
        is_dir, path, name, n = ir._browse_entries[0]
        self.assertFalse(is_dir)
        self.assertEqual(name, 'Samsung')
        self.assertEqual(n, 2)   # 2 buttons: Power, VolUp

    def test_browse_handles_arbitrary_nesting_depth(self):
        import ir_proto
        deep = os.path.join(self._tmp, 'ACs', 'Split', 'Voltas')
        os.makedirs(deep)
        with open(os.path.join(deep, 'model.ir'), 'w') as f:
            f.write(ir_proto.dump_ir([self._sig('On')]))
        ir._browse_rel = 'ACs/Split/Voltas'
        ir._refresh_browse()
        self.assertEqual([(name, n) for (_d, _p, name, n) in ir._browse_entries], [('model', 1)])

    def test_delete_button_by_index_leaves_others_intact(self):
        ir._last = self._sig('A')
        ir._create_remote(None, 'R')
        path = ir._remote_path
        ir._last = self._sig('B')
        ir._add_button(None, path, 'B')
        ir._last = self._sig('C')
        ir._add_button(None, path, 'C')
        ir._delete_button(path, 1)   # remove 'B'
        names = [s['name'] for s in ir._load_sigs(path)]
        self.assertEqual(names, ['R', 'C'])

    def test_delete_remote_removes_file(self):
        ir._last = self._sig()
        ir._create_remote(None, 'Gone')
        path = ir._remote_path
        self.assertTrue(os.path.exists(path))
        ir._delete_remote(path)
        self.assertFalse(os.path.exists(path))

    def test_add_button_with_no_pending_capture_is_a_safe_noop(self):
        ir._last = self._sig()
        ir._create_remote(None, 'R')
        path = ir._remote_path
        ir._last = None   # nothing captured
        ir._add_button(None, path, 'ShouldNotAdd')
        sigs = ir._load_sigs(path)
        self.assertEqual(len(sigs), 1)   # unchanged - only the original first button


if __name__ == '__main__':
    unittest.main()
