"""Convert a docx/pptx Tdoc to Markdown (via markitdown)."""
from __future__ import annotations

import base64
import hashlib
import io
import re
import shutil
import struct
import subprocess
import tempfile
import warnings
from pathlib import Path

from PIL import Image, ImageChops

from .numbering import materialize_labels

CONVERTIBLE = {".docx", ".pptx"}   # plus legacy .doc via _legacy_to_docx
_DATA_IMAGE = re.compile(r"!\[([^\]]*)\]\(data:([^;,)]+);base64,([^)]*)\)")
_EXT = {"jpeg": "jpg", "x-emf": "emf", "emf": "emf", "x-wmf": "wmf", "wmf": "wmf", "svg+xml": "svg",
        "x-png": "png", "tiff": "tif", "x-tiff": "tif"}
# Browsers cannot show these; convert to PNG when LibreOffice/Inkscape is installed.
VECTOR_EXTS = {".emf", ".wmf"}


_MAC_SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
_PAGE_PX = (2400, 3394)   # LibreOffice Draw puts the picture on an A4 page; render big, then crop


def _soffice() -> str | None:
    """LibreOffice binary: on PATH, or the macOS app bundle (which does not put it on PATH)."""
    return shutil.which("soffice") or (_MAC_SOFFICE if Path(_MAC_SOFFICE).exists() else None)


def _autocrop(png: Path, margin: int = 12) -> bool:
    """Trim the white page around the figure in place. False if the image is blank."""
    with Image.open(png) as im:
        im = im.convert("RGBA")
        flat = Image.alpha_composite(Image.new("RGBA", im.size, "white"), im).convert("RGB")
    box = ImageChops.difference(flat, Image.new("RGB", flat.size, "white")).getbbox()
    if box is None:
        return False
    w, h = flat.size
    flat.crop((max(box[0] - margin, 0), max(box[1] - margin, 0),
               min(box[2] + margin, w), min(box[3] + margin, h))).save(png)
    return True


_EMFPLUS_PIXEL_MODES = {0x0026200A: "BGRA", 0x000E200B: "BGRa", 0x00022009: "BGRX", 0x00021808: "BGR"}


def _emfplus_bitmap(data: bytes) -> Image.Image | None:
    """Largest bitmap embedded in an EMF+ stream, as a PIL image (None if there is none).

    Some EMF+ files hold only a bitmap and no GDI fallback records, which LibreOffice draws blank.
    """
    best, objects, off = None, {}, 0       # objects: id -> [total size, bytes so far]
    while off + 8 <= len(data):
        rtype, rsize = struct.unpack_from("<II", data, off)
        if rsize < 8:
            break
        if rtype == 70 and data[off + 12:off + 16] == b"EMF+":     # EMR_COMMENT with EMF+ records
            pos, end = off + 16, off + 12 + struct.unpack_from("<I", data, off + 8)[0]
            while pos + 12 <= end:
                typ, flags, size, dsize = struct.unpack_from("<HHII", data, pos)
                if size < 12:
                    break
                body = data[pos + 12:pos + 12 + dsize]
                if typ == 0x4008 and (flags >> 8) & 0x7F == 5:     # Object record, ObjectType = Image
                    oid = flags & 0xFF
                    if flags & 0x8000:                             # continued: first chunk leads with the total size
                        if oid not in objects:
                            objects[oid] = [struct.unpack_from("<I", body)[0], b""]
                            body = body[4:]
                        objects[oid][1] += body
                        if len(objects[oid][1]) < objects[oid][0]:
                            pos += size
                            continue
                        body = objects.pop(oid)[1]
                    img = _emfplus_image(body)
                    if img is not None and (best is None or img.width * img.height > best.width * best.height):
                        best = img
                pos += size
        off += rsize
    return best


def _emfplus_image(body: bytes) -> Image.Image | None:
    if len(body) < 28 or struct.unpack_from("<I", body, 4)[0] != 1:        # 1 = bitmap (2 = nested metafile)
        return None
    width, height, stride, fmt, kind = struct.unpack_from("<iiiII", body, 8)
    pixels = body[28:]
    try:
        if kind == 1:                                                      # compressed (PNG/JPEG/...)
            return Image.open(io.BytesIO(pixels)).convert("RGBA")
        mode = _EMFPLUS_PIXEL_MODES.get(fmt)
        if mode is None:
            return None
        img = Image.frombuffer("RGBA" if mode != "BGR" else "RGB", (width, height), pixels, "raw", mode, stride, 1)
        return img.convert("RGBA")
    except (ValueError, OSError):
        return None


def _vector_to_png(path: Path) -> Path | None:
    """Render an EMF/WMF file to a cropped PNG; None if that is impossible (original is then kept).

    LibreOffice is used (Inkscape as a fallback). When LibreOffice draws nothing, the EMF+ bitmap is taken.
    """
    png = path.with_suffix(".png")
    soffice = _soffice()
    if soffice:
        with tempfile.TemporaryDirectory() as tmp:
            size = "".join(f'"{k}":{{"type":"long","value":"{v}"}},' for k, v in zip(("PixelWidth", "PixelHeight"), _PAGE_PX))
            cmd = [soffice, f"-env:UserInstallation={Path(tmp).as_uri()}/profile", "--headless", "--convert-to",
                   "png:draw_png_Export:{" + size.rstrip(",") + "}", "--outdir", tmp, str(path)]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=120)
                rendered = Path(tmp) / png.name
                if rendered.exists():
                    shutil.move(rendered, png)
            except (subprocess.SubprocessError, OSError):
                pass
    elif shutil.which("inkscape"):
        try:
            subprocess.run(["inkscape", str(path), "--export-type=png", f"--export-filename={png}"],
                           check=True, capture_output=True, timeout=120)
        except (subprocess.SubprocessError, OSError):
            pass
    else:
        return None
    if png.exists() and png.stat().st_size and (_autocrop(png) if soffice else True):
        return png
    bitmap = _emfplus_bitmap(path.read_bytes())
    if bitmap is not None:
        bitmap.save(png)
        return png
    png.unlink(missing_ok=True)
    return None


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
