"""End-to-end run for one agenda item: list -> download -> unzip -> markdown -> extract."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests

from . import download, extract
from .convert import convert_to_file
from .tdoc_list import Tdoc, load_tdoc_list, meeting_folder_candidates, select_agenda_item


@dataclass
class Result:
    tdoc: Tdoc
    statements: list[extract.Statement] = field(default_factory=list)
    error: str = ""


def _folder_from_links(tdocs: list[Tdoc]) -> str | None:
    """Meeting folder named by the xlsx hyperlinks (the authoritative source)."""
    folders = {download.folder_from_url(t.url) for t in tdocs if t.url} - {None}
    if len(folders) > 1:
        raise SystemExit(f"hyperlinks point to several meeting folders: {sorted(folders)}")
    return folders.pop() if folders else None


def process_tdoc(tdoc: Tdoc, folder: str, work: Path, session: requests.Session) -> Result:
    res = Result(tdoc)
    try:
        url = tdoc.url or download.zip_url(folder, tdoc.number)
        zip_path = download.download_zip(tdoc.number, url, work / "zip", session)
        files = download.unzip(zip_path, work / "extracted" / tdoc.number)
        doc = download.pick_document(files)
        if doc is None:
            raise RuntimeError("no docx/pptx/doc/ppt in zip: " + ", ".join(f.name for f in files))
        md_path = convert_to_file(doc, work / "markdown" / f"{tdoc.number}.md")
        res.statements = extract.extract_statements(md_path.read_text(encoding="utf-8"))
    except Exception as e:  # keep going: one broken Tdoc must not abort the batch
        res.error = f"{type(e).__name__}: {e}"
    return res


def run(xlsx: Path, agenda_item: str, out_root: Path, folder: str | None = None,
        limit: int | None = None, delay: float = 0.5, check_urls: bool = False) -> list[Result]:
    tdocs = select_agenda_item(load_tdoc_list(xlsx), agenda_item)
    if not tdocs:
        raise SystemExit(f"no Tdocs for agenda item {agenda_item!r} in {xlsx}")
    session = requests.Session()
    folder = folder or _folder_from_links(tdocs) or download.resolve_meeting_folder(
        meeting_folder_candidates(xlsx), session)
    work = out_root / folder / agenda_item
    if check_urls:
        problems = download.check_urls({t.number: t.url for t in tdocs if t.url}, session)
        print(f"URL check: {sum(bool(t.url) for t in tdocs) - len(problems)} ok, {len(problems)} problems")
        for n, p in problems.items():
            print(f"  {n}: {p}")
        return []
    targets = [t for t in tdocs if t.downloadable][:limit]
    skipped = [t for t in tdocs if not t.downloadable]
    print(f"{agenda_item}: {len(tdocs)} Tdocs, {len(targets)} to process, {len(skipped)} not available "
          f"(folder {folder})")

    results = []
    for n, t in enumerate(targets, 1):
        r = process_tdoc(t, folder, work, session)
        obs = sum(s.kind == "Observation" for s in r.statements)
        print(f"[{n}/{len(targets)}] {t.number} {t.source[:30]:30} "
              + (f"ERROR {r.error}" if r.error else f"obs={obs} prop={len(r.statements) - obs}"))
        results.append(r)
        time.sleep(delay)
    write_reports(results, skipped, work / "results", agenda_item)
    return results


def write_reports(results: list[Result], skipped: list[Tdoc], out_dir: Path, agenda_item: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = [{"tdoc": r.tdoc.number, "title": r.tdoc.title, "source": r.tdoc.source, "error": r.error,
             "statements": [{"kind": s.kind, "id": s.id, "section": s.section, "text": s.text,
                             "occurrences": s.occurrences} for s in r.statements]} for r in results]
    (out_dir / "observations_proposals.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [f"# Agenda item {agenda_item}: observations and proposals", ""]
    for kind in ("Observation", "Proposal"):
        total = sum(s.kind == kind for r in results for s in r.statements)
        md.append(f"- {kind}s: {total}")
    md.append("")
    for r in results:
        md += [f"## {r.tdoc.number} — {r.tdoc.source}", f"*{r.tdoc.title}*", ""]
        if r.error:
            md += [f"> extraction failed: {r.error}", ""]
            continue
        if not r.statements:
            md += ["> no Observation/Proposal found", ""]
        for kind in ("Observation", "Proposal"):
            items = [s for s in r.statements if s.kind == kind]
            if items:
                md += [f"### {kind}s", ""]
                for s in items:
                    first, *rest = s.text.split("\n")
                    md.append(f"- **{s.label}**" + (f" _({s.section})_" if s.section else "") + f": {first}")
                    md += ["  " + line for line in rest]
                md.append("")
    if skipped:
        md += ["## Not downloaded (no file on server yet)", ""]
        md += [f"- {t.number} ({t.source}) — status: {t.status}" for t in skipped]
    (out_dir / "observations_proposals.md").write_text("\n".join(md) + "\n", encoding="utf-8")
