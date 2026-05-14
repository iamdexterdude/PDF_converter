"""
Image → PDF engine.

Uses Pillow for image processing (auto-orient via EXIF, mode conversion,
optional grayscale) and reportlab for typeset PDF generation.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import List

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A3, A4, A5, LETTER, LEGAL, landscape, portrait
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from utils.session import PdfOptions

log = logging.getLogger(__name__)

PAGE_SIZES = {
    "A4": A4,
    "Letter": LETTER,
    "Legal": LEGAL,
    "A3": A3,
    "A5": A5,
}

QUALITY_DPI = {"High": 300, "Medium": 200, "Low": 100}
QUALITY_JPEG = {"High": 95, "Medium": 85, "Low": 70}


def _load_and_orient(path: Path) -> Image.Image:
    """Open image and auto-rotate per EXIF; convert to RGB."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, "white")
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    return img


def _prepare_image(path: Path, opts: PdfOptions, tmpdir: Path) -> Path:
    """
    Load, orient, optionally grayscale, downsize for chosen DPI/quality,
    and return a path to a JPEG ready to embed.
    """
    img = _load_and_orient(path)

    if opts.grayscale:
        img = img.convert("L").convert("RGB")

    # Cap dimensions roughly to the chosen DPI vs. page size to avoid huge PDFs
    target_dpi = QUALITY_DPI[opts.quality]
    # 8.27 x 11.69 inches for A4; use that as the worst-case page area
    max_dim = int(11.69 * target_dpi)
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    out_path = tmpdir / f"{path.stem}_prepped.jpg"
    img.save(out_path, "JPEG", quality=QUALITY_JPEG[opts.quality], optimize=True)
    return out_path


def _page_size_for(img_path: Path, opts: PdfOptions) -> tuple[float, float]:
    """Resolve the final page size given options + first image dimensions."""
    if opts.page_size == "Auto":
        # Use image's own aspect at 72 DPI
        with Image.open(img_path) as im:
            w, h = im.size
        return float(w), float(h)

    size = PAGE_SIZES[opts.page_size]

    if opts.orientation == "Landscape":
        return landscape(size)
    if opts.orientation == "Portrait":
        return portrait(size)
    # Auto orientation: match image's aspect
    with Image.open(img_path) as im:
        iw, ih = im.size
    if iw > ih:
        return landscape(size)
    return portrait(size)


def _draw_image_on_page(
    c: canvas.Canvas,
    img_path: Path,
    page_w: float,
    page_h: float,
    opts: PdfOptions,
) -> None:
    margin = opts.margin_mm * mm
    avail_w = page_w - 2 * margin
    avail_h = page_h - 2 * margin

    with Image.open(img_path) as im:
        iw, ih = im.size

    if opts.fit_mode == "Original":
        # 72 DPI assumption — place centered, no scaling
        draw_w, draw_h = iw, ih
    elif opts.fit_mode == "Stretch":
        draw_w, draw_h = avail_w, avail_h
    elif opts.fit_mode == "Fill":
        # Cover: fill the area, may crop excess (we just scale-up; reportlab clips
        # naturally by page edges if we draw beyond margins)
        scale = max(avail_w / iw, avail_h / ih)
        draw_w, draw_h = iw * scale, ih * scale
    else:  # Fit (default) — contain
        scale = min(avail_w / iw, avail_h / ih)
        draw_w, draw_h = iw * scale, ih * scale

    x = (page_w - draw_w) / 2
    y = (page_h - draw_h) / 2
    c.drawImage(
        str(img_path), x, y, width=draw_w, height=draw_h,
        preserveAspectRatio=False, mask="auto",
    )


def _set_metadata(c: canvas.Canvas, opts: PdfOptions) -> None:
    if opts.title:
        c.setTitle(opts.title)
    if opts.author:
        c.setAuthor(opts.author)
    c.setCreator("PDF Toolkit Bot")
    c.setProducer("PDF Toolkit Bot")


def _images_to_pdf_sync(
    images: List[Path], out_path: Path, opts: PdfOptions, tmpdir: Path
) -> Path:
    """Blocking conversion — run inside a thread."""
    if not images:
        raise ValueError("No images to convert")

    # Prep all images (orient, grayscale, downsize)
    prepped: List[Path] = [_prepare_image(p, opts, tmpdir) for p in images]

    page_w, page_h = _page_size_for(prepped[0], opts)
    c = canvas.Canvas(str(out_path), pagesize=(page_w, page_h))
    _set_metadata(c, opts)

    total = len(prepped)
    for idx, img_path in enumerate(prepped, start=1):
        if opts.page_size == "Auto":
            # Each page sized to its image
            page_w, page_h = _page_size_for(img_path, opts)
            c.setPageSize((page_w, page_h))
        else:
            page_w, page_h = _page_size_for(img_path, opts)
            c.setPageSize((page_w, page_h))

        _draw_image_on_page(c, img_path, page_w, page_h, opts)

        if opts.add_page_numbers:
            c.setFont("Helvetica", 9)
            c.setFillGray(0.4)
            c.drawCentredString(page_w / 2, 6 * mm, f"{idx} / {total}")

        c.showPage()

    c.save()

    if opts.password:
        _encrypt_pdf(out_path, opts.password)

    return out_path


def _encrypt_pdf(path: Path, password: str) -> None:
    """Encrypt in place using pypdf."""
    reader = PdfReader(str(path))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password=password, owner_password=password, algorithm="AES-256")
    tmp = path.with_suffix(".tmp.pdf")
    with open(tmp, "wb") as f:
        writer.write(f)
    tmp.replace(path)


async def convert_images_to_pdf(
    images: List[Path], out_path: Path, opts: PdfOptions, tmpdir: Path
) -> Path:
    """Async wrapper — runs CPU-bound work in a thread."""
    log.info("Converting %d images → %s (opts=%s)", len(images), out_path.name, opts)
    return await asyncio.to_thread(_images_to_pdf_sync, images, out_path, opts, tmpdir)
