"""Read a saved 3GPP Tdoc list (xlsx) and select Tdocs by agenda item."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import openpyxl
import pandas as pd

SHEET = "TDoc_List"


@dataclass(frozen=True)
class Tdoc:
    number: str
    title: str
    source: str
    agenda_item: str
    status: str
    uploaded: bool
    url: str = ""            # hyperlink on the TDoc cell of the xlsx ("" if the cell has none)

    @property
    def downloadable(self) -> bool:
        return self.uploaded and self.status.lower() != "reserved"


def load_download_urls(xlsx_path: str | Path) -> dict[str, str]:
    """TDoc number -> URL of the hyperlink on its TDoc cell (column A).

    pandas drops hyperlinks, so read them with openpyxl (not read-only mode, which skips them).
    The sheet reports ~1M rows, so only walk down to the last row that has a value.
    """
    ws = openpyxl.load_workbook(xlsx_path)[SHEET]
    urls = {}
    for (cell,) in ws.iter_rows(min_row=2, max_col=1):
        if cell.value is None and cell.row > 5000:
            break
        if cell.value and cell.hyperlink and cell.hyperlink.target:
            urls[str(cell.value).strip()] = cell.hyperlink.target.strip()
    return urls


def load_tdoc_list(xlsx_path: str | Path) -> pd.DataFrame:
    """Load the TDoc_List sheet as strings (plus a 'Download URL' column), dropping blank rows."""
    df = pd.read_excel(xlsx_path, sheet_name=SHEET, dtype=str, keep_default_na=False)
    df = df[df["TDoc"].str.strip() != ""].reset_index(drop=True)
    urls = load_download_urls(xlsx_path)
    df["Download URL"] = df["TDoc"].str.strip().map(urls).fillna("")
    return df


def select_agenda_item(df: pd.DataFrame, agenda_item: str) -> list[Tdoc]:
    """Return Tdocs whose agenda item equals `agenda_item` exactly (10.5.2 != 10.5.2.2)."""
    rows = df[df["Agenda item"].str.strip() == agenda_item.strip()]
    return [
        Tdoc(
            number=r["TDoc"].strip(),
            title=r["Title"].strip(),
            source=r["Source"].strip(),
            agenda_item=r["Agenda item"].strip(),
            status=r["TDoc Status"].strip(),
            uploaded=bool(r["Uploaded"].strip()),
            url=r["Download URL"],
        )
        for _, r in rows.iterrows()
    ]


_SUFFIX = {"bis": "b", "ter": "c"}


def _meeting_key(text: str) -> tuple[str, str] | None:
    """(number, suffix) of a meeting spelled like '126bis', '126-bis', '126b', '#126' or 'RAN1#126-bis'."""
    m = re.search(r"(\d+)(?:[-_ ]?(bis|ter|b|c|e))?\s*$", Path(text).stem if text.endswith(".xlsx") else text, re.I)
    if not m:
        return None
    suffix = (m.group(2) or "").lower()
    return m.group(1), _SUFFIX.get(suffix, suffix)


def available_meetings(directory: str | Path) -> dict[tuple[str, str], Path]:
    """Meeting key -> xlsx for every 'TDoc_List_Meeting_RAN<wg>#<meeting>.xlsx' in `directory`."""
    found = {}
    for p in sorted(Path(directory).glob("*.xlsx")):
        key = _meeting_key(re.sub(r"^.*#", "", p.name)) if "#" in p.name else None
        if key:
            found[key] = p
    return found


def find_tdoc_list(directory: str | Path, meeting: str | None = None) -> Path:
    """The Tdoc list of `meeting` in `directory`; without `meeting`, the only list there."""
    found = available_meetings(directory)
    names = ", ".join(p.name for p in found.values()) or "none"
    if meeting is None:
        if len(found) != 1:
            raise ValueError(f"{len(found)} Tdoc lists in {directory} ({names}); choose one with --meeting")
        return next(iter(found.values()))
    key = _meeting_key(meeting)
    if key is None or key not in found:
        raise ValueError(f"no Tdoc list for meeting {meeting!r} in {directory} (available: {names})")
    return found[key]


def meeting_folder_candidates(xlsx_path: str | Path) -> list[str]:
    """Guess 3GPP FTP meeting folder names from a file name like 'TDoc_List_Meeting_RAN1#126-bis.xlsx'.

    RAN1 folders look like TSGR1_126 / TSGR1_126b, but older ones used 'bis'; try all spellings.
    """
    m = re.search(r"RAN(\d+)#(\d+)(?:[-_ ]?(bis|ter|b|c|e))?", Path(xlsx_path).stem, re.I)
    if not m:
        raise ValueError(f"cannot infer meeting from file name: {xlsx_path}")
    wg, num, suffix = m.group(1), m.group(2), (m.group(3) or "").lower()
    short = {"bis": "b", "ter": "c"}.get(suffix, suffix)
    names = [f"TSGR{wg}_{num}{short}"]
    if suffix in ("bis", "ter"):
        names += [f"TSGR{wg}_{num}{suffix}", f"TSGR{wg}_{num}-{suffix}"]
    return names
