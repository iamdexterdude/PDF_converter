"""Handlers for PDF-on-PDF tools."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from config import settings
from utils import pdf_ops
from utils.keyboards import compress_kb, main_menu, rotate_kb
from utils.session import Session

router = Router(name="pdf_tools")
log = logging.getLogger(__name__)

MAX_BYTES = settings.MAX_FILE_SIZE_MB * 1024 * 1024


class Tool(StatesGroup):
    merge_wait = State()
    split_wait = State()
    compress_wait = State()
    compress_choose = State()
    rotate_wait = State()
    rotate_choose = State()
    protect_wait = State()
    protect_password = State()
    unlock_wait = State()
    unlock_password = State()
    watermark_wait = State()
    watermark_text = State()
    ocr_wait = State()
    pdf2img_wait = State()
    info_wait = State()


# ---------- helpers ----------
async def _download_pdf(bot: Bot, msg: Message, session: Session, idx: int = 0) -> Path | None:
    doc = msg.document
    if not doc:
        await msg.reply("Send a PDF file.")
        return None
    if (doc.mime_type or "").lower() not in {"application/pdf", "application/x-pdf"}:
        await msg.reply("That's not a PDF.")
        return None
    if doc.file_size and doc.file_size > MAX_BYTES:
        await msg.reply(f"⚠️ Too large (>{settings.MAX_FILE_SIZE_MB}MB).")
        return None
    dest = session.work_dir / f"in_{idx:02d}_{doc.file_unique_id}.pdf"
    try:
        await bot.download(doc, destination=dest)
    except Exception:  # noqa: BLE001
        log.exception("PDF download failed")
        await msg.reply("❌ Couldn't download that PDF.")
        return None
    return dest


async def _send_pdf(msg: Message, path: Path, caption: str = "✅ Done") -> None:
    await msg.answer_document(
        FSInputFile(path, filename=path.name), caption=caption, reply_markup=main_menu()
    )


# ====================================================================
# MERGE
# ====================================================================
@router.message(F.text == "🔗 Merge PDFs")
async def start_merge(msg: Message, state: FSMContext, session: Session) -> None:
    session.clear_images()  # reuse session.images for PDF paths
    await state.set_state(Tool.merge_wait)
    await msg.answer(
        "🔗 <b>Merge PDFs</b>\n\n"
        "Send PDFs one by one in the order you want them merged.\n"
        "Send /done when finished, /cancel to abort."
    )


@router.message(Tool.merge_wait, F.document)
async def merge_collect(msg: Message, bot: Bot, session: Session) -> None:
    path = await _download_pdf(bot, msg, session, idx=session.image_count)
    if path:
        session.add_image(path)
        await msg.reply(f"✅ Added (#{session.image_count}). Send more or /done.")


@router.message(Tool.merge_wait, Command("done"))
async def merge_finish(msg: Message, state: FSMContext, session: Session) -> None:
    if session.image_count < 2:
        await msg.reply("Need at least 2 PDFs. Send more or /cancel.")
        return
    out = session.work_dir / "merged.pdf"
    await msg.answer(f"⏳ Merging {session.image_count} PDFs…")
    try:
        await pdf_ops.merge_pdfs(session.images, out)
        await _send_pdf(msg, out, f"✅ Merged {session.image_count} PDFs")
    except Exception as e:  # noqa: BLE001
        log.exception("Merge failed")
        await msg.reply(f"❌ Merge failed: {e}")
    finally:
        session.clear_images()
        out.unlink(missing_ok=True)
        await state.clear()


# ====================================================================
# SPLIT
# ====================================================================
@router.message(F.text == "✂️ Split PDF")
async def start_split(msg: Message, state: FSMContext) -> None:
    await state.set_state(Tool.split_wait)
    await msg.answer("✂️ Send the PDF to split into per-page files.")


@router.message(Tool.split_wait, F.document)
async def split_do(msg: Message, bot: Bot, state: FSMContext, session: Session) -> None:
    pdf = await _download_pdf(bot, msg, session)
    if not pdf:
        return
    await msg.answer("⏳ Splitting…")
    try:
        pages = await pdf_ops.split_pdf(pdf, session.work_dir)
        await msg.answer(f"✅ Got {len(pages)} pages. Sending…")
        # Limit batch sending to avoid Telegram throttling
        for i, p in enumerate(pages, start=1):
            await msg.answer_document(FSInputFile(p, filename=p.name))
            if i % 10 == 0:
                await msg.answer(f"…{i}/{len(pages)} sent")
        await msg.answer("Done!", reply_markup=main_menu())
    except Exception as e:  # noqa: BLE001
        log.exception("Split failed")
        await msg.reply(f"❌ Split failed: {e}")
    finally:
        for p in session.work_dir.glob("*.pdf"):
            p.unlink(missing_ok=True)
        await state.clear()


# ====================================================================
# COMPRESS
# ====================================================================
@router.message(F.text == "📉 Compress")
async def start_compress(msg: Message, state: FSMContext) -> None:
    await state.set_state(Tool.compress_wait)
    await msg.answer("📉 Send the PDF to compress.")


@router.message(Tool.compress_wait, F.document)
async def compress_got(msg: Message, bot: Bot, state: FSMContext, session: Session) -> None:
    pdf = await _download_pdf(bot, msg, session)
    if not pdf:
        return
    await state.update_data(pdf=str(pdf))
    await state.set_state(Tool.compress_choose)
    await msg.answer("Pick a compression level:", reply_markup=compress_kb())


@router.callback_query(Tool.compress_choose, F.data.startswith("cmp:"))
async def compress_do(cb: CallbackQuery, state: FSMContext, session: Session) -> None:
    level = cb.data.split(":", 1)[1]
    if level == "cancel":
        await state.clear()
        await cb.message.edit_text("✖️ Cancelled")
        await cb.answer()
        return
    data = await state.get_data()
    pdf = Path(data["pdf"])
    out = session.work_dir / "compressed.pdf"
    await cb.message.edit_text(f"⏳ Compressing ({level})…")
    await cb.answer()
    try:
        before = pdf.stat().st_size
        await pdf_ops.compress_pdf(pdf, out, level)
        after = out.stat().st_size
        pct = (1 - after / before) * 100
        await _send_pdf(
            cb.message,
            out,
            f"✅ Compressed: {before/1024:.0f}KB → {after/1024:.0f}KB ({pct:+.1f}%)",
        )
    except Exception as e:  # noqa: BLE001
        log.exception("Compress failed")
        await cb.message.answer(f"❌ Compression failed: {e}")
    finally:
        pdf.unlink(missing_ok=True)
        out.unlink(missing_ok=True)
        await state.clear()


# ====================================================================
# ROTATE
# ====================================================================
@router.message(F.text == "🔄 Rotate")
async def start_rotate(msg: Message, state: FSMContext) -> None:
    await state.set_state(Tool.rotate_wait)
    await msg.answer("🔄 Send the PDF to rotate.")


@router.message(Tool.rotate_wait, F.document)
async def rotate_got(msg: Message, bot: Bot, state: FSMContext, session: Session) -> None:
    pdf = await _download_pdf(bot, msg, session)
    if not pdf:
        return
    await state.update_data(pdf=str(pdf))
    await state.set_state(Tool.rotate_choose)
    await msg.answer("How much?", reply_markup=rotate_kb())


@router.callback_query(Tool.rotate_choose, F.data.startswith("rot:"))
async def rotate_do(cb: CallbackQuery, state: FSMContext, session: Session) -> None:
    val = cb.data.split(":", 1)[1]
    if val == "cancel":
        await state.clear()
        await cb.message.edit_text("✖️ Cancelled")
        await cb.answer()
        return
    deg = int(val)
    data = await state.get_data()
    pdf = Path(data["pdf"])
    out = session.work_dir / "rotated.pdf"
    await cb.message.edit_text(f"⏳ Rotating {deg}°…")
    await cb.answer()
    try:
        await pdf_ops.rotate_pdf(pdf, out, deg)
        await _send_pdf(cb.message, out, f"✅ Rotated {deg}°")
    except Exception as e:  # noqa: BLE001
        log.exception("Rotate failed")
        await cb.message.answer(f"❌ Rotate failed: {e}")
    finally:
        pdf.unlink(missing_ok=True)
        out.unlink(missing_ok=True)
        await state.clear()


# ====================================================================
# PROTECT / UNLOCK
# ====================================================================
@router.message(F.text == "🔒 Protect")
async def start_protect(msg: Message, state: FSMContext) -> None:
    await state.set_state(Tool.protect_wait)
    await msg.answer("🔒 Send the PDF to password-protect.")


@router.message(Tool.protect_wait, F.document)
async def protect_got(msg: Message, bot: Bot, state: FSMContext, session: Session) -> None:
    pdf = await _download_pdf(bot, msg, session)
    if not pdf:
        return
    await state.update_data(pdf=str(pdf))
    await state.set_state(Tool.protect_password)
    await msg.answer("Send the password (I'll delete your message afterwards).")


@router.message(Tool.protect_password)
async def protect_do(msg: Message, state: FSMContext, session: Session) -> None:
    pwd = (msg.text or "").strip()
    if not pwd:
        await msg.reply("Empty password — try again or /cancel.")
        return
    try:
        await msg.delete()
    except Exception:  # noqa: BLE001
        pass
    data = await state.get_data()
    pdf = Path(data["pdf"])
    out = session.work_dir / "protected.pdf"
    notice = await msg.answer("⏳ Encrypting…")
    try:
        await pdf_ops.encrypt_pdf(pdf, out, pwd)
        await _send_pdf(msg, out, "✅ Encrypted")
    except Exception as e:  # noqa: BLE001
        log.exception("Encrypt failed")
        await notice.edit_text(f"❌ Encryption failed: {e}")
    finally:
        pdf.unlink(missing_ok=True)
        out.unlink(missing_ok=True)
        await state.clear()


@router.message(F.text == "🔓 Unlock")
async def start_unlock(msg: Message, state: FSMContext) -> None:
    await state.set_state(Tool.unlock_wait)
    await msg.answer("🔓 Send the encrypted PDF.")


@router.message(Tool.unlock_wait, F.document)
async def unlock_got(msg: Message, bot: Bot, state: FSMContext, session: Session) -> None:
    pdf = await _download_pdf(bot, msg, session)
    if not pdf:
        return
    await state.update_data(pdf=str(pdf))
    await state.set_state(Tool.unlock_password)
    await msg.answer("Send the password.")


@router.message(Tool.unlock_password)
async def unlock_do(msg: Message, state: FSMContext, session: Session) -> None:
    pwd = (msg.text or "").strip()
    try:
        await msg.delete()
    except Exception:  # noqa: BLE001
        pass
    data = await state.get_data()
    pdf = Path(data["pdf"])
    out = session.work_dir / "unlocked.pdf"
    notice = await msg.answer("⏳ Unlocking…")
    try:
        await pdf_ops.decrypt_pdf(pdf, out, pwd)
        await _send_pdf(msg, out, "✅ Unlocked")
    except ValueError:
        await notice.edit_text("❌ Wrong password.")
    except Exception as e:  # noqa: BLE001
        log.exception("Decrypt failed")
        await notice.edit_text(f"❌ Failed: {e}")
    finally:
        pdf.unlink(missing_ok=True)
        out.unlink(missing_ok=True)
        await state.clear()


# ====================================================================
# WATERMARK
# ====================================================================
@router.message(F.text == "💧 Watermark")
async def start_wm(msg: Message, state: FSMContext) -> None:
    await state.set_state(Tool.watermark_wait)
    await msg.answer("💧 Send the PDF you want watermarked.")


@router.message(Tool.watermark_wait, F.document)
async def wm_got(msg: Message, bot: Bot, state: FSMContext, session: Session) -> None:
    pdf = await _download_pdf(bot, msg, session)
    if not pdf:
        return
    await state.update_data(pdf=str(pdf))
    await state.set_state(Tool.watermark_text)
    await msg.answer("Send the watermark text (e.g. CONFIDENTIAL).")


@router.message(Tool.watermark_text)
async def wm_do(msg: Message, state: FSMContext, session: Session) -> None:
    text = (msg.text or "").strip()
    if not text:
        await msg.reply("Empty — try again or /cancel.")
        return
    data = await state.get_data()
    pdf = Path(data["pdf"])
    out = session.work_dir / "watermarked.pdf"
    await msg.answer("⏳ Applying watermark…")
    try:
        await pdf_ops.watermark_pdf(pdf, out, text)
        await _send_pdf(msg, out, f"✅ Watermarked: “{text}”")
    except Exception as e:  # noqa: BLE001
        log.exception("Watermark failed")
        await msg.reply(f"❌ Failed: {e}")
    finally:
        pdf.unlink(missing_ok=True)
        out.unlink(missing_ok=True)
        await state.clear()


# ====================================================================
# OCR
# ====================================================================
@router.message(F.text == "🔍 OCR")
async def start_ocr(msg: Message, state: FSMContext) -> None:
    await state.set_state(Tool.ocr_wait)
    await msg.answer(
        "🔍 Send a scanned PDF. I'll add a searchable text layer.\n"
        f"<i>Languages: {settings.OCR_LANGUAGES}</i>"
    )


@router.message(Tool.ocr_wait, F.document)
async def ocr_do(msg: Message, bot: Bot, state: FSMContext, session: Session) -> None:
    pdf = await _download_pdf(bot, msg, session)
    if not pdf:
        return
    notice = await msg.answer("⏳ Running OCR (this can take a while)…")
    out = session.work_dir / "ocr.pdf"
    try:
        await pdf_ops.ocr_pdf(pdf, out, settings.OCR_LANGUAGES)
        await _send_pdf(msg, out, "✅ Searchable PDF ready")
    except Exception as e:  # noqa: BLE001
        log.exception("OCR failed")
        await notice.edit_text(f"❌ OCR failed: {e}")
    finally:
        pdf.unlink(missing_ok=True)
        out.unlink(missing_ok=True)
        await state.clear()


# ====================================================================
# PDF → Images
# ====================================================================
@router.message(F.text == "🖼 PDF → Images")
async def start_p2i(msg: Message, state: FSMContext) -> None:
    await state.set_state(Tool.pdf2img_wait)
    await msg.answer("🖼 Send a PDF; I'll convert each page to a JPEG.")


@router.message(Tool.pdf2img_wait, F.document)
async def p2i_do(msg: Message, bot: Bot, state: FSMContext, session: Session) -> None:
    pdf = await _download_pdf(bot, msg, session)
    if not pdf:
        return
    out_dir = session.work_dir / "pages"
    out_dir.mkdir(exist_ok=True)
    await msg.answer("⏳ Rendering pages…")
    try:
        imgs = await pdf_ops.pdf_to_images(pdf, out_dir)
        for i, p in enumerate(imgs, start=1):
            await msg.answer_document(FSInputFile(p, filename=p.name))
            if i % 10 == 0:
                await msg.answer(f"…{i}/{len(imgs)} sent")
        await msg.answer(f"✅ {len(imgs)} pages exported", reply_markup=main_menu())
    except Exception as e:  # noqa: BLE001
        log.exception("PDF→IMG failed")
        await msg.reply(f"❌ Failed: {e}")
    finally:
        pdf.unlink(missing_ok=True)
        for p in out_dir.glob("*"):
            p.unlink(missing_ok=True)
        try:
            out_dir.rmdir()
        except OSError:
            pass
        await state.clear()


# ====================================================================
# INFO
# ====================================================================
@router.message(F.text == "ℹ️ Info")
async def start_info(msg: Message, state: FSMContext) -> None:
    await state.set_state(Tool.info_wait)
    await msg.answer("ℹ️ Send a PDF to inspect.")


@router.message(Tool.info_wait, F.document)
async def info_do(msg: Message, bot: Bot, state: FSMContext, session: Session) -> None:
    pdf = await _download_pdf(bot, msg, session)
    if not pdf:
        return
    try:
        pages, meta, enc = pdf_ops.get_pdf_info(pdf)
        size_kb = pdf.stat().st_size / 1024
        lines = [
            "<b>ℹ️ PDF info</b>",
            f"📄 Pages: <b>{pages}</b>",
            f"📦 Size: <b>{size_kb:.1f} KB</b>",
            f"🔒 Encrypted: <b>{'Yes' if enc else 'No'}</b>",
        ]
        if meta:
            lines.append("\n<b>Metadata</b>")
            for k, v in meta.items():
                lines.append(f"  • <code>{k}</code>: {v[:200]}")
        await msg.answer("\n".join(lines), reply_markup=main_menu())
    except Exception as e:  # noqa: BLE001
        log.exception("Info failed")
        await msg.reply(f"❌ Failed: {e}")
    finally:
        pdf.unlink(missing_ok=True)
        await state.clear()
