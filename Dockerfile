# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app
COPY pyproject.toml .
RUN pip install --upgrade pip && pip install --no-cache-dir setuptools wheel build && pip install --no-cache-dir .

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY agents/ agents/
COPY api/ api/
COPY conflict/ conflict/
COPY db/ db/
COPY summarizer/ summarizer/
COPY utils/ utils/
COPY data/ data/
COPY config.py .

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
