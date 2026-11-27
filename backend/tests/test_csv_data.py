import unittest

from src.business.profile import PROFILE
from src.utils.csv_data import parse_csv

MEASUREMENT_HEADER = "sample_id,station,revision,overflow\n"


def dataset_csv(sample_ids):
    lines = ["sample_id,split,template,lang_pair,width_mm,lines,ink_mm,overflow"]
    for sample_id in sample_ids:
        lines.append(f"{sample_id},训练,LY-T01,中文/英文,100,2,180,是")
    return "\n".join(lines) + "\n"


class DatasetParseTest(unittest.TestCase):
    def test_duplicate_sample_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "重复"):
            parse_csv(dataset_csv(["LY-H1", "LY-H1"]), PROFILE["columns"])

    def test_valid_rows_pass(self):
        rows = parse_csv(dataset_csv(["LY-H1", "LY-H2"]), PROFILE["columns"])
        self.assertEqual(len(rows), 2)


class MeasurementParseTest(unittest.TestCase):
    def parse(self, text):
        return parse_csv(text, PROFILE["measurement_columns"],
                         unique=("sample_id", "station", "revision"))

    def test_same_sample_from_two_stations_is_allowed(self):
        rows = self.parse(MEASUREMENT_HEADER + "S1,1号打样台,1,是\nS1,2号打样台,1,是\n")
        self.assertEqual(len(rows), 2)

    def test_same_key_new_revision_is_allowed(self):
        rows = self.parse(MEASUREMENT_HEADER + "S1,1号打样台,1,是\nS1,1号打样台,2,否\n")
        self.assertEqual(len(rows), 2)

    def test_exact_duplicate_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "重复"):
            self.parse(MEASUREMENT_HEADER + "S1,1号打样台,1,是\nS1,1号打样台,1,是\n")

    def test_revision_must_be_integer(self):
        with self.assertRaisesRegex(ValueError, "整数"):
            self.parse(MEASUREMENT_HEADER + "S1,1号打样台,1.5,是\n")

    def test_revision_is_returned_as_int(self):
        rows = self.parse(MEASUREMENT_HEADER + "S1,1号打样台,2,是\n")
        self.assertEqual(rows[0]["revision"], 2)
        self.assertIsInstance(rows[0]["revision"], int)

    def test_unknown_station_rejected(self):
        with self.assertRaisesRegex(ValueError, "打样台"):
            self.parse(MEASUREMENT_HEADER + "S1,3号打样台,1,是\n")

    def test_overflow_choices_enforced(self):
        with self.assertRaisesRegex(ValueError, "实测溢出"):
            self.parse(MEASUREMENT_HEADER + "S1,1号打样台,1,未知\n")


if __name__ == "__main__":
    unittest.main()
