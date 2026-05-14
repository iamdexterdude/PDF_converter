"""Images → PDF flow."""
from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    Message,
)

from config import settings
from utils.keyboards import choice_kb, images_session_kb, main_menu, options_kb
from utils.pdf_engine import convert_images_to_pdf
from utils.session import Session

router = Router(name="images_to_pdf")
log = logging.getLogger(__name__)


class ImgFlow(StatesGroup):
    collecting = State()
    awaiting_password = State()
    awaiting_metadata = State()
    awaiting_margin = State()


# ---------- Entry ----------
@router.message(F.text == "🖼 Images → PDF")
async def start_images(msg: Message, state: FSMContext, session: Session) -> None:
    session.clear_images()
    await state.set_state(ImgFlow.collecting)
    await msg.answer(
        "📤 <b>Send me your images</b>\n\n"
        "• One by one, or in an album\n"
        "• As <i>photos</i> or as <i>files</i> (files = better quality)\n"
        f"• Up to {settings.MAX_IMAGES_PER_PDF} images per PDF\n\n"
        "I'll show you a count after each one.",
        reply_markup=images_session_kb(0),
    )


# ---------- Receive a photo ----------
@router.message(ImgFlow.collecting, F.photo)
async def on_photo(msg: Message, bot: Bot, session: Session, state: FSMContext) -> None:
    if session.image_count >= settings.MAX_IMAGES_PER_PDF:
        await msg.reply(f"⚠️ Limit reached ({settings.MAX_IMAGES_PER_PDF}). Tap Convert.")
        return

    photo = msg.photo[-1]  # highest resolution
    if photo.file_size and photo.file_size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        await msg.reply("⚠️ That photo is too large.")
        return

    dest = session.work_dir / f"img_{session.image_count:03d}_{photo.file_unique_id}.jpg"
    try:
        await bot.download(photo, destination=dest)
    except Exception as e:  # noqa: BLE001
        log.exception("Photo download failed")
        await msg.reply("❌ Couldn't download that photo. Try again?")
        return

    session.add_image(dest)
    await _ack_image(msg, session)


# ---------- Receive a document (image file) ----------
@router.message(ImgFlow.collecting, F.document)
async def on_doc(msg: Message, bot: Bot, session: Session, state: FSMContext) -> None:
    doc = msg.document
    if not doc:
        return
    mime = (doc.mime_type or "").lower()
    if not mime.startswith("image/"):
        await msg.reply("That doesn't look like an image. Send an image file or photo.")
        return

    if doc.file_size and doc.file_size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        await msg.reply(f"⚠️ File too large (>{settings.MAX_FILE_SIZE_MB}MB).")
        return

    if session.image_count >= settings.MAX_IMAGES_PER_PDF:
        await msg.reply(f"⚠️ Limit reached ({settings.MAX_IMAGES_PER_PDF}). Tap Convert.")
        return

    suffix = Path(doc.file_name or "img").suffix or ".jpg"
    dest = session.work_dir / f"img_{session.image_count:03d}_{doc.file_unique_id}{suffix}"
    try:
        await bot.download(doc, destination=dest)
    except Exception:  # noqa: BLE001
        log.exception("Doc download failed")
        await msg.reply("❌ Couldn't download that file. Try again?")
        return

    session.add_image(dest)
    await _ack_image(msg, session)


async def _ack_image(msg: Message, session: Session) -> None:
    await msg.reply(
        f"✅ Added (<b>{session.image_count}</b> total)",
        reply_markup=images_session_kb(session.image_count),
    )


# ---------- Inline session controls ----------
@router.callback_query(F.data == "img:cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext, session: Session) -> None:
    session.clear_images()
    await state.clear()
    await cb.message.edit_text("✖️ Cancelled.")
    await cb.message.answer("Back to the main menu.", reply_markup=main_menu())
    await cb.answer()


@router.callback_query(F.data == "img:clear")
async def cb_clear(cb: CallbackQuery, session: Session) -> None:
    session.clear_images()
    await cb.message.edit_text(
        "🗑 All images cleared. Send new ones, or cancel.",
        reply_markup=images_session_kb(0),
    )
    await cb.answer("Cleared")


@router.callback_query(F.data == "img:list")
async def cb_list(cb: CallbackQuery, session: Session) -> None:
    if not session.images:
        await cb.answer("No images yet", show_alert=True)
        return
    lines = [f"{i+1}. {p.name}" for i, p in enumerate(session.images)]
    text = "📋 <b>Image queue</b>\n\n" + "\n".join(lines[:50])
    if len(lines) > 50:
        text += f"\n…and {len(lines) - 50} more"
    await cb.message.answer(text)
    await cb.answer()


# ---------- Options panel ----------
@router.callback_query(F.data == "img:options")
async def cb_options(cb: CallbackQuery, session: Session) -> None:
    await cb.message.edit_text(
        "⚙️ <b>PDF options</b>\nTap any setting to change it.",
        reply_markup=options_kb(session.options),
    )
    await cb.answer()


@router.callback_query(F.data == "opt:back")
async def cb_opt_back(cb: CallbackQuery, session: Session) -> None:
    await cb.message.edit_text(
        f"📥 Images queued: <b>{session.image_count}</b>",
        reply_markup=images_session_kb(session.image_count),
    )
    await cb.answer()


@router.callback_query(F.data == "opt:page_size")
async def cb_opt_size(cb: CallbackQuery, session: Session) -> None:
    await cb.message.edit_reply_markup(
        reply_markup=choice_kb(
            "size", ["A4", "Letter", "Legal", "A3", "A5", "Auto"], session.options.page_size
        )
    )
    await cb.answer()


@router.callback_query(F.data.startswith("size:"))
async def cb_size_set(cb: CallbackQuery, session: Session) -> None:
    val = cb.data.split(":", 1)[1]
    if val != "_back":
        session.options.page_size = val  # type: ignore[assignment]
    await cb.message.edit_text(
        "⚙️ <b>PDF options</b>", reply_markup=options_kb(session.options)
    )
    await cb.answer(f"Size: {session.options.page_size}")


@router.callback_query(F.data == "opt:orientation")
async def cb_opt_orient(cb: CallbackQuery, session: Session) -> None:
    await cb.message.edit_reply_markup(
        reply_markup=choice_kb(
            "orient", ["Portrait", "Landscape", "Auto"], session.options.orientation
        )
    )
    await cb.answer()


@router.callback_query(F.data.startswith("orient:"))
async def cb_orient_set(cb: CallbackQuery, session: Session) -> None:
    val = cb.data.split(":", 1)[1]
    if val != "_back":
        session.options.orientation = val  # type: ignore[assignment]
    await cb.message.edit_text("⚙️ <b>PDF options</b>", reply_markup=options_kb(session.options))
    await cb.answer()


@router.callback_query(F.data == "opt:fit_mode")
async def cb_opt_fit(cb: CallbackQuery, session: Session) -> None:
    await cb.message.edit_reply_markup(
        reply_markup=choice_kb(
            "fit", ["Fit", "Fill", "Stretch", "Original"], session.options.fit_mode
        )
    )
    await cb.answer()


@router.callback_query(F.data.startswith("fit:"))
async def cb_fit_set(cb: CallbackQuery, session: Session) -> None:
    val = cb.data.split(":", 1)[1]
    if val != "_back":
        session.options.fit_mode = val  # type: ignore[assignment]
    await cb.message.edit_text("⚙️ <b>PDF options</b>", reply_markup=options_kb(session.options))
    await cb.answer()


@router.callback_query(F.data == "opt:quality")
async def cb_opt_q(cb: CallbackQuery, session: Session) -> None:
    await cb.message.edit_reply_markup(
        reply_markup=choice_kb("q", ["High", "Medium", "Low"], session.options.quality)
    )
    await cb.answer()


@router.callback_query(F.data.startswith("q:"))
async def cb_q_set(cb: CallbackQuery, session: Session) -> None:
    val = cb.data.split(":", 1)[1]
    if val != "_back":
        session.options.quality = val  # type: ignore[assignment]
    await cb.message.edit_text("⚙️ <b>PDF options</b>", reply_markup=options_kb(session.options))
    await cb.answer()


@router.callback_query(F.data == "opt:grayscale")
async def cb_opt_gray(cb: CallbackQuery, session: Session) -> None:
    session.options.grayscale = not session.options.grayscale
    await cb.message.edit_reply_markup(reply_markup=options_kb(session.options))
    await cb.answer(f"Grayscale: {'On' if session.options.grayscale else 'Off'}")


@router.callback_query(F.data == "opt:pagenums")
async def cb_opt_pn(cb: CallbackQuery, session: Session) -> None:
    session.options.add_page_numbers = not session.options.add_page_numbers
    await cb.message.edit_reply_markup(reply_markup=options_kb(session.options))
    await cb.answer(f"Page numbers: {'On' if session.options.add_page_numbers else 'Off'}")


@router.callback_query(F.data == "opt:margin")
async def cb_opt_margin(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ImgFlow.awaiting_margin)
    await cb.message.answer(
        "📏 Send a margin value in <b>mm</b> (0–50). Or /cancel to go back."
    )
    await cb.answer()


@router.message(ImgFlow.awaiting_margin)
async def on_margin(msg: Message, state: FSMContext, session: Session) -> None:
    try:
        v = int((msg.text or "").strip())
    except ValueError:
        await msg.reply("Please send a whole number, e.g. 10")
        return
    if not 0 <= v <= 50:
        await msg.reply("Margin must be 0–50 mm.")
        return
    session.options.margin_mm = v
    await state.set_state(ImgFlow.collecting)
    await msg.answer(
        f"✅ Margin set to {v}mm",
        reply_markup=options_kb(session.options),
    )


@router.callback_query(F.data == "opt:password")
async def cb_opt_pwd(cb: CallbackQuery, state: FSMContext, session: Session) -> None:
    if session.options.password:
        session.options.password = None
        await cb.message.edit_reply_markup(reply_markup=options_kb(session.options))
        await cb.answer("Password removed")
        return
    await state.set_state(ImgFlow.awaiting_password)
    await cb.message.answer(
        "🔒 Send the password for the PDF (or /cancel).\n"
        "<i>I'll delete your message right after.</i>"
    )
    await cb.answer()


@router.message(ImgFlow.awaiting_password)
async def on_password(msg: Message, state: FSMContext, session: Session) -> None:
    pwd = (msg.text or "").strip()
    if not pwd:
        await msg.reply("Empty — try again or /cancel.")
        return
    session.options.password = pwd
    try:
        await msg.delete()
    except Exception:  # noqa: BLE001
        pass
    await state.set_state(ImgFlow.collecting)
    await msg.answer("✅ Password set.", reply_markup=options_kb(session.options))


@router.callback_query(F.data == "opt:metadata")
async def cb_opt_meta(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ImgFlow.awaiting_metadata)
    await cb.message.answer(
        "🏷 Send title and author separated by a <code>|</code>:\n\n"
        "<i>e.g.</i> <code>Q4 Report | Alice Doe</code>\n\n"
        "Or just a title. /cancel to skip."
    )
    await cb.answer()


@router.message(ImgFlow.awaiting_metadata)
async def on_metadata(msg: Message, state: FSMContext, session: Session) -> None:
    text = (msg.text or "").strip()
    if "|" in text:
        t, a = (s.strip() for s in text.split("|", 1))
        session.options.title = t or None
        session.options.author = a or None
    else:
        session.options.title = text or None
    await state.set_state(ImgFlow.collecting)
    await msg.answer("✅ Metadata set.", reply_markup=options_kb(session.options))


# ---------- Convert ----------
@router.callback_query(F.data == "img:convert")
async def cb_convert(cb: CallbackQuery, state: FSMContext, session: Session) -> None:
    if session.image_count == 0:
        await cb.answer("No images yet!", show_alert=True)
        return

    await cb.message.edit_text(
        f"⏳ Building PDF from <b>{session.image_count}</b> image(s)…"
    )
    await cb.answer()

    out_path = session.work_dir / "output.pdf"
    try:
        await convert_images_to_pdf(
            session.images, out_path, session.options, session.work_dir
        )
    except Exception as e:  # noqa: BLE001
        log.exception("Conversion failed")
        await cb.message.answer(f"❌ Conversion failed: {e}")
        return

    size_kb = out_path.stat().st_size / 1024
    caption = (
        f"✅ <b>Done!</b>\n"
        f"📄 {session.image_count} page(s) • {size_kb:.1f} KB\n"
        f"📐 {session.options.page_size} • {session.options.fit_mode} • "
        f"{session.options.quality} quality"
    )
    try:
        await cb.message.answer_document(
            FSInputFile(out_path, filename=_filename(session)),
            caption=caption,
            reply_markup=main_menu(),
        )
    finally:
        # Cleanup
        session.clear_images()
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        await state.clear()


def _filename(session: Session) -> str:
    base = session.options.title or "document"
    safe = "".join(c if c.isalnum() or c in " -_." else "_" for c in base).strip()
    return f"{safe or 'document'}.pdf"
