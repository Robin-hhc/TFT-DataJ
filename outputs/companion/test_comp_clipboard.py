"""Copy pinned codes through the real Qt clipboard, preserving user MIME data.

Only scheduling, HTTP and game-window discovery are isolated. Selection and
version callbacks run production code, including its stale-response guards.
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QClipboard
from app import QApplication, Companion
from dataj import DataJ


CATALOG = {'hex': [], 'equip': [], 'hero': [], 'trait': []}
MAIN_CODE = '【阵容码】黑暗仪式蜘蛛 II++ / Ω\n① <>& "\' 你好'


class CompClipboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stack = ExitStack()
        self.pending = []
        self.requests = []
        self.codes = {('18.2a', '112'): MAIN_CODE,
                      ('18.2a', '113'): '【阵容码】另一套阵容',
                      ('18.3', '113'): '【阵容码】新版另一套阵容'}
        self.fail_ids = set()
        for module in ('app', 'dataj', 'comp_browser'):
            self.stack.enter_context(patch(module + '.STATE_DIR', Path(self.tmp.name)))
        transport = httpx.MockTransport(self.response)
        db = Path(self.tmp.name) / 'cache.db'

        class Source(DataJ):
            def __init__(self, patch='18.2a'):
                super().__init__(patch=patch, db=db, transport=transport)

            def request(self, *args, **kwargs):
                self.next_request = 0
                return super().request(*args, **kwargs)

        self.stack.enter_context(patch('app.DataJ', Source))
        self.stack.enter_context(patch('app.Vision.prepare'))
        self.stack.enter_context(patch('app.win.enumerate_mumu', return_value=[]))
        self.stack.enter_context(patch.object(Companion, 'submit',
            lambda panel, pool, fn, done, failed=lambda _: None:
                self.pending.append((fn, done, failed))))
        self.p = Companion(offline=True, offline_catalog=CATALOG)
        self.p.timer.stop()
        self.flush()

    def tearDown(self):
        try:
            self.p.shutdown()
            self.p.deleteLater()
            self.qt.processEvents()
        finally:
            self.stack.close()
            self.tmp.cleanup()

    @contextmanager
    def preserved_clipboard(self):
        """Clone bytes, not a Qt-owned pointer invalidated by the next copy.

        Preserve every MIME format exposed by Qt, and any supported auxiliary
        clipboard modes. Never log or assert the original private contents.
        """
        clipboard = QApplication.clipboard()
        modes = [QClipboard.Mode.Clipboard]
        if clipboard.supportsSelection():
            modes.append(QClipboard.Mode.Selection)
        if clipboard.supportsFindBuffer():
            modes.append(QClipboard.Mode.FindBuffer)
        originals = {}
        for mode in modes:
            mime = clipboard.mimeData(mode)
            originals[mode] = None if mime is None else {
                fmt: bytes(mime.data(fmt)) for fmt in mime.formats()}
        try:
            yield clipboard
        finally:
            for mode, formats in originals.items():
                if formats is None:
                    clipboard.clear(mode)
                else:
                    restored = QMimeData()
                    for fmt, value in formats.items():
                        restored.setData(fmt, value)
                    clipboard.setMimeData(restored, mode)
            self.qt.processEvents()

    def response(self, request):
        self.requests.append(request)
        path = request.url.path.removeprefix('/api/web')
        if path.startswith('/comp/') and len(path.split('/')) == 3:
            comp = path.rsplit('/', 1)[-1]
            if comp in self.fail_ids:
                raise httpx.ConnectError('controlled details failure', request=request)
            version = request.url.params['gameVersion']
            data = {'compId': comp, 'name': '测试阵容' + comp, 'heroes': []}
            key = (version, comp)
            if key in self.codes:
                data['gameCode'] = deepcopy(self.codes[key])
        elif path == '/gamedata':
            data = deepcopy(CATALOG)
        else:
            data = []
        return httpx.Response(200, json={'code': 200, 'success': True, 'data': data})

    def prepare_completion(self):
        fn, done, failed = self.pending.pop(0)
        try:
            result = fn()
        except Exception as exc:
            return failed, str(exc)
        return done, result

    def complete(self):
        callback, result = self.prepare_completion()
        callback(result)

    def flush(self):
        for _ in range(20):
            if not self.pending:
                # Native clipboard and WebEngine notices still need the real
                # Qt event turn that an interactive button click normally has.
                self.qt.processEvents()
                if not self.pending:
                    return
            self.complete()
        self.fail('companion callbacks did not settle')

    def sentinel(self, clipboard):
        mime = QMimeData()
        mime.setText('clipboard regression sentinel')
        mime.setData('application/x-dataj-regression', b'\x00\xffkeep-all-mime')
        clipboard.setMimeData(mime)

    def assert_sentinel(self, clipboard):
        self.assertEqual(clipboard.text(), 'clipboard regression sentinel')
        self.assertEqual(bytes(clipboard.mimeData().data('application/x-dataj-regression')),
                         b'\x00\xffkeep-all-mime')

    def test_main_code_real_button_copies_chinese_symbols_and_newlines_exactly(self):
        with self.preserved_clipboard() as clipboard:
            self.p.select_comp('112')
            self.flush()
            self.assertTrue(self.p.copy_button.isEnabled())
            self.p.copy_button.click()
            self.qt.processEvents()
            self.assertEqual(clipboard.text(), MAIN_CODE)
            self.assertIn('主阵容码', self.p.status.text())
            details = [r for r in self.requests if r.url.path.endswith('/comp/112')]
            self.assertEqual(len(details), 1)
            self.assertEqual(details[0].url.params['gameVersion'], '18.2a')

    def test_no_pin_or_missing_invalid_code_never_overwrites_other_clipboard_formats(self):
        with self.preserved_clipboard() as clipboard:
            self.sentinel(clipboard)
            self.p.copy_code()
            self.assert_sentinel(clipboard)
            for comp, invalid in [('114', None), ('115', ''), ('116', '旧阵容码'),
                                  ('117', 112), ('118', {'gameCode': MAIN_CODE})]:
                with self.subTest(comp=comp):
                    if invalid is not None:
                        self.codes[('18.2a', comp)] = invalid
                    self.p.select_comp(comp)
                    self.flush()
                    self.assertFalse(self.p.copy_button.isEnabled())
                    self.p.copy_code()
                    self.assert_sentinel(clipboard)

    def test_switch_and_detail_failure_disable_copy_and_clear_previous_code(self):
        with self.preserved_clipboard() as clipboard:
            self.p.select_comp('112')
            self.flush()
            self.sentinel(clipboard)
            self.fail_ids.add('113')
            self.p.select_comp('113')
            self.assertIsNone(self.p.comp_detail)
            self.assertFalse(self.p.copy_button.isEnabled())
            self.p.copy_code()
            self.assert_sentinel(clipboard)
            self.flush()
            self.assertIsNone(self.p.comp_detail)
            self.assertFalse(self.p.copy_button.isEnabled())
            self.p.copy_code()
            self.assert_sentinel(clipboard)

    def test_late_previous_comp_completion_cannot_replace_new_code(self):
        with self.preserved_clipboard() as clipboard:
            self.p.select_comp('112')
            old_done, old_result = self.prepare_completion()
            self.p.select_comp('113')
            self.flush()
            old_done(old_result)
            self.assertEqual(self.p.session.target, '113')
            self.assertEqual(self.p.comp_detail['compId'], '113')
            self.p.copy_button.click()
            self.assertEqual(clipboard.text(), '【阵容码】另一套阵容')

    def test_unpin_retired_completion_cannot_reenable_or_copy_previous_code(self):
        with self.preserved_clipboard() as clipboard:
            self.p.select_comp('112')
            old_done, old_result = self.prepare_completion()
            self.p.unpin()
            self.sentinel(clipboard)
            old_done(old_result)
            self.assertIsNone(self.p.session.target)
            self.assertIsNone(self.p.comp_detail)
            self.assertFalse(self.p.copy_button.isEnabled())
            self.p.copy_code()
            self.assert_sentinel(clipboard)

    def test_version_change_rejects_old_detail_until_current_version_code_arrives(self):
        with self.preserved_clipboard() as clipboard:
            self.p.select_comp('112')
            self.flush()
            self.p.select_comp('113')
            old_done, old_result = self.prepare_completion()
            self.p.patch.addItem('18.3')
            self.p.patch.setCurrentText('18.3')
            self.p.patch.activated.emit(self.p.patch.currentIndex())
            self.sentinel(clipboard)
            old_done(old_result)
            self.assertEqual(self.p.session.target, '113')
            self.assertIsNone(self.p.comp_detail)
            self.assertFalse(self.p.copy_button.isEnabled())
            self.p.copy_code()
            self.assert_sentinel(clipboard)
            self.flush()
            self.assertTrue(self.p.copy_button.isEnabled())
            self.p.copy_button.click()
            self.assertEqual(clipboard.text(), '【阵容码】新版另一套阵容')
            self.assertEqual(self.p.adapter.patch, '18.3')


if __name__ == '__main__':
    unittest.main()
