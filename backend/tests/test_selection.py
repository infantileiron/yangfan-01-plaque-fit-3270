import unittest

from src.business.selection import compare


class CompareTest(unittest.TestCase):
    def test_no_pending_plain_comparison(self):
        self.assertEqual(compare(-0.1, []), (True, True))
        self.assertEqual(compare(0.1, []), (False, True))
        self.assertEqual(compare(0.0, []), (False, True))

    def test_challenger_leads_under_every_judgment_switches(self):
        self.assertEqual(compare(-2.0, [(0.8, -0.2), (0.5, -0.5)]), (True, True))

    def test_incumbent_leads_under_every_judgment_is_firm(self):
        self.assertEqual(compare(2.0, [(-0.8, 0.2)]), (False, True))

    def test_pending_can_flip_outcome_is_provisional(self):
        use_challenger, firm = compare(-0.5, [(0.8, -0.2)])
        self.assertFalse(use_challenger)
        self.assertFalse(firm)

    def test_exact_boundary(self):
        self.assertEqual(compare(-0.8, [(0.8, -0.8)]), (False, False))
        self.assertEqual(compare(0.8, [(-0.8, 0.8)]), (False, False))


if __name__ == "__main__":
    unittest.main()
