import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import openpyxl

from tdoc_converter import pipeline
from tests.test_convert import make_docx_with_label_numbering


class PipelineTest(unittest.TestCase):
    def test_end_to_end_offline(self):
        tmp = Path(tempfile.mkdtemp())
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "TDoc_List"
        ws.append(["TDoc", "Title", "Source", "Agenda item", "TDoc Status", "Uploaded"])
        ws.append(["R1-1", "t1", "Acme", "10.5.2.2", "available", "2026-10-01"])
        ws["A2"].hyperlink = "https://www.3gpp.org/ftp/tsg_ran/WG1_RL1/TSGR1_126b/Docs/R1-1.Zip"
        ws.append(["R1-2", "t2", "Beta", "10.5.2.2", "available", "2026-10-01"])   # broken zip content
        ws.append(["R1-3", "t3", "Gamma", "10.5.2.2", "reserved", None])
        ws.append(["R1-4", "t4", "Delta", "10.5.2.3", "available", "2026-10-01"])
        xlsx = tmp / "TDoc_List_Meeting_RAN1#126-bis.xlsx"
        wb.save(xlsx)

        docx = tmp / "d.docx"
        make_docx_with_label_numbering(docx)

        requested = {}

        def fake_download(tdoc, url, dest_dir, session=None, retries=3):
            requested[tdoc] = url
            dest_dir.mkdir(parents=True, exist_ok=True)
            z = dest_dir / f"{tdoc}.zip"
            with zipfile.ZipFile(z, "w") as zf:
                if tdoc == "R1-1":
                    zf.write(docx, f"{tdoc} title.docx")
                else:
                    zf.writestr("readme.txt", "no document")
            return z

        with mock.patch.object(pipeline.download, "download_zip", fake_download), \
                mock.patch("time.sleep"):
            results = pipeline.run(xlsx, "10.5.2.2", tmp / "out")

        self.assertEqual([r.tdoc.number for r in results], ["R1-1", "R1-2"])   # reserved/other item skipped
        # R1-1 uses its hyperlink verbatim (and names the folder); R1-2 has none -> rule-based fallback
        self.assertTrue(requested["R1-1"].endswith("/TSGR1_126b/Docs/R1-1.Zip"))
        self.assertEqual(requested["R1-2"], "https://ftp.3gpp.org/tsg_ran/WG1_RL1/TSGR1_126b/Docs/R1-2.zip")
        self.assertEqual(len(results[0].statements), 3)
        self.assertIn("no docx", results[1].error)
        res_dir = tmp / "out" / "TSGR1_126b" / "10.5.2.2" / "results"
        data = json.loads((res_dir / "observations_proposals.json").read_text())
        self.assertEqual(data[0]["company"], "Acme")
        self.assertEqual(data[0]["tdocs"][0]["statements"][0]["text"], "Support single TB over 400 MHz.")
        with (res_dir / "observations_proposals.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], ["Tdoc", "Agenda item", "Company", "Type", "Theme", "Text"])
        self.assertEqual(len(rows), 4)          # header + the 3 statements of R1-1
        self.assertEqual(rows[1][:4], ["R1-1", "10.5.2.2", "Acme", "Proposal"])
        self.assertEqual(rows[1][5], "Support single TB over 400 MHz.")
        report = (res_dir / "observations_proposals.md").read_text()
        self.assertIn("R1-3", report)               # listed under "Not downloaded"
        self.assertIn("extraction failed", report)


if __name__ == "__main__":
    unittest.main()
