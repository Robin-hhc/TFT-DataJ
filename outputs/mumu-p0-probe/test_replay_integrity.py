import hashlib
from pathlib import Path
import tempfile
import unittest
from ocr_baseline import ENGINE_PARAMS, verify_replay_inputs

class ReplayIntegrityTest(unittest.TestCase):
    def test_replaced_image_cannot_reuse_old_boxes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"image.bin"
            path.write_bytes(b"original")
            baseline = {"versions":{"ocr":"1"}, "models":[], "engine_params":ENGINE_PARAMS,
                        "images":[{"image":str(path),"image_sha256":hashlib.sha256(b"original").hexdigest()}]}
            verify_replay_inputs(baseline, {"ocr":"1"}, [])
            path.write_bytes(b"replacement")
            with self.assertRaisesRegex(ValueError, "Image changed"):
                verify_replay_inputs(baseline, {"ocr":"1"}, [])

    def test_upgraded_environment_cannot_reuse_baseline(self):
        baseline = {"versions":{"ocr":"1"}, "models":[], "engine_params":ENGINE_PARAMS, "images":[]}
        with self.assertRaisesRegex(ValueError, "environment/model/config changed"):
            verify_replay_inputs(baseline, {"ocr":"2"}, [])

if __name__ == "__main__":
    unittest.main()
