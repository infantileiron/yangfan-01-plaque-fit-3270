import unittest

from src.business.algorithm import analyze

STATIONS = ["1号打样台", "2号打样台"]


def row(sample_id, split, template, ratio, overflow=None):
    return {
        "sample_id": sample_id, "split": split, "template": template, "lang_pair": "中文/英文",
        "width_mm": 100, "lines": 2, "ink_mm": 100 * 2 * ratio, "overflow": overflow,
    }


# 训练批：TA 低占位也溢出、TB 高占位也不溢出，几何基准只能学到反向占位系数，
# 目标编码能学到版式差异，方便构造两版模型分歧确定的场景。
TRAINING = [row(f"T{i:02}", "训练", "TA", 0.7, "是") for i in range(20)] + \
           [row(f"T{i:02}", "训练", "TB", 1.3, "否") for i in range(20, 40)]
CANDIDATES = [row("P01", "待校", "TA", 0.7), row("P02", "待校", "TB", 1.3), row("P03", "待校", "TA", 0.9)]


def evidence(resolved, pending=()):
    return {
        "resolved": resolved, "stations": STATIONS, "digest": "0" * 64,
        "pending": [{"sample_id": sid, "reason": reason, "detail": "对账待定"} for sid, reason in pending],
    }


def metric(result, label):
    return next(item["value"] for item in result["metrics"] if item["label"] == label)


def run_case(aligned_specs, pending_specs=()):
    """aligned_specs/pending_specs: [(sample_id, template, ratio, label_or_None)], 留出实测以证据快照为准。"""
    rows = list(TRAINING) + list(CANDIDATES)
    resolved = {}
    pending = []
    for sample_id, template, ratio, label in aligned_specs:
        rows.append(row(sample_id, "留出", template, ratio))
        resolved[sample_id] = label
    for sample_id, template, ratio in pending_specs:
        rows.append(row(sample_id, "留出", template, ratio))
        pending.append((sample_id, "冲突"))
    return analyze(rows, 0.6, evidence(resolved, pending))


class VersionSelectionTest(unittest.TestCase):
    def test_fragile_lead_stays_provisional(self):
        # 已对齐部分两版打平，待定纸样可能翻转结论：暂用几何基准并注明暂用依据。
        aligned = [(f"H{i:02}", "TA", 0.7, "是") for i in range(7)] + \
                  [(f"H{i:02}", "TB", 1.3, "否") for i in range(7, 14)]
        result = run_case(aligned, [("H99", "TA", 1.3)])
        self.assertEqual(metric(result, "择优口径"), "暂用")
        self.assertEqual(metric(result, "本批择优"), "几何基准")
        self.assertEqual(metric(result, "待定纸样"), 1)
        self.assertIn("暂用", result["summary"])
        self.assertTrue(all("暂用几何基准版" in item["evidence"] for item in result["rows"]))
        self.assertTrue(any("复测到齐后重判" in note for note in result["notes"]))
        self.assertTrue(any("两台冲突 1 条" in note for note in result["notes"]))

    def test_robust_lead_switches_version_firmly(self):
        # 待定纸样无论怎么判目标编码都领先：换版且结论正式。
        aligned = [(f"H{i:02}", "TA", 1.3, "是") for i in range(12)] + \
                  [(f"H{i:02}", "TB", 1.3, "否") for i in range(12, 14)]
        result = run_case(aligned, [("H99", "TA", 1.3)])
        self.assertEqual(metric(result, "本批择优"), "目标编码")
        self.assertEqual(metric(result, "择优口径"), "正式")
        self.assertTrue(all("暂用" not in item["evidence"] for item in result["rows"]))
        self.assertTrue(any("均不影响" in note for note in result["notes"]))

    def test_robust_loss_keeps_incumbent_firmly(self):
        # 留出标签与版式训练模式相反：目标编码铁定落后，留任结论正式。
        aligned = [(f"H{i:02}", "TA", 1.3, "否") for i in range(12)] + \
                  [(f"H{i:02}", "TB", 0.7, "是") for i in range(12, 14)]
        result = run_case(aligned, [("H99", "TA", 1.3)])
        self.assertEqual(metric(result, "本批择优"), "几何基准")
        self.assertEqual(metric(result, "择优口径"), "正式")

    def test_no_pending_is_always_firm(self):
        aligned = [(f"H{i:02}", "TA", 1.3, "是") for i in range(12)] + \
                  [(f"H{i:02}", "TB", 1.3, "否") for i in range(12, 14)]
        result = run_case(aligned)
        self.assertEqual(metric(result, "择优口径"), "正式")
        self.assertEqual(metric(result, "待定纸样"), 0)
        self.assertTrue(any("同一批实测快照" in note for note in result["notes"]))


class EvidenceContractTest(unittest.TestCase):
    def test_holdout_labels_come_from_evidence_not_rows(self):
        # 底稿留出列即使误填也以对账快照为准。
        rows = list(TRAINING) + list(CANDIDATES)
        resolved = {}
        for i in range(14):
            sample_id = f"H{i:02}"
            rows.append(row(sample_id, "留出", "TA" if i % 2 else "TB", 0.7 if i % 2 else 1.3, overflow="是"))
            resolved[sample_id] = "是" if i % 2 else "否"
        result = analyze(rows, 0.6, evidence(resolved))
        self.assertEqual(metric(result, "已对齐留出"), 14)

    def test_too_few_aligned_stops_calculation(self):
        aligned = [(f"H{i:02}", "TA", 0.7, "是") for i in range(6)] + \
                  [(f"H{i:02}", "TB", 1.3, "否") for i in range(6, 11)]
        with self.assertRaisesRegex(ValueError, "已对齐"):
            run_case(aligned, [("H98", "TA", 1.3), ("H99", "TB", 0.7), ("H97", "TA", 0.9)])

    def test_candidate_with_measurement_rejected(self):
        rows = list(TRAINING) + [row("P01", "待校", "TA", 0.7, overflow="否")]
        resolved = {}
        for i in range(14):
            rows.append(row(f"H{i:02}", "留出", "TA", 0.7))
            resolved[f"H{i:02}"] = "是" if i % 2 else "否"
        with self.assertRaisesRegex(ValueError, "待校"):
            analyze(rows, 0.6, evidence(resolved))


if __name__ == "__main__":
    unittest.main()
