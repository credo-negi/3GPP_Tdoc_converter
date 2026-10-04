"""Extract 'Observation' and 'Proposal' statements from a Tdoc converted to Markdown.

A statement starts at a line like `***Proposal 2-1-1:*** text` (bold/italic/bullet markers are
ignored) and runs over the lines that belong to it (continuation lines and the bullet list that
follows). Table rows are skipped: companies quote earlier agreements there, which are not
their own observations/proposals. A statement repeated in the Conclusion is merged with the
first one (the longest wording is kept).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

LABEL = re.compile(
    r"^(?P<kind>Observation|Proposal)s?\s*#?\s*(?P<id>[0-9A-Za-z][\w.\-–]*)?\s*(?:\([^)]*\))?\s*(?:[:：]|(?<=\d)\.(?=\s))\s*(?P<rest>.*)$",
    re.I,
)
# A line holding only the label ('**Proposal 3**'); the statement is the text that follows.
LABEL_ONLY = re.compile(r"^(?P<kind>Observation|Proposal)\s*#?\s*(?P<id>\d[\w.\-–]*)\s*(?:\([^)]*\))?\s*(?P<rest>)$", re.I)
_LEAD = re.compile(r"^(?:\s*>\s*)*\s*(?:[*+\-•]\s+|\d+[.)]\s+)?")
_BULLET = re.compile(r"^\s*(?:[*+\-•]|\d+[.)])\s+")
_HEADING = re.compile(r"^\s*#{1,6}\s+(.*)$")
_NUM_HEADING = re.compile(r"^\s*\d+\.\s+\*\*(.+?)\*\*\s*$")   # '1. **DMRS design**' (list-styled heading)
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_CAPTION = re.compile(r"^\W*(?:Figure|Table)\s+[\d.\-–]+", re.I)
_EMPH = re.compile(r"\*{2,3}|(?<!\w)_{1,2}(?=\S)|(?<=\S)_{1,2}(?!\w)")


@dataclass
class Statement:
    kind: str                # "Observation" | "Proposal"
    id: str                  # e.g. "2-1-1" ("" if unnumbered)
    text: str
    section: str = ""
    occurrences: int = 1

    @property
    def label(self) -> str:
        return f"{self.kind} {self.id}".strip()


def _clean(line: str) -> str:
    line = re.sub(r"^(\s*)\*(\s)", r"\1-\2", line)       # '*' bullet -> '-'
    line = _EMPH.sub("", line).replace("*", "")
    return line.rstrip()


def _match_label(line: str):
    plain = _EMPH.sub("", _LEAD.sub("", line)).replace("*", "").strip()
    m = LABEL.match(plain)
    if m:
        return m
    return LABEL_ONLY.match(plain)


def _is_bullet(line: str) -> bool:
    return bool(_BULLET.match(line))


def extract_statements(markdown: str) -> list[Statement]:
    lines = _IMAGE.sub("", markdown).splitlines()   # figures are not part of the statement text
    found: list[Statement] = []
    section = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        h = _HEADING.match(line) or _NUM_HEADING.match(line)
        if h:
            section = _clean(h.group(1)).strip()
            i += 1
            continue
        m = None if line.lstrip().startswith("|") else _match_label(line)
        if not m:
            i += 1
            continue

        body = [m.group("rest").strip()]
        last = line          # last non-blank line included
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            if not nxt.strip():
                k = j + 1
                while k < len(lines) and not lines[k].strip():
                    k += 1
                if k >= len(lines):
                    break
                cand = lines[k]
                # a blank line only continues a bullet list that belongs to the statement: the
                # statement is unfinished (no closing '.', '!' or '?') or already inside a list
                stem = _clean(last).rstrip()
                if len(body) == 1 and not body[0] and not _match_label(cand) \
                        and not (cand.lstrip().startswith("|") or _HEADING.match(cand)):
                    j = k          # label-only line: the statement is the block that follows
                    continue
                if _is_bullet(cand) and (not stem.endswith((".", "!", "?")) or _is_bullet(last)) \
                        and not _match_label(cand):
                    j = k
                    continue
                break
            if (nxt.lstrip().startswith("|") or _HEADING.match(nxt) or _NUM_HEADING.match(nxt) or _CAPTION.match(_clean(nxt).strip())
                    or _match_label(nxt)):
                break
            body.append(_clean(nxt))
            last = nxt
            j += 1

        if len(body) > 1 and not body[0] and body[1].startswith("- "):
            body = body[1:]
            body[0] = body[0][2:]          # label-only line followed by a one-item bullet
        text = "\n".join(body).strip()
        text = re.sub(rf"^{m.group('kind')}\s*{re.escape(m.group('id') or '')}\s*[:：]\s*", "", text, flags=re.I)
        found.append(Statement(m.group("kind").capitalize(), (m.group("id") or "").strip(" .:"),
                               text, section))
        i = max(j, i + 1)
    return _merge_duplicates(found)


def _merge_duplicates(items: list[Statement]) -> list[Statement]:
    merged: dict[tuple, Statement] = {}
    for s in items:
        key = (s.kind, s.id) if s.id else (s.kind, re.sub(r"\s+", " ", s.text.lower()))
        if key not in merged:
            merged[key] = s
            continue
        keep = merged[key]
        keep.occurrences += 1
        if len(s.text) > len(keep.text):   # keep the fullest wording, but the first section
            keep.text = s.text
    return list(merged.values())
