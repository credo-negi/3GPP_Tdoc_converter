import csv
import json
import tempfile
import unittest
from pathlib import Path

from tdoc_converter.extract import Statement
from tdoc_converter.pipeline import Result
from tdoc_converter.report import group_by_company, write_reports
from tdoc_converter.tdoc_list import Tdoc


def result(number, source, *statements, item="10.5.2.2"):
    return Result(Tdoc(number, "title " + number, source, item, "available", True), list(statements))


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.results = [
            result("R1-1", "Acme", Statement("Proposal", "1", "P1 a\nb", "DMRS"),
                   Statement("Observation", "1", "O1", ""), Statement("Proposal", "2", "P2, \"quoted\"", "")),
            result("R1-2", "Beta", Statement("Observation", "1", "O2", "TDRA")),
            result("R1-3", "Acme", Statement("Proposal", "1", "P3", "FDRA")),
        ]

    def test_groups_keep_first_appearance_order(self):
        groups = group_by_company(self.results)
        self.assertEqual(list(groups), ["Acme", "Beta"])
        self.assertEqual([r.tdoc.number for r in groups["Acme"]], ["R1-1", "R1-3"])

    def test_csv_json_md_are_per_company_in_order_with_kinds_interleaved(self):
        out = Path(tempfile.mkdtemp())
        write_reports(self.results, [], out, "10.5.2.2")

        with (out / "observations_proposals.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], ["Tdoc", "Agenda item", "Company", "Type", "Theme", "Text"])
        self.assertEqual([(r[0], r[2], r[3]) for r in rows[1:]],
                         [("R1-1", "Acme", "Proposal"), ("R1-1", "Acme", "Observation"),
                          ("R1-1", "Acme", "Proposal"), ("R1-3", "Acme", "Proposal"),
                          ("R1-2", "Beta", "Observation")])
        self.assertEqual(rows[1][4:], ["DMRS", "P1 a\nb"])      # multi-line text survives quoting
        self.assertEqual(rows[3][5], 'P2, "quoted"')

        data = json.loads((out / "observations_proposals.json").read_text())
        self.assertEqual([c["company"] for c in data], ["Acme", "Beta"])
        self.assertEqual(data[0]["tdocs"][0]["statements"][0]["theme"], "DMRS")

        md = (out / "observations_proposals.md").read_text()
        self.assertLess(md.index("## Acme"), md.index("## Beta"))
        self.assertLess(md.index("**Proposal 1**"), md.index("**Observation 1**"))


if __name__ == "__main__":
    unittest.main()
