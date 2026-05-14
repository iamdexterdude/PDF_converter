"""PDF-on-PDF operations: merge, split, compress, rotate, watermark, OCR, metadata."""
from __future__ import annotations

import asyncio
import io
import logging
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas

log = logging.getLogger(__name__)


# ---------- Merge ----------
def _merge_sync(pdfs: List[Path], out_path: Path) -> Path:
    writer = PdfWriter()
    for pdf in pdfs:
        reader = PdfReader(str(pdf))
        for page in reader.pages:
            writer.add_page(page)
    with open(out_path, "wb") as f:
        writer.write(f)
    return out_path


async def merge_pdfs(pdfs: List[Path], out_path: Path) -> Path:
    return await asyncio.to_thread(_merge_sync, pdfs, out_path)


# ---------- Split ----------
def _split_sync(pdf: Path, out_dir: Path) -> List[Path]:
    reader = PdfReader(str(pdf))
    out: List[Path] = []
    for i, page in enumerate(reader.pages, start=1):
        writer = PdfWriter()
        writer.add_page(page)
        out_path = out_dir / f"page_{i:03d}.pdf"
        with open(out_path, "wb") as f:
            writer.write(f)
        out.append(out_path)
    return out


async def split_pdf(pdf: Path, out_dir: Path) -> List[Path]:
    return await asyncio.to_thread(_split_sync, pdf, out_dir)


# ---------- Rotate ----------
def _rotate_sync(pdf: Path, out_path: Path, degrees: int) -> Path:
    reader = PdfReader(str(pdf))
    writer = PdfWriter()
    for page in reader.pages:
        page.rotate(degrees)
        writer.add_page(page)
    with open(out_path, "wb") as f:
        writer.write(f)
    return out_path


async def rotate_pdf(pdf: Path, out_path: Path, degrees: int) -> Path:
    return await asyncio.to_thread(_rotate_sync, pdf, out_path, degrees)


# ---------- Encrypt ----------
def _encrypt_sync(pdf: Path, out_path: Path, password: str) -> Path:
    reader = PdfReader(str(pdf))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password=password, owner_password=password, algorithm="AES-256")
    with open(out_path, "wb") as f:
        writer.write(f)
    return out_path


async def encrypt_pdf(pdf: Path, out_path: Path, password: str) -> Path:
    return await asyncio.to_thread(_encrypt_sync, pdf, out_path, password)


# ---------- Decrypt ----------
def _decrypt_sync(pdf: Path, out_path: Path, password: str) -> Path:
    reader = PdfReader(str(pdf))
    if reader.is_encrypted:
        if not reader.decrypt(password):
            raise ValueError("Incorrect password")
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    with open(out_path, "wb") as f:
        writer.write(f)
    return out_path


async def decrypt_pdf(pdf: Path, out_path: Path, password: str) -> Path:
    return await asyncio.to_thread(_decrypt_sync, pdf, out_path, password)


# ---------- Watermark ----------
def _make_text_watermark(text: str, page_w: float, page_h: float) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))
    c.setFont("Helvetica-Bold", max(40, int(page_w / 15)))
    c.setFillColor(Color(0.6, 0.6, 0.6, alpha=0.3))
    c.saveState()
    c.translate(page_w / 2, page_h / 2)
    c.rotate(45)
    c.drawCentredString(0, 0, text)
    c.restoreState()
    c.save()
    return buf.getvalue()


def _watermark_sync(pdf: Path, out_path: Path, text: str) -> Path:
    reader = PdfReader(str(pdf))
    writer = PdfWriter()
    for page in reader.pages:
        page_w = float(page.mediabox.width)
        page_h = float(page.mediabox.height)
        wm_bytes = _make_text_watermark(text, page_w, page_h)
        wm_reader = PdfReader(io.BytesIO(wm_bytes))
        page.merge_page(wm_reader.pages[0])
        writer.add_page(page)
    with open(out_path, "wb") as f:
        writer.write(f)
    return out_path


async def watermark_pdf(pdf: Path, out_path: Path, text: str) -> Path:
    return await asyncio.to_thread(_watermark_sync, pdf, out_path, text)


# ---------- Metadata ----------
def _set_metadata_sync(
    pdf: Path,
    out_path: Path,
    title: Optional[str],
    author: Optional[str],
    subject: Optional[str],
) -> Path:
    reader = PdfReader(str(pdf))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    md: dict = {}
    if title:
        md[NameObject("/Title")] = TextStringObject(title)
    if author:
        md[NameObject("/Author")] = TextStringObject(author)
    if subject:
        md[NameObject("/Subject")] = TextStringObject(subject)
    md[NameObject("/Producer")] = TextStringObject("PDF Toolkit Bot")
    writer.add_metadata(md)
    with open(out_path, "wb") as f:
        writer.write(f)
    return out_path


async def set_metadata(
    pdf: Path,
    out_path: Path,
    title: Optional[str] = None,
    author: Optional[str] = None,
    subject: Optional[str] = None,
) -> Path:
    return await asyncio.to_thread(_set_metadata_sync, pdf, out_path, title, author, subject)


# ---------- Compress ----------
def _has_ghostscript() -> bool:
    return shutil.which("gs") is not None


def _compress_sync(pdf: Path, out_path: Path, level: str = "screen") -> Path:
    """
    Use Ghostscript when available (best quality/size ratio).
    Fallback: re-write with pypdf compression streams.

    Levels: screen (72dpi, smallest), ebook (150dpi), printer (300dpi), prepress.
    """
    if _has_ghostscript():
        cmd = [
            "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
            f"-dPDFSETTINGS=/{level}", "-dNOPAUSE", "-dQUIET", "-dBATCH",
            f"-sOutputFile={out_path}", str(pdf),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return out_path

    # Fallback — re-stream with pypdf
    reader = PdfReader(str(pdf))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    # compress_content_streams must be called after pages are part of a writer
    for page in writer.pages:
        try:
            page.compress_content_streams()
        except Exception:  # noqa: BLE001
            pass
    with open(out_path, "wb") as f:
        writer.write(f)
    return out_path


async def compress_pdf(pdf: Path, out_path: Path, level: str = "ebook") -> Path:
    return await asyncio.to_thread(_compress_sync, pdf, out_path, level)


# ---------- PDF → Images ----------
def _pdf_to_images_sync(pdf: Path, out_dir: Path, dpi: int = 200) -> List[Path]:
    """Use pdf2image if available, else pypdfium2."""
    try:
        from pdf2image import convert_from_path  # type: ignore
        images = convert_from_path(str(pdf), dpi=dpi)
        out: List[Path] = []
        for i, im in enumerate(images, start=1):
            p = out_dir / f"page_{i:03d}.jpg"
            im.save(p, "JPEG", quality=92)
            out.append(p)
        return out
    except ImportError:
        pass

    try:
        import pypdfium2 as pdfium  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "Need either pdf2image+poppler or pypdfium2 installed for PDF→image"
        ) from e

    out = []
    doc = pdfium.PdfDocument(str(pdf))
    scale = dpi / 72
    for i, page in enumerate(doc, start=1):
        pil = page.render(scale=scale).to_pil()
        p = out_dir / f"page_{i:03d}.jpg"
        pil.save(p, "JPEG", quality=92)
        out.append(p)
    return out


async def pdf_to_images(pdf: Path, out_dir: Path, dpi: int = 200) -> List[Path]:
    return await asyncio.to_thread(_pdf_to_images_sync, pdf, out_dir, dpi)


# ---------- OCR ----------
def _ocr_sync(pdf: Path, out_path: Path, languages: str = "eng") -> Path:
    """
    Make a searchable PDF using OCRmyPDF if installed (preferred — preserves layout
    and adds invisible text layer). Otherwise, fall back to per-page Tesseract OCR
    over rasterized images.
    """
    if shutil.which("ocrmypdf"):
        cmd = [
            "ocrmypdf", "--language", languages, "--skip-text",
            "--optimize", "1", str(pdf), str(out_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return out_path

    # Fallback path — Tesseract + reportlab
    try:
        import pytesseract  # type: ignore
        import pypdfium2 as pdfium  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "OCR requires either `ocrmypdf` (recommended) or "
            "`pytesseract` + `pypdfium2` installed."
        ) from e

    doc = pdfium.PdfDocument(str(pdf))
    pages_imgs: List[Image.Image] = [p.render(scale=200 / 72).to_pil() for p in doc]

    # Build a fresh PDF with image + invisible text layer per page
    from reportlab.pdfgen.canvas import Canvas
    c = Canvas(str(out_path))
    for img in pages_imgs:
        w, h = img.size
        c.setPageSize((w, h))
        img_buf = io.BytesIO()
        img.save(img_buf, "JPEG", quality=85)
        img_buf.seek(0)
        c.drawImage(io.BytesIO(img_buf.read()), 0, 0, width=w, height=h)  # type: ignore
        # Invisible text — render-mode 3
        data = pytesseract.image_to_data(img, lang=languages, output_type="dict")
        c.setFillAlpha(0)
        for i, txt in enumerate(data["text"]):
            if not txt.strip():
                continue
            x, y, tw, th = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            # Flip y — PDF origin is bottom-left
            c.setFont("Helvetica", max(th, 6))
            c.drawString(x, h - y - th, txt)
        c.setFillAlpha(1)
        c.showPage()
    c.save()
    return out_path


async def ocr_pdf(pdf: Path, out_path: Path, languages: str = "eng") -> Path:
    return await asyncio.to_thread(_ocr_sync, pdf, out_path, languages)


# ---------- Info ----------
def get_pdf_info(pdf: Path) -> Tuple[int, dict, bool]:
    """Return (page_count, metadata_dict, is_encrypted)."""
    reader = PdfReader(str(pdf))
    is_encrypted = reader.is_encrypted
    if is_encrypted:
        # Can't read metadata or pages without the password
        return 0, {}, True
    try:
        md = reader.metadata or {}
        meta = {str(k): str(v) for k, v in md.items()}
    except Exception:  # noqa: BLE001
        meta = {}
    return len(reader.pages), meta, is_encrypted
