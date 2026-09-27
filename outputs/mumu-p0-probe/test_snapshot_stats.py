import unittest
from snapshot_stats import stage_stat

class SnapshotStatsTest(unittest.TestCase):
    def setUp(self):
        self.rows = [{"hexId":1,"avgPlacement":3.81,"roundStats":[{"round":0,"roundLabel":"2-1","avgPlacement":3.65,"sampleCount":100}]}]

    def test_returns_stage_instead_of_overall(self):
        self.assertEqual(stage_stat(self.rows, "1", "2-1")["avg_placement"], 3.65)

    def test_missing_stage_never_falls_back(self):
        self.assertIsNone(stage_stat(self.rows, 1, "3-2")["avg_placement"])
        self.assertIsNone(stage_stat(self.rows, 1, "3-3")["avg_placement"])

    def test_label_index_conflict_is_rejected(self):
        self.rows[0]["roundStats"][0]["round"] = 1
        self.assertIsNone(stage_stat(self.rows, 1, "2-1")["avg_placement"])

if __name__ == "__main__":
    unittest.main()
