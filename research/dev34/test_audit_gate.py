import unittest

from research.dev34.audit_gate import (
    can_settle, asof_eligible, result_check, win5,
    audit, training_gate, production_promotion_gate,
)


class TestAuditGate(unittest.TestCase):
    def test_results_gate(self):
        self.assertTrue(can_settle("CONFIRMED_CROSS_SOURCE"))
        self.assertFalse(can_settle("PROVISIONAL_SINGLE_RECAP_SOURCE"))
        self.assertFalse(can_settle("SCHEDULED_NOT_PLAYED"))

    def test_win5_bounds(self):
        self.assertEqual([win5(x) for x in (6, 5, -5, -6)], ["승", "5", "5", "패"])
        with self.assertRaises(ValueError):
            result_check(90, 90)
        self.assertTrue(result_check(114, 101, 55, 50, 59, 51))

    def test_source_timing(self):
        self.assertFalse(asof_eligible(None, None, "2026-11-12T11:00:00Z", True, True))
        self.assertFalse(asof_eligible(
            "2026-11-12T12:00:00Z", "2026-11-12T12:10:00Z",
            "2026-11-12T11:00:00Z", True, True))

    def test_postgame_and_promotion_block(self):
        self.assertFalse(training_gate("CONFIRMED_CROSS_SOURCE", True, True, True))
        self.assertFalse(production_promotion_gate(True, True, False, True, True, True))

    def test_miss_diagnostics(self):
        x = audit(116, 111, 111, 145)
        self.assertEqual(x["margin_mae"], 39)
        self.assertIn("WINNER_MISS", x["tags"])


if __name__ == "__main__":
    unittest.main()
