"""Write the extracted statements per company (in order of appearance) as json, md and csv.

Companies are listed in the order they first appear in the Tdoc list; within a company the Tdocs
keep list order and each Tdoc keeps its Observations and Proposals interleaved as they appear.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .tdoc_list import Tdoc

CSV_COLUMNS = ["Tdoc", "Agenda item", "Company", "Type", "Theme", "Text"]


def group_by_company(results: list) -> dict[str, list]:
    """company (the Tdoc's Source field) -> its Results, in order of first appearance."""
    groups: dict[str, list] = {}
    for r in results:
        groups.setdefault(r.tdoc.source, []).append(r)
    return groups


def csv_rows(groups: dict[str, list]) -> list[list[str]]:
    return [[r.tdoc.number, r.tdoc.agenda_item, company, s.kind, s.section, s.text]
            for company, rs in groups.items() for r in rs for s in r.statements]


def write_reports(results: list, skipped: list[Tdoc], out_dir: Path, agenda_item: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    groups = group_by_company(results)

    data = [{"company": company,
             "tdocs": [{"tdoc": r.tdoc.number, "title": r.tdoc.title, "agenda_item": r.tdoc.agenda_item,
                        "error": r.error,
                        "statements": [{"kind": s.kind, "id": s.id, "theme": s.section, "text": s.text,
                                        "occurrences": s.occurrences} for s in r.statements]}
                       for r in rs]} for company, rs in groups.items()]
    (out_dir / "observations_proposals.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # utf-8-sig: Excel only recognises UTF-8 CSV when it starts with a BOM
    with (out_dir / "observations_proposals.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        w.writerows(csv_rows(groups))

    md = [f"# Agenda item {agenda_item}: observations and proposals", ""]
    for kind in ("Observation", "Proposal"):
        total = sum(s.kind == kind for r in results for s in r.statements)
        md.append(f"- {kind}s: {total}")
    md.append("")
    for company, rs in groups.items():
        md += [f"## {company}", ""]
        for r in rs:
            md += [f"### {r.tdoc.number}", f"*{r.tdoc.title}*", ""]
            if r.error:
                md += [f"> extraction failed: {r.error}", ""]
                continue
            if not r.statements:
                md += ["> no Observation/Proposal found", ""]
                continue
            for s in r.statements:
                first, *rest = s.text.split("\n")
                md.append(f"- **{s.label}**" + (f" _({s.section})_" if s.section else "") + f": {first}")
                md += ["  " + line for line in rest]
            md.append("")
    if skipped:
        md += ["## Not downloaded (no file on server yet)", ""]
        md += [f"- {t.number} ({t.source}) — status: {t.status}" for t in skipped]
    (out_dir / "observations_proposals.md").write_text("\n".join(md) + "\n", encoding="utf-8")
