import unittest

import tests.dbenv  # noqa: F401  先于 src 导入设置测试环境

from migrations.bootstrap import migrate
from src.business.algorithm import analyze
from src.business.demo import demo_batch
from src.business.profile import PROFILE
from src.config.settings import Session, engine
from src.services import measurements
from src.services.datasets import check_split_labels
from src.utils.csv_data import parse_csv, render_csv

REMEASURE_CSV = (
    "sample_id,station,revision,overflow\n"
    "LY-H204,1号打样台,2,否\n"
    "LY-H210,2号打样台,1,否\n"
    "LY-H223,2号打样台,2,是\n"
)


def metrics_of(result):
    return {item["label"]: item["value"] for item in result["metrics"]}


class DemoFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(engine)

    def test_seed_reconcile_and_remeasure_flow(self):
        rows, records = demo_batch()
        columns = PROFILE["columns"]
        parsed = parse_csv(render_csv(rows, [column["key"] for column in columns]), columns)
        check_split_labels(parsed)
        holdout_ids = [row["sample_id"] for row in parsed if row["split"] == "留出"]
        self.assertEqual(len(holdout_ids), 48)

        with Session.begin() as db:
            counts = measurements.apply_records(db, records, "seed")
        self.assertEqual(counts["applied"], len({(r["sample_id"], r["station"]) for r in records}))

        with Session() as db:
            snap = measurements.snapshot_for(db, holdout_ids)
        self.assertEqual(len(snap["resolved"]), 45)
        reasons = {item["sample_id"]: item["reason"] for item in snap["pending"]}
        self.assertEqual(reasons, {"LY-H204": "冲突", "LY-H210": "缺测", "LY-H223": "冲突"})
        self.assertEqual(snap["resolved"]["LY-H237"], "否")  # 乱序到达以修订号 2 为准

        result = analyze(parsed, 0.6, snap)
        self.assertEqual(len(result["rows"]), 8)
        metrics = metrics_of(result)
        self.assertEqual(metrics["待定纸样"], 3)
        self.assertEqual(metrics["择优口径"], "暂用")
        self.assertEqual(metrics["本批择优"], "几何基准")
        self.assertTrue(all("暂用" in item["evidence"] for item in result["rows"]))
        self.assertIn("暂用", result["summary"])
        decisions = {item["sample_id"]: item["decision"] for item in result["rows"]}
        self.assertEqual(decisions["LY-P01"], "人工重排")
        self.assertEqual(decisions["LY-P08"], "补纸样")

        # 复测到齐后重判：待定清零，正式换用目标编码版。
        follow = measurements.ingest(REMEASURE_CSV, "analyst")
        self.assertEqual(follow["applied"], 3)
        with Session() as db:
            complete = measurements.snapshot_for(db, holdout_ids)
        self.assertEqual(complete["pending"], [])
        final = analyze(parsed, 0.6, complete)
        metrics = metrics_of(final)
        self.assertEqual(metrics["待定纸样"], 0)
        self.assertEqual(metrics["择优口径"], "正式")
        self.assertEqual(metrics["本批择优"], "目标编码")
        self.assertNotEqual(complete["digest"], snap["digest"])

        # 种子与回传重放都不重复采信。
        with Session.begin() as db:
            self.assertEqual(measurements.apply_records(db, records, "seed")["applied"], 0)
        again = measurements.ingest(REMEASURE_CSV, "analyst")
        self.assertEqual(again["applied"], 0)


if __name__ == "__main__":
    unittest.main()
