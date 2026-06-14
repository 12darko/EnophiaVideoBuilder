# ============================================================
# AI Agent — Dockerfile
# Python 3.11 + Playwright (Chromium) + Browser-Use
# ============================================================
# Otonom yapay zeka ajanı: video üretimi tetikler,
# sosyal medyaya paylaşır, hataları kendi kendine çözer.
# ============================================================

FROM python:3.11-slim-bookworm

# ── Meta ─────────────────────────────────────────────────────
LABEL maintainer="your-email@example.com"
LABEL description="Autonomous AI Agent for Video Factory"

# ── System deps ──────────────────────────────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        git \
        # Playwright/Chromium dependencies
        libnss3 \
        libnspr4 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libdbus-1-3 \
        libxkbcommon0 \
        libatspi2.0-0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libpango-1.0-0 \
        libcairo2 \
        libasound2 \
        libx11-xcb1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ───────────────────────────────────────
WORKDIR /agent

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ── Python deps ─────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Install Playwright browsers ─────────────────────────────
RUN playwright install chromium

# ── Application code ────────────────────────────────────────
COPY . .

# ── Create data directories ─────────────────────────────────
RUN mkdir -p /agent/data /agent/logs

# ── Healthcheck ──────────────────────────────────────────────
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os; exit(0 if os.path.exists('/agent/data/heartbeat') else 1)"

# ── Entrypoint ───────────────────────────────────────────────
CMD ["python", "-u", "main.py"]
