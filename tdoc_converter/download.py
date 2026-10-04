"""Download Tdoc zip files from the 3GPP FTP server and unzip them."""
from __future__ import annotations

import re
import time
import zipfile
from pathlib import Path

import requests

FTP_BASE = "https://ftp.3gpp.org/tsg_ran/WG1_RL1"
# The server rejects the default python-requests agent with 403.
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def resolve_meeting_folder(candidates: list[str], session: requests.Session | None = None) -> str:
    """Fallback only: pick the candidate that exists in the WG1 FTP directory listing."""
    s = session or requests.Session()
    try:
        r = s.get(FTP_BASE + "/", headers=HEADERS, timeout=60)
        r.raise_for_status()
        existing = set(re.findall(r"TSGR1_[0-9A-Za-z_-]+", r.text))
    except requests.RequestException:
        return candidates[0]
    for c in candidates:
        if c in existing:
            return c
    raise FileNotFoundError(f"none of {candidates} found on {FTP_BASE}")


def zip_url(folder: str, tdoc: str) -> str:
    """Fallback URL built from the naming rule (used when the xlsx has no hyperlink)."""
    return f"{FTP_BASE}/{folder}/Docs/{tdoc}.zip"


def folder_from_url(url: str) -> str | None:
    m = re.search(r"/(TSGR\d+_[^/]+)/Docs/", url)
    return m.group(1) if m else None


def download_zip(tdoc: str, url: str, dest_dir: Path, session: requests.Session | None = None,
                 retries: int = 3) -> Path:
    """Download `url` into dest_dir/<tdoc>.zip (skipped if a valid zip is already there)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{tdoc}.zip"
    if dest.exists() and zipfile.is_zipfile(dest):
        return dest
    s = session or requests.Session()
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with s.get(url, headers=HEADERS, timeout=120, stream=True) as r:
                r.raise_for_status()
                tmp = dest.with_suffix(".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        f.write(chunk)
            if not zipfile.is_zipfile(tmp):  # server may answer 200 with an HTML error page
                tmp.unlink()
                raise ValueError(f"{url} did not return a zip file")
            tmp.replace(dest)
            return dest
        except (requests.RequestException, ValueError) as e:
            last = e
            if isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code == 404:
                break
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"download failed for {url}: {last}")


def check_url(url: str, session: requests.Session) -> str:
    """Probe a download URL with HEAD; return '' if it looks like a downloadable zip, else the problem."""
    try:
        r = session.head(url, headers=HEADERS, timeout=60, allow_redirects=True)
    except requests.RequestException as e:
        return f"{type(e).__name__}: {e}"
    ctype = r.headers.get("Content-Type", "")
    if r.status_code != 200:
        return f"HTTP {r.status_code}"
    if "zip" not in ctype.lower():
        return f"unexpected Content-Type {ctype!r}"
    return ""


def check_urls(urls: dict[str, str], session: requests.Session | None = None,
               workers: int = 4) -> dict[str, str]:
    """HEAD-check {tdoc: url} concurrently; return {tdoc: problem} for the failures only."""
    from concurrent.futures import ThreadPoolExecutor
    s = session or requests.Session()
    with ThreadPoolExecutor(workers) as ex:
        problems = list(ex.map(lambda kv: check_url(kv[1], s), urls.items()))
    return {t: p for t, p in zip(urls, problems) if p}


def unzip(zip_path: Path, out_dir: Path) -> list[Path]:
    """Extract zip into out_dir; return extracted file paths (zipfile strips unsafe '..' paths)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out_dir)
        return [out_dir / n for n in z.namelist() if not n.endswith("/")]


def pick_document(files: list[Path]) -> Path | None:
    """Choose the main document: docx > pptx > doc/ppt, largest first; ignore temp files."""
    rank = {".docx": 0, ".pptx": 1, ".doc": 2, ".ppt": 3}
    cands = [f for f in files if f.suffix.lower() in rank and not f.name.startswith(("~$", "."))
             and "__MACOSX" not in f.parts]
    cands.sort(key=lambda f: (rank[f.suffix.lower()], -f.stat().st_size))
    return cands[0] if cands else None
