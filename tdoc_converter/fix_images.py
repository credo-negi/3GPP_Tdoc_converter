"""Convert the EMF/WMF files that earlier runs left next to the Markdown files, and fix the links.

    python3 -m tdoc_converter.fix_images output/TSGR1_126b/10.5.2.2/markdown
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from .convert import VECTOR_EXTS, _vector_to_png


def fix_markdown_dir(md_dir: Path) -> tuple[int, list[Path]]:
    """Return (number of converted images, images that could not be converted)."""
    converted, failed = 0, []
    for vec in sorted(p for p in md_dir.glob("images/*/*") if p.suffix.lower() in VECTOR_EXTS):
        png = _vector_to_png(vec)
        if png is None:
            failed.append(vec)
            continue
        converted += 1
        link = re.compile(re.escape(f"images/{vec.parent.name}/{vec.name}") + r"(?=\))")
        md = md_dir / f"{vec.parent.name}.md"
        if md.exists():
            md.write_text(link.sub(f"images/{vec.parent.name}/{png.name}", md.read_text(encoding="utf-8")),
                          encoding="utf-8")
        vec.unlink()
    return converted, failed


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m tdoc_converter.fix_images", description=__doc__)
    ap.add_argument("markdown_dir", type=Path, help="the `markdown/` folder of an agenda item")
    a = ap.parse_args()
    converted, failed = fix_markdown_dir(a.markdown_dir)
    print(f"{converted} converted to PNG, {len(failed)} left as EMF/WMF")
    for p in failed:
        print("  ", p)


if __name__ == "__main__":
    main()
