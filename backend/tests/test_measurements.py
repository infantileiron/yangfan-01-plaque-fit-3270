import unittest

import tests.dbenv  # noqa: F401  先于 src 导入设置测试环境

from fastapi import HTTPException
from sqlalchemy import select

from migrations.bootstrap import migrate
from src.config.settings import Session, engine
from src.models.audit import Event
from src.services import measurements

HEADER = "sample_id,station,revision,overflow\n"


def rec(sample_id, station, revision, overflow):
    return {"sample_id": sample_id, "station": station, "revision": revision, "overflow": overflow}


class ApplyRecordsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(engine)

    def test_retry_does_not_double_count(self):
        batch = [rec("T-S1", "1号打样台", 1, "是"), rec("T-S1", "2号打样台", 1, "是")]
        with Session.begin() as db:
            self.assertEqual(measurements.apply_records(db, batch, "tester"),
                             {"applied": 2, "unchanged": 0, "stale": 0})
        with Session.begin() as db:
            self.assertEqual(measurements.apply_records(db, batch, "tester"),
                             {"applied": 0, "unchanged": 2, "stale": 0})

    def test_out_of_order_revision_kept_and_stale_ignored(self):
        with Session.begin() as db:
            measurements.apply_records(db, [rec("T-S2", "1号打样台", 2, "否")], "tester")
        with Session.begin() as db:
            counts = measurements.apply_records(db, [rec("T-S2", "1号打样台", 1, "是")], "tester")
        self.assertEqual(counts["stale"], 1)
        with Session.begin() as db:
            measurements.apply_records(db, [rec("T-S2", "2号打样台", 1, "否")], "tester")
        with Session() as db:
            snap = measurements.snapshot_for(db, ["T-S2"])
        self.assertEqual(snap["resolved"], {"T-S2": "否"})

    def test_same_revision_different_value_rejected(self):
        with Session.begin() as db:
            measurements.apply_records(db, [rec("T-S3", "1号打样台", 1, "是")], "tester")
        with self.assertRaises(HTTPException):
            with Session.begin() as db:
                measurements.apply_records(db, [rec("T-S3", "1号打样台", 1, "否")], "tester")
        with Session() as db:
            snap = measurements.snapshot_for(db, ["T-S3"])
        self.assertEqual(snap["pending"][0]["reason"], "缺测")

    def test_ingest_csv_counts_and_audit(self):
        csv_text = HEADER + "T-S4,1号打样台,1,是\nT-S4,2号打样台,1,否\n"
        first = measurements.ingest(csv_text, "ingest-tester")
        self.assertEqual((first["received"], first["applied"], first["unchanged"]), (2, 2, 0))
        again = measurements.ingest(csv_text, "ingest-tester")
        self.assertEqual((again["applied"], again["unchanged"]), (0, 2))
        with Session() as db:
            actions = db.scalars(select(Event.action).where(
                Event.action == "measurements_ingested", Event.actor == "ingest-tester")).all()
        self.assertEqual(len(actions), 2)

    def test_ingest_rejects_bad_csv(self):
        with self.assertRaises(HTTPException):
            measurements.ingest(HEADER + "T-S5,1号打样台,1,是\nT-S5,1号打样台,1,否\n", "tester")


if __name__ == "__main__":
    unittest.main()
