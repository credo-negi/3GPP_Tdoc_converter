"""Write Word auto-numbered labels ('Proposal 3:') into the text of a docx.

Many Tdocs define "Observation %1:" / "Proposal %1:" as list-numbering formats, so the label is
not stored in the paragraph text and every docx->markdown converter drops it. We compute the
label from numbering.xml and insert it as a real text run before conversion.
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

_LABEL_FMT = re.compile(r"observation|proposal", re.I)


def _roman(n: int) -> str:
    out = ""
    for v, s in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"),
                 (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out, n = out + s, n - v
    return out


def _format(n: int, fmt: str) -> str:
    if fmt == "lowerLetter":
        return chr(ord("a") + (n - 1) % 26) * ((n - 1) // 26 + 1)
    if fmt == "upperLetter":
        return chr(ord("A") + (n - 1) % 26) * ((n - 1) // 26 + 1)
    if fmt == "lowerRoman":
        return _roman(n).lower()
    if fmt == "upperRoman":
        return _roman(n)
    if fmt == "decimalZero":
        return f"{n:02d}"
    return str(n)


def _val(el, tag: str):
    child = el.find(qn(tag)) if el is not None else None
    return child.get(qn("w:val")) if child is not None else None


class _Numbering:
    def __init__(self, numbering_el):
        self.abstract = {a.get(qn("w:abstractNumId")): a for a in numbering_el.findall(qn("w:abstractNum"))}
        self.num_to_abs: dict[str, str] = {}
        self.overrides: dict[tuple[str, int], int] = {}
        for n in numbering_el.findall(qn("w:num")):
            nid = n.get(qn("w:numId"))
            self.num_to_abs[nid] = _val(n, "w:abstractNumId")
            for ov in n.findall(qn("w:lvlOverride")):
                so = _val(ov, "w:startOverride")
                if so is not None:
                    self.overrides[(nid, int(ov.get(qn("w:ilvl"))))] = int(so)
        self.counters: dict[object, list] = {}

    def level(self, abs_id: str, ilvl: int):
        for lvl in self.abstract[abs_id].findall(qn("w:lvl")):
            if int(lvl.get(qn("w:ilvl"))) == ilvl:
                return lvl
        return None

    def label(self, num_id: str, ilvl: int) -> str | None:
        """Advance the counter for this list item and return its rendered label."""
        abs_id = self.num_to_abs.get(num_id)
        if abs_id is None or abs_id not in self.abstract:
            return None
        lvl = self.level(abs_id, ilvl)
        if lvl is None:
            return None
        key = ("num", num_id) if any(k[0] == num_id for k in self.overrides) else abs_id
        cnt = self.counters.setdefault(key, [None] * 9)
        if cnt[ilvl] is None:
            start = self.overrides.get((num_id, ilvl))
            cnt[ilvl] = start if start is not None else int(_val(lvl, "w:start") or 1)
        else:
            cnt[ilvl] += 1
        for d in range(ilvl + 1, 9):
            cnt[d] = None
        text = _val(lvl, "w:lvlText") or ""
        if not _LABEL_FMT.search(text):
            return None   # plain bullets / '1.' are already rendered by the markdown converter

        def sub(m):
            k = int(m.group(1)) - 1
            lv = self.level(abs_id, k)
            n = cnt[k] if cnt[k] is not None else int(_val(lv, "w:start") or 1)
            return _format(n, _val(lv, "w:numFmt") or "decimal")
        return re.sub(r"%(\d)", sub, text).strip()


def _num_pr(par):
    """(numId, ilvl) from the paragraph or its style chain; None if not numbered."""
    ppr = par._p.pPr
    num_pr = ppr.find(qn("w:numPr")) if ppr is not None else None
    style = par.style
    ilvl_default = None
    while num_pr is None and style is not None:
        sppr = style.element.pPr
        num_pr = sppr.find(qn("w:numPr")) if sppr is not None else None
        style = style.base_style
    if num_pr is None:
        return None
    num_id, ilvl = _val(num_pr, "w:numId"), _val(num_pr, "w:ilvl")
    if num_id in (None, "0"):
        return None
    return num_id, int(ilvl or ilvl_default or 0)


def materialize_labels(src: Path, dst: Path) -> int:
    """Copy src to dst with numbered 'Observation/Proposal' labels as literal text; return count."""
    doc = Document(str(src))
    try:
        numbering = _Numbering(doc.part.numbering_part.element)
    except (KeyError, NotImplementedError):
        doc.save(str(dst))
        return 0
    count = 0
    for par in doc.paragraphs:
        np_ = _num_pr(par)
        if np_ is None:
            continue
        lab = numbering.label(*np_)
        if not lab:
            continue
        text = par.text.lstrip()
        if not lab.endswith((":", ".")) and not text.startswith((":", "：")):
            lab += ":"
        run = OxmlElement("w:r")
        t = OxmlElement("w:t")
        t.set(qn("xml:space"), "preserve")
        t.text = lab + " "
        run.append(t)
        ppr = par._p.pPr
        if ppr is not None:
            ppr.addnext(run)
        else:
            par._p.insert(0, run)
        count += 1
    doc.save(str(dst))
    return count
