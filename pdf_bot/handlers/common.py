"""Welcome, help, cancel — common commands."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from utils.keyboards import main_menu
from utils.session import Session, session_manager

router = Router(name="common")
log = logging.getLogger(__name__)


WELCOME = (
    "👋 <b>Welcome to PDF Toolkit Bot</b>\n\n"
    "I'm your all-in-one PDF assistant. I can:\n\n"
    "🖼 <b>Images → PDF</b> — multi-image, high quality, configurable\n"
    "🔗 <b>Merge</b> PDFs into one\n"
    "✂️ <b>Split</b> PDF into per-page files\n"
    "📉 <b>Compress</b> to shrink file size\n"
    "🔄 <b>Rotate</b> all pages\n"
    "🔒 <b>Password protect</b> / 🔓 <b>unlock</b>\n"
    "💧 <b>Watermark</b> with custom text\n"
    "🔍 <b>OCR</b> — make scanned PDFs searchable\n"
    "🖼 <b>PDF → Images</b> — export each page\n"
    "ℹ️ <b>Info</b> — page count, metadata, encryption status\n\n"
    "Tap a tool below or send /help for more details."
)

HELP_TEXT = (
    "<b>📖 How to use me</b>\n\n"
    "<b>Images → PDF (most popular)</b>\n"
    "  1. Tap 🖼 <i>Images → PDF</i>\n"
    "  2. Send me photos — one by one or as an album\n"
    "  3. Tap ⚙️ <i>Options</i> to tune size / quality / margins\n"
    "  4. Tap ✅ <i>Convert</i> — I'll send back the PDF\n\n"
    "<b>Other tools</b>\n"
    "  • Tap the tool first, then upload the PDF.\n"
    "  • Merge: upload multiple PDFs in sequence, then /done.\n\n"
    "<b>Tips</b>\n"
    "  • Send images as <b>files</b> (not compressed photos) for best quality.\n"
    "  • Max <b>{max_imgs}</b> images per PDF, <b>{max_size}MB</b> per file.\n"
    "  • Your files are deleted after conversion — nothing is stored.\n\n"
    "<b>Commands</b>\n"
    "  /start — main menu\n"
    "  /cancel — abort current operation\n"
    "  /done — finish multi-file uploads\n"
    "  /help — this message"
)


@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext, session: Session) -> None:
    await state.clear()
    session.clear_images()
    await msg.answer(WELCOME, reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(msg: Message) -> None:
    from config import settings
    await msg.answer(
        HELP_TEXT.format(max_imgs=settings.MAX_IMAGES_PER_PDF, max_size=settings.MAX_FILE_SIZE_MB)
    )


@router.message(Command("cancel"))
async def cmd_cancel(msg: Message, state: FSMContext, session: Session) -> None:
    await state.clear()
    session.clear_images()
    await msg.answer("✖️ Cancelled. Back to the main menu.", reply_markup=main_menu())


@router.message(F.text == "❓ Help")
async def text_help(msg: Message) -> None:
    await cmd_help(msg)
