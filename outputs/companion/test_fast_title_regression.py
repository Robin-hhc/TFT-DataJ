"""Real title pixels must survive the live selection reader's crop geometry."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image

from vision import Vision
from choice_reader import normalize_name


FIXTURE = Path(__file__).parent / 'fixtures/hex-title-20261007'


class FastTitleRegressionTests(unittest.TestCase):
    def test_real_celestial_blessing_quality_is_read_from_complete_title(self):
        evidence = json.loads(FIXTURE.with_suffix('.json').read_text(encoding='utf-8'))
        png = FIXTURE.with_suffix('.png')
        self.assertEqual(hashlib.sha256(png.read_bytes()).hexdigest(), evidence['derived_png_sha256'])
        frame = Image.new('RGB', tuple(evidence['source_canvas']), 'black')
        with Image.open(png) as title:
            frame.paste(title.convert('RGB'), tuple(evidence['derived_title_crop_box'][:2]))
        vision = Vision()
        # Isolate title geometry; original full-frame reviewed replay separately
        # checks the actual scene and round with no mocked recognition.
        with patch('vision.may_be_choice', return_value=True), \
                patch.object(vision, 'read_round_crop', return_value='3-2'):
            observation = vision.analyze_fast(frame, evidence['catalog'])
        self.assertEqual(observation['scene'], 'choice_candidates')
        resolution = observation['cards'][evidence['expected_slot']]['resolution']
        self.assertEqual(resolution['status'], 'resolved')
        self.assertEqual(resolution['id'], evidence['expected_id'])
        self.assertEqual(resolution['name'], '星界赐福 III')
        self.assertGreaterEqual(sum(normalize_name(value) == normalize_name(resolution['name'])
                                    for value in resolution['readings']), 2)


if __name__ == '__main__':
    unittest.main()
