"""Validate experiment command ordering using mocks, never send Android input."""
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from PIL import Image
from bootstrap import ROOT


spec = importlib.util.spec_from_file_location('capture_android_hold_tool', ROOT/'tools/capture_android_hold.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class NativeHoldToolTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.adb = self.root/'adb.exe'; self.adb.write_bytes(b'unit-test placeholder')
        self.output = self.root/'detail.png'
        buffer = BytesIO(); Image.new('RGB', (32, 18)).save(buffer, format='PNG')
        self.png = buffer.getvalue()
        self.argv = ['capture_android_hold.py', '--adb', str(self.adb), '--serial', 'test-device',
                     '--x', '12', '--y', '34', '--output', str(self.output)]

    def invoke(self, response=None, error=None):
        events = []
        child = Mock(returncode=0)
        child.communicate.side_effect = lambda **_: (events.append('wait') or b'', b'')
        def spawn(command, **_):
            events.append(('input', command))
            return child
        def capture(command, **_):
            events.append(('capture', command))
            if error:
                raise error
            return response or SimpleNamespace(returncode=0, stdout=self.png, stderr=b'')
        with patch.object(sys, 'argv', self.argv), \
                patch.object(tool.subprocess, 'Popen', side_effect=spawn), \
                patch.object(tool.subprocess, 'run', side_effect=capture), \
                patch.object(tool.time, 'sleep', side_effect=lambda seconds: events.append(('delay', seconds))), \
                patch('builtins.print'):
            result = tool.main()
        return result, events, child

    def test_capture_is_requested_during_hold_and_real_png_metadata_is_saved(self):
        result, events, child = self.invoke()
        self.assertEqual(result, 0)
        self.assertEqual([event[0] if isinstance(event, tuple) else event for event in events],
                         ['input', 'delay', 'capture', 'wait'])
        self.assertEqual(events[0][1][-7:], ['input', 'swipe', '12', '34', '12', '34', '2000'])
        self.assertEqual(events[1], ('delay', .2))
        self.assertEqual(self.output.read_bytes(), self.png)
        metadata = json.loads(self.output.with_suffix('.json').read_text(encoding='utf-8'))
        self.assertTrue(metadata['valid_png'])
        self.assertEqual(metadata['size'], [32, 18])
        self.assertEqual(metadata['point'], [12, 34])
        child.communicate.assert_called_once()

    def test_corrupt_png_is_not_written_or_marked_as_screenshot_success(self):
        response = SimpleNamespace(returncode=0, stdout=b'\x89PNG\r\n\x1a\ncorrupt', stderr=b'')
        result, _, _ = self.invoke(response=response)
        self.assertEqual(result, 1)
        self.assertFalse(self.output.exists())
        metadata = json.loads(self.output.with_suffix('.json').read_text(encoding='utf-8'))
        self.assertFalse(metadata['valid_png'])
        self.assertIsNone(metadata['path'])

    def test_capture_timeout_still_waits_for_the_input_process(self):
        result, events, child = self.invoke(error=subprocess.TimeoutExpired('fake capture', 20))
        self.assertEqual(result, 1)
        self.assertEqual(events[-1], 'wait')
        child.communicate.assert_called_once()
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
