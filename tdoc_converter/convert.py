"""Convert a docx/pptx Tdoc to Markdown (via markitdown)."""
from __future__ import annotations

import base64
import hashlib
import re
import shutil
import subprocess
import tempfile
import warnings
from pathlib import Path

from .numbering import materialize_labels

CONVERTIBLE = {".docx", ".pptx"}   # plus legacy .doc via _legacy_to_docx
_DATA_IMAGE = re.compile(r"!\[([^\]]*)\]\(data:([^;,)]+);base64,([^)]*)\)")
_EXT = {"jpeg": "jpg", "x-emf": "emf", "emf": "emf", "x-wmf": "wmf", "wmf": "wmf", "svg+xml": "svg",
        "x-png": "png", "tiff": "tif", "x-tiff": "tif"}
# Browsers cannot show these; convert to PNG when LibreOffice/Inkscape is installed.
VECTOR_EXTS = {".emf", ".wmf"}


def _vector_to_png(path: Path) -> Path | None:
    """Render an EMF/WMF file to PNG with Inkscape or LibreOffice; None if neither is available."""
    png = path.with_suffix(".png")
    if shutil.which("inkscape"):
        cmd = ["inkscape", str(path), "--export-type=png", f"--export-filename={png}"]
    elif shutil.which("soffice"):
        cmd = ["soffice", "--headless", "--convert-to", "png", "--outdir", str(path.parent), str(path)]
    else:
        return None
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except (subprocess.SubprocessError, OSError):
        return None
    return png if png.exists() and png.stat().st_size else None


def externalize_images(text: str, image_dir: Path, link_prefix: str) -> str:
    """Save base64 images in `text` as files under image_dir and link them relatively.

    Identical images are stored once. EMF/WMF are linked as PNG if a converter exists,
    otherwise as the original file (kept so that nothing is lost).
    """
    saved: dict[str, str] = {}   # sha1 -> link target

    def repl(m: re.Match) -> str:
        alt, mime, b64 = m.group(1).strip(), m.group(2).lower(), m.group(3)
        try:
            data = base64.b64decode(b64, validate=False)
        except ValueError:
            return m.group(0)
        digest = hashlib.sha1(data).hexdigest()
        if digest not in saved:
            sub = mime.split("/", 1)[-1]
            name = f"img{len(saved) + 1:03d}.{_EXT.get(sub, sub)}"
            image_dir.mkdir(parents=True, exist_ok=True)
            path = image_dir / name
            path.write_bytes(data)
            if path.suffix in VECTOR_EXTS:
                path = _vector_to_png(path) or path
            saved[digest] = link_prefix + path.name
        return f"![{alt or 'image'}]({saved[digest]})"

    return _DATA_IMAGE.sub(repl, text)


def _legacy_to_docx(doc_path: Path, out_dir: Path) -> Path:
    """Convert .doc -> .docx with macOS textutil or LibreOffice, whichever is installed."""
    if shutil.which("textutil"):
        cmd = ["textutil", "-convert", "docx", "-output", str(out_dir / (doc_path.stem + ".docx")), str(doc_path)]
    elif shutil.which("soffice"):
        cmd = ["soffice", "--headless", "--convert-to", "docx", "--outdir", str(out_dir), str(doc_path)]
    else:
        raise ValueError(f"cannot convert legacy {doc_path.suffix} (install LibreOffice): {doc_path.name}")
    subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    return out_dir / (doc_path.stem + ".docx")


def to_markdown(doc_path: Path, image_dir: Path | None = None, link_prefix: str = "") -> str:
    """Convert docx/pptx/doc to Markdown. With image_dir, embedded images are saved there as files
    (linked as `link_prefix + file name`); without it they are dropped."""
    suffix = doc_path.suffix.lower()
    if suffix not in CONVERTIBLE | {".doc"}:
        raise ValueError(f"unsupported format {suffix}: {doc_path.name}")
    with tempfile.TemporaryDirectory() as tmp:
        src = doc_path
        if suffix == ".doc":
            src = _legacy_to_docx(doc_path, Path(tmp))
        if src.suffix.lower() == ".docx":
            labelled = Path(tmp) / "labelled.docx"
            materialize_labels(src, labelled)
            src = labelled
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # pydub's ffmpeg warning
            from markitdown import MarkItDown
            text = MarkItDown().convert(str(src), keep_data_uris=True).text_content
    if image_dir is None:
        return _DATA_IMAGE.sub("", text)
    return externalize_images(text, image_dir, link_prefix)


def convert_to_file(doc_path: Path, md_path: Path) -> Path:
    """Write `<name>.md`; its images go to `images/<name>/` next to it and are linked relatively."""
    md_path.parent.mkdir(parents=True, exist_ok=True)
    image_dir = md_path.parent / "images" / md_path.stem
    if image_dir.exists():
        shutil.rmtree(image_dir)       # drop images of an earlier conversion
    md_path.write_text(to_markdown(doc_path, image_dir, f"images/{md_path.stem}/"), encoding="utf-8")
    return md_path
