"""Launch contract: an existing Windows instance blocks all Qt startup work."""
import ctypes
from ctypes import wintypes
from contextlib import ExitStack
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import Mock, patch

import app
from single_instance import SingleInstance


def unique_name():
    return r'Local\TFT-DataJ.Tests.' + uuid.uuid4().hex


class AppSingleInstanceTests(unittest.TestCase):
    def test_existing_windows_instance_returns_before_creating_qt(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.restype = wintypes.BOOL
        # This literal is the external launch contract, independent of the implementation.
        handle = kernel.CreateMutexW(None, False, r'Local\TFT-DataJ.Companion.v1')
        self.assertTrue(handle)
        try:
            with patch.object(sys, 'argv', ['app.py']), \
                    patch('app.win.enable_dpi'), \
                    patch('app.QApplication', side_effect=RuntimeError('duplicate created QApplication')) as qt, \
                    patch('app.Companion') as panel, patch('app.MouseShortcut') as mouse:
                self.assertEqual(app.main(), 0)
                qt.assert_not_called()
                panel.assert_not_called()
                mouse.assert_not_called()
        finally:
            kernel.CloseHandle(handle)

    def test_self_test_bypasses_ordinary_instance_lock(self):
        with SingleInstance():
            # A live companion may already own the production mutex during this test.
            with patch.object(sys, 'argv', ['app.py', '--self-test']), \
                    patch('app.win.enable_dpi'), \
                    patch('app.QApplication', side_effect=RuntimeError('diagnostic reached Qt')):
                with self.assertRaisesRegex(RuntimeError, 'diagnostic reached Qt'):
                    app.main()

    def test_start_collapsed_shows_only_mark(self):
        guard = SingleInstance(unique_name())
        qt = Mock()
        qt.exec.return_value = 0
        panel = Mock()
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, 'argv', ['app.py', '--start-collapsed']))
            stack.enter_context(patch('single_instance.SingleInstance', return_value=guard))
            stack.enter_context(patch('app.win.enable_dpi'))
            stack.enter_context(patch('app.win.user.RegisterHotKey', return_value=True))
            stack.enter_context(patch('app.QApplication', return_value=qt))
            stack.enter_context(patch('app.Companion', return_value=panel))
            stack.enter_context(patch('app.MouseShortcut'))
            stack.enter_context(patch('app.QAbstractNativeEventFilter', object))
            self.assertEqual(app.main(), 0)
        panel.mark.show.assert_called_once_with()
        panel.show.assert_not_called()
        panel.activateWindow.assert_not_called()

    def test_startup_exception_releases_native_guard(self):
        guard = SingleInstance(unique_name())
        with patch.object(sys, 'argv', ['app.py']), \
                patch('single_instance.SingleInstance', return_value=guard), \
                patch('app.win.enable_dpi'), \
                patch('app.QApplication', side_effect=RuntimeError('startup failed')):
            with self.assertRaisesRegex(RuntimeError, 'startup failed'):
                app.main()
        with SingleInstance(guard.name) as acquired:
            self.assertTrue(acquired)

    def test_mutex_failure_cannot_start_second_application(self):
        guard = SingleInstance(r'Local\TFT-DataJ\invalid-mutex-name')
        with patch.object(sys, 'argv', ['app.py']), \
                patch('single_instance.SingleInstance', return_value=guard), \
                patch('app.QApplication') as qt:
            with self.assertRaises(OSError):
                app.main()
            qt.assert_not_called()

    def test_guard_covers_event_loop_and_releases_on_normal_exit(self):
        guard = SingleInstance(unique_name())
        qt = Mock()
        panel = Mock()
        mouse = Mock()

        def event_loop():
            with SingleInstance(guard.name) as acquired:
                self.assertFalse(acquired, 'mutex must remain held during the Qt event loop')
            return 7

        qt.exec.side_effect = event_loop
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, 'argv', ['app.py']))
            stack.enter_context(patch('single_instance.SingleInstance', return_value=guard))
            stack.enter_context(patch('app.win.enable_dpi'))
            stack.enter_context(patch('app.win.user.RegisterHotKey', return_value=True))
            stack.enter_context(patch('app.QApplication', return_value=qt))
            stack.enter_context(patch('app.Companion', return_value=panel))
            stack.enter_context(patch('app.MouseShortcut', return_value=mouse))
            stack.enter_context(patch('app.QAbstractNativeEventFilter', object))
            self.assertEqual(app.main(), 7)
        mouse.start.assert_called_once_with()
        qt.exec.assert_called_once_with()
        with SingleInstance(guard.name) as acquired:
            self.assertTrue(acquired)

    def test_launcher_diagnose_does_not_enter_application_main(self):
        import launch
        run = Mock(return_value=23)
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            stack.enter_context(patch.object(sys, 'argv', ['launch.py', '--diagnose']))
            stack.enter_context(patch.object(sys, 'stdout', sys.stdout))
            stack.enter_context(patch.object(sys, 'stderr', sys.stderr))
            stack.enter_context(patch('bootstrap.STATE_DIR', Path(directory)))
            stack.enter_context(patch('launch.faulthandler.enable'))
            stack.enter_context(patch('launch.faulthandler.disable'))
            stack.enter_context(patch.dict(sys.modules, {'portable_check': SimpleNamespace(main=run)}))
            main = stack.enter_context(patch('app.main'))
            result = launch.main()
            # The actual launcher leaves its diagnostics stream open for process lifetime.
            log = sys.stdout
            try:
                self.assertEqual(result, 23)
                run.assert_called_once_with()
                main.assert_not_called()
            finally:
                log.close()


class NativeSingleInstanceTests(unittest.TestCase):
    def test_rejected_contender_does_not_extend_original_lock_lifetime(self):
        name = unique_name()
        primary = SingleInstance(name)
        rejected = SingleInstance(name)
        try:
            self.assertTrue(primary.acquire())
            self.assertFalse(rejected.acquire())
            primary.close()
            with SingleInstance(name) as acquired:
                self.assertTrue(acquired)
        finally:
            primary.close()
            rejected.close()

    def test_second_process_is_blocked_and_can_launch_after_first_exit(self):
        name = unique_name()
        code = ('from single_instance import SingleInstance; import sys; '
                'guard=SingleInstance(sys.argv[1]); acquired=guard.acquire(); '
                'guard.close(); print(int(acquired))')
        def attempt():
            result = subprocess.run([sys.executable, '-X', 'utf8', '-c', code, name],
                cwd=Path(__file__).parent, capture_output=True, text=True, timeout=5, check=True)
            return result.stdout.strip()
        with SingleInstance(name) as acquired:
            self.assertTrue(acquired)
            self.assertEqual(attempt(), '0')
        self.assertEqual(attempt(), '1')

    def test_close_is_idempotent_and_same_guard_can_acquire_after_close(self):
        guard = SingleInstance(unique_name())
        try:
            self.assertTrue(guard.acquire())
            self.assertTrue(guard.acquire())
            guard.close()
            guard.close()
            self.assertTrue(guard.acquire())
        finally:
            guard.close()


if __name__ == '__main__':
    unittest.main()
