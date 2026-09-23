FROM python:3.12-slim

WORKDIR /app

# fonts-dejavu-core: pdf_report.py embeds DejaVu Sans into every PDF it
# builds instead of relying on reportlab's default (non-embedded)
# Helvetica — a bare-slim image with no fonts installed leaves PDF
# viewers to substitute their own metrics for Helvetica, which produces
# visibly broken letter-spacing in some renderers (see ADR-0015).
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
