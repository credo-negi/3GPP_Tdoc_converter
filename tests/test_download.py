import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import requests

from tdoc_converter import download


def make_zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, c in files.items():
            z.writestr(n, c)
    return buf.getvalue()


class FakeResponse:
    def __init__(self, content, status=200):
        self.content, self.status_code = content, status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def iter_content(self, n):
        yield self.content


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        mock.patch("time.sleep").start()
        self.addCleanup(mock.patch.stopall)

    def test_fallback_url_and_folder_from_url(self):
        self.assertEqual(download.zip_url("TSGR1_126b", "R1-2607006"),
                         "https://ftp.3gpp.org/tsg_ran/WG1_RL1/TSGR1_126b/Docs/R1-2607006.zip")
        self.assertEqual(download.folder_from_url(
            "https://www.3gpp.org/ftp/tsg_ran/WG1_RL1/TSGR1_126b/Docs/R1-2606970.zip"), "TSGR1_126b")
        self.assertIsNone(download.folder_from_url("https://example.com/x.zip"))

    def test_check_url(self):
        s = mock.Mock()
        ok = mock.Mock(status_code=200, headers={"Content-Type": "application/x-zip-compressed"})
        html = mock.Mock(status_code=200, headers={"Content-Type": "text/html"})
        forbidden = mock.Mock(status_code=403, headers={})
        s.head.side_effect = [ok, html, forbidden, requests.ConnectionError("down")]
        got = [download.check_url("u", s) for _ in range(4)]
        self.assertEqual(got[0], "")
        self.assertIn("Content-Type", got[1])
        self.assertEqual(got[2], "HTTP 403")
        self.assertIn("ConnectionError", got[3])

    def test_check_urls_reports_failures_only(self):
        s = mock.Mock()
        s.head.side_effect = lambda url, **kw: mock.Mock(
            status_code=200 if "good" in url else 404, headers={"Content-Type": "application/zip"})
        self.assertEqual(download.check_urls({"A": "good", "B": "bad"}, s, workers=1), {"B": "HTTP 404"})

    def test_download_and_unzip_and_cache(self):
        s = mock.Mock()
        s.get.return_value = FakeResponse(make_zip_bytes({"R1-1 title.docx": "x", "~$tmp.docx": "y"}))
        z = download.download_zip("R1-1", "http://h/R1-1.zip", self.tmp, s)
        self.assertTrue(zipfile.is_zipfile(z))
        download.download_zip("R1-1", "http://h/R1-1.zip", self.tmp, s)
        self.assertEqual(s.get.call_count, 1)  # cached
        self.assertEqual(s.get.call_args.args[0], "http://h/R1-1.zip")  # the given URL is used verbatim
        files = download.unzip(z, self.tmp / "out")
        self.assertEqual(download.pick_document(files).name, "R1-1 title.docx")

    def test_html_error_page_is_rejected(self):
        s = mock.Mock()
        s.get.return_value = FakeResponse(b"<html>blocked</html>")
        with self.assertRaises(RuntimeError):
            download.download_zip("R1-1", "http://h/R1-1.zip", self.tmp, s, retries=2)
        self.assertFalse((self.tmp / "R1-1.zip").exists())

    def test_404_is_not_retried(self):
        s = mock.Mock()
        s.get.return_value = FakeResponse(b"", 404)
        with self.assertRaises(RuntimeError):
            download.download_zip("R1-1", "http://h/R1-1.zip", self.tmp, s, retries=3)
        self.assertEqual(s.get.call_count, 1)

    def test_pick_document_prefers_docx_over_pptx(self):
        for n, size in (("a.pptx", 500), ("b.docx", 10), ("c.txt", 900)):
            (self.tmp / n).write_bytes(b"0" * size)
        picked = download.pick_document([self.tmp / n for n in ("a.pptx", "b.docx", "c.txt")])
        self.assertEqual(picked.name, "b.docx")
        self.assertIsNone(download.pick_document([self.tmp / "c.txt"]))


if __name__ == "__main__":
    unittest.main()
