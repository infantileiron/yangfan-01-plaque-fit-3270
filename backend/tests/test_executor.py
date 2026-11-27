import unittest
from datetime import timedelta

import tests.dbenv  # noqa: F401  先于 src 导入设置测试环境

from migrations.bootstrap import migrate
from src.config.settings import Session, engine
from src.models.base import utcnow
from src.models.dataset import Dataset
from src.models.run import Run
from src.services import measurements
from src.services.executor import claim, execute
from src.utils.csv_data import digest


def row(sample_id, split, template, ratio, overflow=None):
    return {
        "sample_id": sample_id, "split": split, "template": template, "lang_pair": "中文/英文",
        "width_mm": 100, "lines": 2, "ink_mm": 100 * 2 * ratio, "overflow": overflow,
    }


ROWS = [row(f"EX-T{i:02}", "训练", "TA", 0.7, "是") for i in range(20)] + \
       [row(f"EX-T{i:02}", "训练", "TB", 1.3, "否") for i in range(20, 40)] + \
       [row(f"EX-H{i:02}", "留出", "TA" if i % 2 else "TB", 0.7 if i % 2 else 1.3) for i in range(1, 15)] + \
       [row("EX-P1", "待校", "TA", 0.7), row("EX-P2", "待校", "TB", 1.3), row("EX-P3", "待校", "TA", 0.9)]


def report(sample_id, label):
    return [{"sample_id": sample_id, "station": station, "revision": 1, "overflow": label}
            for station in ("1号打样台", "2号打样台")]


def metrics_of(run):
    return {item["label"]: item["value"] for item in run.result["metrics"]}


class ExecutorSnapshotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(engine)

    def test_snapshot_frozen_across_retry_and_remeasure_triggers_rejudge(self):
        with Session.begin() as db:
            dataset = Dataset(name="exec", checksum=digest(ROWS), rows=ROWS, author="test")
            db.add(dataset)
            db.flush()
            records = [item for i in range(1, 13)
                       for item in report(f"EX-H{i:02}", "是" if i % 2 else "否")]
            self.assertEqual(measurements.apply_records(db, records, "test")["applied"], 24)
            run = Run(dataset_id=dataset.id, label="第一班", parameter=0.6, actor="test")
            db.add(run)
            db.flush()
            run_id = run.id

        job = claim()
        self.assertEqual(job[0], run_id)
        frozen = job[4]
        self.assertEqual(len(frozen["resolved"]), 12)
        self.assertEqual(len(frozen["pending"]), 2)

        # 第一次认领之后复测才到齐。
        with Session.begin() as db:
            rest = [item for i in (13, 14) for item in report(f"EX-H{i:02}", "否")]
            measurements.apply_records(db, rest, "test")

        # 模拟途中断了：租约过期后重试，不重复采信，仍用同一批实测快照。
        with Session.begin() as db:
            db.get(Run, run_id).started_at = utcnow() - timedelta(minutes=11)
        retry = claim()
        self.assertEqual(retry[0], run_id)
        self.assertEqual(retry[4]["digest"], frozen["digest"])
        self.assertEqual(len(retry[4]["pending"]), 2)

        execute(retry)
        with Session() as db:
            finished = db.get(Run, run_id)
            self.assertEqual(finished.status, "succeeded")
            metrics = metrics_of(finished)
            self.assertEqual(metrics["待定纸样"], 2)
            self.assertEqual(metrics["已对齐留出"], 12)
            self.assertEqual(metrics["实测快照"], frozen["digest"][:12])

        # 复测到齐后重判：新计算单冻结新快照，择优口径转正式。
        with Session.begin() as db:
            follow = Run(dataset_id=finished.dataset_id, label="复测后", parameter=0.6, actor="test")
            db.add(follow)
            db.flush()
            follow_id = follow.id
        job = claim()
        self.assertEqual(job[0], follow_id)
        self.assertEqual(len(job[4]["pending"]), 0)
        self.assertNotEqual(job[4]["digest"], frozen["digest"])
        execute(job)
        with Session() as db:
            metrics = metrics_of(db.get(Run, follow_id))
            self.assertEqual(metrics["待定纸样"], 0)
            self.assertEqual(metrics["已对齐留出"], 14)
            self.assertEqual(metrics["择优口径"], "正式")


if __name__ == "__main__":
    unittest.main()
