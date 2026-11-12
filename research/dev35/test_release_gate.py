import unittest

from research.dev35.release_gate import ApprovalEvidence, can_promote_production, can_retrain_research, status


class TestDev35Gate(unittest.TestCase):
    def test_missing_asof_is_blocked(self):
        e=ApprovalEvidence(False,True,True,True,True,True,True,True,True)
        self.assertFalse(can_promote_production(e))
        self.assertEqual(status(e),'BLOCKED_NO_PRODUCTION_PROMOTION')

    def test_kbl_win5_logloss_worse_is_blocked(self):
        e=ApprovalEvidence(True,True,True,True,False,False,True,True,True)
        self.assertFalse(can_promote_production(e))

    def test_research_candidate_is_separate(self):
        self.assertTrue(can_retrain_research(True,True,True,True))
        self.assertFalse(can_retrain_research(True,True,False,True))


if __name__=='__main__':unittest.main()
