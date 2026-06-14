"""
AI Agent — Main Entrypoint
=============================
Otonom video fabrikası ajanının ana giriş noktası.
Tüm modülleri başlatır, scheduler'ı kurar ve
7/24 çalışmaya başlar.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from datetime import datetime

from loguru import logger

# ── Logging yapılandırması ───────────────────────────────────
LOG_DIR = os.environ.get("AGENT_LOG_DIR", "/agent/logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Konsol ve dosya logları
logger.remove()  # Varsayılan handler'ı kaldır
logger.add(
    sys.stdout,
    level="INFO",
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    ),
    colorize=True,
)
logger.add(
    os.path.join(LOG_DIR, "agent_{time:YYYY-MM-DD}.log"),
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
    compression="gz",
    format=(
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        "{name}:{function}:{line} — {message}"
    ),
)


def _write_heartbeat(config: object) -> None:
    """Anında bir heartbeat yaz — healthcheck baştan geçsin (restart loop önle)."""
    try:
        hb = os.path.join(config.data_dir, "heartbeat")  # type: ignore[attr-defined]
        os.makedirs(os.path.dirname(hb), exist_ok=True)
        with open(hb, "w") as f:
            f.write(datetime.now().isoformat())
        logger.info(f"💓 İlk heartbeat yazıldı: {hb}")
    except Exception as e:
        logger.warning(f"⚠️ İlk heartbeat yazılamadı: {e}")


def _panel_done(task: "asyncio.Task[None]") -> None:
    """Panel task'ı beklenmedik durursa hatayı görünür şekilde logla."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(f"❌ Kontrol paneli beklenmedik şekilde durdu: {exc!r}")


async def main() -> None:
    """Ana async giriş noktası."""

    logger.info("=" * 60)
    logger.info("🤖 Otonom Video Fabrikası Ajanı Başlatılıyor...")
    logger.info(f"⏰ Başlangıç zamanı: {datetime.now().isoformat()}")
    logger.info("=" * 60)

    # ── Konfigürasyon yükle ──────────────────────────────────
    from config import config

    logger.info(f"📋 LLM Provider: {config.llm.provider}")
    logger.info(f"📋 İçerik Niche: {config.content.niche}")
    logger.info(f"📋 İçerik Dili: {config.content.language}")
    logger.info(
        f"📋 Üretim Saatleri: {config.scheduler.production_hours}"
    )
    logger.info(
        f"📋 Aktif Platformlar: {config.social_media.enabled_platforms}"
    )
    logger.info(
        f"📋 Video Generator URL: {config.video_generator.api_base_url}"
    )

    # ── Modülleri başlat ─────────────────────────────────────
    from core.orchestrator import Orchestrator
    from core.scheduler import AgentScheduler

    orchestrator = Orchestrator(config)
    scheduler = AgentScheduler(config)

    # Scheduler'a video üretim callback'ini bağla
    scheduler.set_video_callback(orchestrator.run_production_cycle)

    # ── Graceful shutdown handler ────────────────────────────
    shutdown_event = asyncio.Event()

    def _handle_signal(signum: int, frame: object) -> None:
        sig_name = signal.Signals(signum).name
        logger.info(f"📡 Sinyal alındı: {sig_name} — kapatılıyor...")
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # ── Hemen heartbeat yaz (healthcheck baştan geçsin) ──────
    _write_heartbeat(config)

    # ── Kontrol panelini ERKEN başlat (web arayüzü) ──────────
    # Video generator beklemesinden ÖNCE başlatılır ki panel (8090)
    # anında erişilebilir olsun, health wait'i beklemesin.
    from core.control_panel import run_panel

    panel_task = asyncio.create_task(run_panel(orchestrator, config))
    panel_task.add_done_callback(_panel_done)

    # ── Scheduler'ı ERKEN başlat (heartbeat + zamanlamalar) ──
    scheduler.start()
    for job in scheduler.get_next_run_times():
        logger.info(f"📅 {job['name']}: sonraki çalışma → {job['next_run']}")

    # ── Video generator'ın hazır olmasını bekle (bilgi amaçlı) ─
    logger.info("⏳ Video generator servisinin hazır olması bekleniyor...")
    vg_ready = await orchestrator.video_client.wait_until_healthy(
        max_wait=300, interval=10
    )
    if not vg_ready:
        logger.error(
            "❌ Video generator 5 dakika içinde hazır olmadı! "
            "Scheduler çalışıyor; üretim tetiklendiğinde tekrar denenecek."
        )
    else:
        logger.info("✅ Video generator hazır!")

    # ── İlk başlangıçta bir test üretimi yap (opsiyonel) ────
    run_initial = os.environ.get("AGENT_RUN_ON_START", "false").lower()
    if run_initial == "true":
        logger.info("🎬 İlk başlangıç: Test video üretimi tetikleniyor...")
        try:
            await orchestrator.run_production_cycle()
        except Exception as e:
            logger.error(f"❌ İlk test üretimi hatası: {e}")

    logger.info("=" * 60)
    logger.info("🟢 Agent aktif — 7/24 çalışmaya hazır!")
    logger.info("=" * 60)

    # ── Ana döngü: shutdown sinyali gelene kadar bekle ───────
    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass

    # ── Temiz kapatma ────────────────────────────────────────
    logger.info("🔻 Agent kapatılıyor...")
    scheduler.stop()
    panel_task.cancel()
    try:
        await panel_task
    except asyncio.CancelledError:
        pass
    await orchestrator.shutdown()
    logger.info("✅ Agent temiz bir şekilde kapatıldı. Hoşçakalın! 👋")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⌨️ Keyboard interrupt — çıkılıyor...")
    except Exception as e:
        logger.exception(f"💥 Kritik hata: {e}")
        sys.exit(1)
