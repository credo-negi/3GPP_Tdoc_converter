import argparse
from pathlib import Path

from .pipeline import run


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m tdoc_converter", description=__doc__)
    ap.add_argument("agenda_item", help="agenda item, e.g. 10.5.2.2")
    ap.add_argument("--xlsx", type=Path, help="Tdoc list (default: the only xlsx in Tdoc_List/)")
    ap.add_argument("--out", type=Path, default=Path("output"))
    ap.add_argument("--folder", help="FTP meeting folder override, e.g. TSGR1_126b")
    ap.add_argument("--limit", type=int, help="process only the first N Tdocs (for testing)")
    ap.add_argument("--check-urls", action="store_true",
                    help="only HEAD-check the xlsx download links of the agenda item; download nothing")
    a = ap.parse_args()
    xlsx = a.xlsx
    if xlsx is None:
        found = sorted(Path("Tdoc_List").glob("*.xlsx"))
        if len(found) != 1:
            ap.error(f"pass --xlsx (found {len(found)} files in Tdoc_List/)")
        xlsx = found[0]
    run(xlsx, a.agenda_item, a.out, a.folder, a.limit, check_urls=a.check_urls)


main()
