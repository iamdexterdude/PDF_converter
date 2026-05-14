# PDF Toolkit Bot

A professional, all-in-one Telegram bot for working with PDFs and images.

## Features

| Tool | What it does |
|---|---|
| 🖼 **Images → PDF** | Multi-image, configurable page size / orientation / fit / quality / margins, grayscale toggle, page numbers, password, metadata |
| 🔗 **Merge** | Combine multiple PDFs in order |
| ✂️ **Split** | One PDF → one file per page |
| 📉 **Compress** | Three quality tiers (screen / ebook / printer) via Ghostscript when available |
| 🔄 **Rotate** | 90 / 180 / 270° for all pages |
| 🔒 **Protect / 🔓 Unlock** | AES-256 password encryption |
| 💧 **Watermark** | Diagonal text watermark on every page |
| 🔍 **OCR** | Make scanned PDFs searchable (uses `ocrmypdf` if installed) |
| 🖼 **PDF → Images** | Export each page as a JPEG |
| ℹ️ **Info** | Page count, metadata, encryption status |

## Senior-level touches

- **Async everywhere** — heavy CPU work runs in threads, never blocks the loop
- **Per-user sessions** with TTL auto-cleanup of temp files
- **Rate limiting middleware** — protection against button spam
- **FSM** (finite state machine) — clean multi-step flows
- **Inline keyboards** for UX instead of typing slash commands
- **EXIF auto-orient** — photos taken sideways come out right
- **Smart image preprocessing** — downsize to target DPI to keep PDFs small
- **Graceful shutdown** on SIGTERM/SIGINT
- **Rotating file logs** (10MB × 5)
- **Hard caps** on file size and image count
- **Cleanup guaranteed** via `try/finally` on every flow

## Setup

```bash
# Get a token from @BotFather
export BOT_TOKEN="123456:ABC-DEF..."

# Install
pip install -r requirements.txt

# (Optional, for best OCR / compression)
sudo apt install ghostscript poppler-utils tesseract-ocr
pip install ocrmypdf pdf2image pytesseract

# Run
python bot.py
```

## Configuration (env vars)

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | _(required)_ | Telegram bot token |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` |
| `LOG_FILE` | `bot.log` | Log file path |
| `WORK_DIR` | `./sessions` | Per-user temp directory |
| `MAX_IMAGES_PER_PDF` | `100` | Hard cap per session |
| `MAX_FILE_SIZE_MB` | `20` | Telegram's getFile limit |
| `SESSION_TTL_SECONDS` | `3600` | Idle session expiry |
| `RATE_LIMIT` | `0.5` | Min seconds between events per user |
| `OCR_LANGUAGES` | `eng` | Tesseract language codes (e.g. `eng+rus`) |

## Architecture

```
bot.py              Entry point — wiring, signal handling, lifecycle
config.py           Environment-driven settings (frozen dataclass)
handlers/
  common.py         /start, /help, /cancel
  images_to_pdf.py  The headline flow + options panel
  pdf_tools.py      Merge, split, compress, rotate, protect, watermark, OCR, info
  errors.py         Catch-all error handler + fallback
utils/
  session.py        Per-user state, TTL sweeper
  middleware.py     Rate limit + user-context injection
  keyboards.py      All inline / reply keyboards
  pdf_engine.py     Image → PDF (Pillow + reportlab)
  pdf_ops.py        PDF-on-PDF (pypdf, reportlab, optional ghostscript/ocrmypdf)
```

## Deployment

```bash
# systemd service
[Unit]
Description=PDF Toolkit Bot
After=network.target

[Service]
Type=simple
User=bot
WorkingDirectory=/opt/pdf-bot
Environment=BOT_TOKEN=...
ExecStart=/opt/pdf-bot/.venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Or via Docker — add a `Dockerfile` based on `python:3.12-slim`, install
`ghostscript poppler-utils tesseract-ocr`, copy the code, and `CMD ["python", "bot.py"]`.
