import unittest

from research.dev31.audit_engine import Score, audit_prediction, win5_class, verify_pregame_source, approve_scoring_promotion


class TestDev31Audit(unittest.TestCase):
    def test_score_diagnostics(self):
        x=audit_prediction(Score(112,115),Score(133,110),20)
        self.assertFalse(x["winner_hit"])
        self.assertIn("BLOWOUT_TAIL_UNDERWEIGHT",x["tags"])

    def test_low_total_shock(self):
        x=audit_prediction(Score(70,66),Score(51,54))
        self.assertIn("TOTAL_SHOCK_30",x["tags"])

    def test_win5_not_score_winner(self):
        self.assertEqual(win5_class(3),"5")
        self.assertEqual(win5_class(23),"승")
        self.assertEqual(win5_class(-6),"패")

    def test_asof_missing_and_late(self):
        self.assertFalse(verify_pregame_source(None,None,"2026-11-11T00:00:00Z",True,True))
        self.assertFalse(verify_pregame_source("2026-11-11T01:00:00Z","2026-11-11T01:00:00Z","2026-11-11T00:00:00Z",True,True))
        self.assertTrue(verify_pregame_source("2026-11-10T18:00:00Z","2026-11-10T18:10:00Z","2026-11-11T00:00:00Z",True,True))

    def test_production_fail_closed(self):
        self.assertFalse(approve_scoring_promotion(True,True,False,True,True))


if __name__=="__main__":
    unittest.main()
