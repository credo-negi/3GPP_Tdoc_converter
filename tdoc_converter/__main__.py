import argparse
from pathlib import Path

from .pipeline import run
from .tdoc_list import find_tdoc_list


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m tdoc_converter", description=__doc__)
    ap.add_argument("agenda_item", help="agenda item, e.g. 10.5.2.2")
    ap.add_argument("--meeting", help="meeting whose Tdoc list in Tdoc_List/ to use, e.g. 126bis or 126 "
                                      "(default: the only list there)")
    ap.add_argument("--xlsx", type=Path, help="path of a Tdoc list (overrides --meeting)")
    ap.add_argument("--out", type=Path, default=Path("output"))
    ap.add_argument("--folder", help="FTP meeting folder override, e.g. TSGR1_126b")
    ap.add_argument("--limit", type=int, help="process only the first N Tdocs (for testing)")
    ap.add_argument("--check-urls", action="store_true",
                    help="only HEAD-check the xlsx download links of the agenda item; download nothing")
    a = ap.parse_args()
    xlsx = a.xlsx
    if xlsx is None:
        try:
            xlsx = find_tdoc_list("Tdoc_List", a.meeting)
        except ValueError as e:
            ap.error(str(e))
    run(xlsx, a.agenda_item, a.out, a.folder, a.limit, check_urls=a.check_urls)


main()
