# ============================================================
# MoneyPrinterTurbo — Coolify-Optimized Dockerfile
# Python 3.11 + FFmpeg + ImageMagick + Supervisord
# ============================================================
# Hem Streamlit WebUI (8501) hem FastAPI backend (8080) çalıştırır.
# supervisord ile iki process paralel yönetilir.
# ============================================================

FROM python:3.11-slim-bookworm AS base

# ── Meta ─────────────────────────────────────────────────────
LABEL maintainer="your-email@example.com"
LABEL description="MoneyPrinterTurbo AI Video Generator"

# ── System deps ──────────────────────────────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        ffmpeg \
        imagemagick \
        fonts-liberation \
        fonts-dejavu-core \
        fonts-noto-core \
        fonts-freefont-ttf \
        fontconfig \
        curl \
        ca-certificates \
        supervisor \
    && fc-cache -fv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── ImageMagick policy: allow PDF/SVG read (moviepy needs it) ─
RUN if [ -f /etc/ImageMagick-6/policy.xml ]; then \
        sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/' /etc/ImageMagick-6/policy.xml; \
    fi

# ── MoneyPrinterTurbo kaynak kodu (build sırasında klonlanır) ─
# Repoya elle kopyalama gerekmez; Coolify doğrudan bu repoyu
# build edebilir. Belirli bir sürüme sabitlemek için MPT_REF
# build-arg'ını kullanın (ör. --build-arg MPT_REF=v1.2.6).
ARG MPT_REPO=https://github.com/harry0703/MoneyPrinterTurbo.git
ARG MPT_REF=main

# ── Working directory ───────────────────────────────────────
WORKDIR /MoneyPrinterTurbo

ENV PYTHONPATH="/MoneyPrinterTurbo"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUTF8=1
ENV LANG=C.UTF-8

# ── MoneyPrinterTurbo'yu klonla ─────────────────────────────
RUN git clone --depth 1 --branch "${MPT_REF}" "${MPT_REPO}" /tmp/mpt 2>/dev/null \
        || git clone "${MPT_REPO}" /tmp/mpt && \
    if [ "${MPT_REF}" != "main" ]; then git -C /tmp/mpt checkout "${MPT_REF}" || true; fi && \
    cp -a /tmp/mpt/. /MoneyPrinterTurbo/ && \
    rm -rf /tmp/mpt /MoneyPrinterTurbo/.git

# ── Python deps (MPT'nin kendi requirements'ı) ──────────────
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir toml   # env→config.toml enjeksiyonu için garanti

# ── Create directories for volumes ──────────────────────────
RUN mkdir -p /MoneyPrinterTurbo/storage \
             /MoneyPrinterTurbo/output \
             /MoneyPrinterTurbo/resource/songs \
             /MoneyPrinterTurbo/resource/videos

# ── Default config: copy example if config.toml is missing ──
RUN if [ ! -f config.toml ] && [ -f config.example.toml ]; then \
        cp config.example.toml config.toml; \
    fi

# ── Supervisord config ──────────────────────────────────────
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# ── Entrypoint + env→config enjeksiyon scripti ──────────────
COPY entrypoint.sh /entrypoint.sh
COPY inject_config.py /inject_config.py
RUN chmod +x /entrypoint.sh

# NOT: MPT Main.py'ye panel-link enjeksiyonu KALDIRILDI — 3. parti
# Streamlit UI'ını bozma riski vardı. Panele kendi URL'siyle erişilir.

# ── Expose ports ─────────────────────────────────────────────
# SADECE 8080 expose edilir (Streamlit UI) — Coolify tek port görsün,
# port belirsizliği/round-robin olmasın. FastAPI 8081'de çalışır ama
# expose EDİLMEZ; ai-agent yine iç ağdan (video-generator:8081) erişir
# (Docker'da aynı ağdaki servisler expose olmadan da birbirine ulaşır).
EXPOSE 8080

# ── Healthcheck ──────────────────────────────────────────────
# NOT: FastAPI'nin kök route'u (/) 404 döner; bu yüzden /docs kullanılır.
# Aksi halde healthcheck unhealthy olur ve ai-agent (depends_on:
# service_healthy) hiç başlamaz.
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8080/_stcore/health && \
        curl -f http://localhost:8081/docs || exit 1

# ── Entrypoint: config kalıcılığı → supervisord ─────────────
CMD ["/entrypoint.sh"]
