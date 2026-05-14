# Slim Python image with all system tools the bot uses
FROM python:3.12-slim

# System deps:
#   ghostscript   — best-quality PDF compression
#   poppler-utils — PDF→image rendering
#   tesseract-ocr — OCR engine (eng by default; add tesseract-ocr-LANG for more)
#   ocrmypdf      — best searchable-PDF pipeline (pulls in qpdf/unpaper)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ghostscript \
        poppler-utils \
        tesseract-ocr \
        qpdf \
        unpaper \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir ocrmypdf pdf2image pytesseract

# Copy the bot
COPY . .

# Render free tier provides ephemeral disk only — sessions live under /tmp
ENV WORK_DIR=/tmp/sessions \
    LOG_FILE=/tmp/bot.log \
    PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
