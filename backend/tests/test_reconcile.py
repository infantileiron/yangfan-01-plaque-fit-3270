import unittest

from src.business.reconcile import fold, reconcile, snapshot

STATIONS = ["1号打样台", "2号打样台"]


def rec(sample_id, station, revision, overflow):
    return {"sample_id": sample_id, "station": station, "revision": revision, "overflow": overflow}


class FoldTest(unittest.TestCase):
    def test_out_of_order_records_follow_revision(self):
        ledger = fold([rec("S1", "1号打样台", 2, "否"), rec("S1", "1号打样台", 1, "是")])
        self.assertEqual(ledger[("S1", "1号打样台")]["overflow"], "否")
        ledger = fold([rec("S1", "1号打样台", 1, "是"), rec("S1", "1号打样台", 2, "否")])
        self.assertEqual(ledger[("S1", "1号打样台")]["overflow"], "否")

    def test_same_revision_same_value_is_deduplicated(self):
        ledger = fold([rec("S1", "1号打样台", 1, "是"), rec("S1", "1号打样台", 1, "是")])
        self.assertEqual(len(ledger), 1)

    def test_same_revision_different_value_is_rejected(self):
        with self.assertRaises(ValueError):
            fold([rec("S1", "1号打样台", 1, "是"), rec("S1", "1号打样台", 1, "否")])


class ReconcileTest(unittest.TestCase):
    def test_agreement_resolves(self):
        ledger = fold([rec("S1", "1号打样台", 1, "是"), rec("S1", "2号打样台", 1, "是")])
        result = reconcile(["S1"], ledger, STATIONS)
        self.assertEqual(result["resolved"], {"S1": "是"})
        self.assertEqual(result["pending"], [])

    def test_missing_station_is_pending(self):
        result = reconcile(["S1"], fold([rec("S1", "1号打样台", 1, "是")]), STATIONS)
        self.assertEqual(result["resolved"], {})
        self.assertEqual(result["pending"][0]["reason"], "缺测")
        self.assertIn("2号打样台", result["pending"][0]["detail"])

    def test_no_records_at_all_is_pending(self):
        result = reconcile(["S1"], fold([]), STATIONS)
        self.assertEqual(result["pending"][0]["reason"], "缺测")

    def test_conflict_is_pending(self):
        ledger = fold([rec("S1", "1号打样台", 1, "是"), rec("S1", "2号打样台", 1, "否")])
        result = reconcile(["S1"], ledger, STATIONS)
        self.assertEqual(result["resolved"], {})
        self.assertEqual(result["pending"][0]["reason"], "冲突")

    def test_revision_correction_resolves_conflict(self):
        records = [rec("S1", "1号打样台", 1, "是"), rec("S1", "2号打样台", 1, "否"),
                   rec("S1", "2号打样台", 2, "是")]
        result = reconcile(["S1"], fold(records), STATIONS)
        self.assertEqual(result["resolved"], {"S1": "是"})


class SnapshotTest(unittest.TestCase):
    def test_digest_is_stable_across_arrival_order(self):
        first = snapshot([rec("S1", "1号打样台", 2, "否"), rec("S1", "1号打样台", 1, "是"),
                          rec("S1", "2号打样台", 1, "否")], ["S1"], STATIONS)
        second = snapshot([rec("S1", "2号打样台", 1, "否"), rec("S1", "1号打样台", 1, "是"),
                           rec("S1", "1号打样台", 2, "否")], ["S1"], STATIONS)
        self.assertEqual(first["digest"], second["digest"])
        self.assertEqual(first["resolved"], {"S1": "否"})

    def test_digest_changes_with_new_measurements(self):
        base = snapshot([rec("S1", "1号打样台", 1, "是")], ["S1"], STATIONS)
        more = snapshot([rec("S1", "1号打样台", 1, "是"), rec("S1", "2号打样台", 1, "是")], ["S1"], STATIONS)
        self.assertNotEqual(base["digest"], more["digest"])

    def test_unrelated_samples_do_not_change_digest(self):
        base = snapshot([rec("S1", "1号打样台", 1, "是")], ["S1"], STATIONS)
        wider = snapshot([rec("S1", "1号打样台", 1, "是"), rec("S2", "1号打样台", 1, "否")], ["S1"], STATIONS)
        self.assertEqual(base["digest"], wider["digest"])


if __name__ == "__main__":
    unittest.main()
