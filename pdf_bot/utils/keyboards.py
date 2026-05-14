"""Inline keyboards — keep all UI markup in one place."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from utils.session import PdfOptions


def main_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(
        KeyboardButton(text="🖼 Images → PDF"),
        KeyboardButton(text="🔗 Merge PDFs"),
        KeyboardButton(text="✂️ Split PDF"),
        KeyboardButton(text="📉 Compress"),
        KeyboardButton(text="🔄 Rotate"),
        KeyboardButton(text="🔒 Protect"),
        KeyboardButton(text="🔓 Unlock"),
        KeyboardButton(text="💧 Watermark"),
        KeyboardButton(text="🔍 OCR"),
        KeyboardButton(text="🖼 PDF → Images"),
        KeyboardButton(text="ℹ️ Info"),
        KeyboardButton(text="❓ Help"),
    )
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True, input_field_placeholder="Pick a tool…")


def images_session_kb(count: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if count > 0:
        kb.button(text=f"✅ Convert ({count})", callback_data="img:convert")
        kb.button(text="⚙️ Options", callback_data="img:options")
        kb.button(text="📋 List images", callback_data="img:list")
        kb.button(text="🗑 Clear all", callback_data="img:clear")
    kb.button(text="🏁 Cancel", callback_data="img:cancel")
    kb.adjust(2, 2, 1) if count > 0 else kb.adjust(1)
    return kb.as_markup()


def options_kb(opts: PdfOptions) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=f"📄 Size: {opts.page_size}", callback_data="opt:page_size")
    kb.button(text=f"📐 Orient: {opts.orientation}", callback_data="opt:orientation")
    kb.button(text=f"🖼 Fit: {opts.fit_mode}", callback_data="opt:fit_mode")
    kb.button(text=f"💎 Quality: {opts.quality}", callback_data="opt:quality")
    kb.button(text=f"📏 Margin: {opts.margin_mm}mm", callback_data="opt:margin")
    kb.button(
        text=f"⚫ Grayscale: {'On' if opts.grayscale else 'Off'}",
        callback_data="opt:grayscale",
    )
    kb.button(
        text=f"🔢 Page #: {'On' if opts.add_page_numbers else 'Off'}",
        callback_data="opt:pagenums",
    )
    kb.button(
        text=f"🔒 Password: {'Set' if opts.password else 'None'}",
        callback_data="opt:password",
    )
    kb.button(text="🏷 Title/Author", callback_data="opt:metadata")
    kb.button(text="« Back", callback_data="opt:back")
    kb.adjust(2, 2, 2, 2, 1, 1)
    return kb.as_markup()


def choice_kb(prefix: str, choices: list[str], current: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for c in choices:
        label = f"✓ {c}" if c == current else c
        kb.button(text=label, callback_data=f"{prefix}:{c}")
    kb.button(text="« Back", callback_data=f"{prefix}:_back")
    kb.adjust(2)
    return kb.as_markup()


def rotate_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="↻ 90°", callback_data="rot:90")
    kb.button(text="↻ 180°", callback_data="rot:180")
    kb.button(text="↻ 270°", callback_data="rot:270")
    kb.button(text="✖ Cancel", callback_data="rot:cancel")
    kb.adjust(3, 1)
    return kb.as_markup()


def compress_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📱 Screen (smallest)", callback_data="cmp:screen")
    kb.button(text="📖 eBook (balanced)", callback_data="cmp:ebook")
    kb.button(text="🖨 Printer (high-Q)", callback_data="cmp:printer")
    kb.button(text="✖ Cancel", callback_data="cmp:cancel")
    kb.adjust(1)
    return kb.as_markup()


def confirm_kb(action: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Yes", callback_data=f"{action}:yes")
    kb.button(text="✖ No", callback_data=f"{action}:no")
    kb.adjust(2)
    return kb.as_markup()
