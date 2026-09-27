import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from diagnostics import FrameRecorder


class RecorderTest(unittest.TestCase):
    def test_rate_limit_and_bounded_frame_ring(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);recorder=FrameRecorder(root);im=Image.new('RGB',(20,10))
            with patch('diagnostics.time.monotonic',return_value=0):
                self.assertEqual(recorder.save(im,{'scene':'unknown'}),'frame-0')
                self.assertIsNone(recorder.save(im,{'scene':'unknown'}))
            for i in range(1,10):
                with patch('diagnostics.time.monotonic',return_value=i*16):
                    recorder.save(im,{'scene':'unknown'})
            self.assertEqual(len(list(root.glob('*.png'))),6)
            self.assertEqual(len(list(root.glob('*.json'))),6)


if __name__=='__main__':unittest.main()
