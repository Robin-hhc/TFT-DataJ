"""The GUI uses structured statistics, not previously formatted display text."""
import unittest
import app
from types import SimpleNamespace
from unittest.mock import patch

import test_hex_comp_supplement_ui as fixture


class HexResultPublicationTests(unittest.TestCase):
    IDS = fixture.HexCompSupplementUI.IDS
    NAMES = fixture.HexCompSupplementUI.NAMES
    EXPECTED = fixture.HexCompSupplementUI.EXPECTED
    setUpClass = classmethod(fixture.HexCompSupplementUI.setUpClass.__func__)
    setUp = fixture.HexCompSupplementUI.setUp
    tearDown = fixture.HexCompSupplementUI.tearDown
    response = fixture.HexCompSupplementUI.response
    query = fixture.HexCompSupplementUI.query
    complete = fixture.HexCompSupplementUI.complete

    def test_display_projection_cannot_change_refresh_retention_or_overlay_value(self):
        self.query()
        self.complete()
        self.complete()
        result = self.p.stats_payload['result']
        self.assertEqual(result.choices[0].comp_stat.average, 4.23)
        self.p.stats_payload['rows'][0][2] = '文案变化不应改动已确认统计'
        # Source callbacks may take longer than the production capture TTL.
        # This assertion exercises projection from a fresh unchanged frame;
        # the stopped fixture timer does not provide the live capture refresh.
        self.p.last_capture = app.time.monotonic()
        self.p.display_overlays()
        self.assertIn('4.23 · 13局 · 少', self.p.overlays[0].text())
        self.assertNotIn('文案变化', self.p.overlays[0].text())
        self.query(refresh=True)
        self.complete()
        self.assertEqual(self.p.stats_payload['rows'][0][2], '4.23 · 13局 · 少')
        self.assertEqual(self.p.stats_payload['result'].choices[0].comp_stat.samples, 13)
        self.complete()

    def test_stale_capture_defers_structured_publication_until_fresh_frame(self):
        self.query()
        self.complete()
        self.complete()
        self.assertEqual(self.p.stats_payload['result'].choices[0].comp_stat.average, 4.23)
        self.p.stats_payload['rows'][0][2] = '文案变化不应改动已确认统计'
        self.p.overlays[0].setText('等待新鲜画面')
        with patch('app.time', SimpleNamespace(monotonic=lambda: 10.0)):
            self.p.last_capture = 8.0
            self.p.display_overlays()
            self.assertEqual(self.p.overlays[0].text(), '等待新鲜画面')
            self.p.last_capture = 10.0
            self.p.display_overlays()
        self.assertIn('4.23 · 13局 · 少', self.p.overlays[0].text())
        self.assertNotIn('文案变化', self.p.overlays[0].text())


if __name__ == '__main__':
    unittest.main()
