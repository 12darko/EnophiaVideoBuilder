"""
AI Agent — Scheduler (7/24 Zamanlayıcı)
==========================================
APScheduler ile cron tabanlı görev zamanlama.
Video üretim ve sosyal medya paylaşım takvimi.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable, Coroutine, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from config import AgentConfig


class AgentScheduler:
    """
    7/24 çalışan görev zamanlayıcı.

    Görevleri:
    - Belirlenen saatlerde video üretimi tetiklemek
    - Heartbeat güncellemek (container health check için)
    - Periyodik log temizliği
    """

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.scheduler = AsyncIOScheduler(
            timezone="Europe/Istanbul",
            job_defaults={
                "coalesce": True,  # Kaçırılan job'ları birleştir
                "max_instances": 1,  # Aynı job'dan max 1 instance
                "misfire_grace_time": 300,  # 5 dk grace time
            },
        )
        self._video_callback: Optional[
            Callable[[], Coroutine[Any, Any, None]]
        ] = None

    def set_video_callback(
        self, callback: Callable[[], Coroutine[Any, Any, None]]
    ) -> None:
        """Video üretim callback fonksiyonunu ayarla."""
        self._video_callback = callback

    def setup_schedules(self) -> None:
        """Tüm zamanlanmış görevleri kur."""

        # ── Video Üretim Schedule'ları ───────────────────────
        production_hours = [
            int(h.strip())
            for h in self.config.scheduler.production_hours.split(",")
            if h.strip().isdigit()
        ]

        if not production_hours:
            production_hours = [9, 14, 19]  # Varsayılan

        for hour in production_hours:
            job_id = f"video_production_{hour:02d}"
            self.scheduler.add_job(
                self._trigger_video_production,
                trigger=CronTrigger(hour=hour, minute=0),
                id=job_id,
                name=f"Video üretimi (saat {hour:02d}:00)",
                replace_existing=True,
            )
            logger.info(f"⏰ Schedule eklendi: {job_id} → her gün {hour:02d}:00")

        # ── Heartbeat (her 30 saniye) ────────────────────────
        self.scheduler.add_job(
            self._update_heartbeat,
            trigger=IntervalTrigger(
                seconds=self.config.heartbeat_interval_seconds
            ),
            id="heartbeat",
            name="Heartbeat güncelleme",
            replace_existing=True,
        )

        # ── Günlük log temizliği (her gün 04:00) ────────────
        self.scheduler.add_job(
            self._cleanup_logs,
            trigger=CronTrigger(hour=4, minute=0),
            id="log_cleanup",
            name="Log temizliği",
            replace_existing=True,
        )

        logger.info(
            f"📅 Toplam {len(self.scheduler.get_jobs())} schedule kuruldu. "
            f"Video saatleri: {production_hours}"
        )

    async def _trigger_video_production(self) -> None:
        """Video üretim callback'ini çağır."""
        if self._video_callback is None:
            logger.warning("⚠️ Video callback tanımlı değil!")
            return

        now = datetime.now()
        logger.info(
            f"🎬 Zamanlanmış video üretimi tetiklendi: {now.strftime('%H:%M:%S')}"
        )

        try:
            await self._video_callback()
        except Exception as e:
            logger.error(f"❌ Zamanlanmış video üretimi hatası: {e}")

    async def _update_heartbeat(self) -> None:
        """Heartbeat dosyasını güncelle (health check için)."""
        import os

        heartbeat_path = os.path.join(self.config.data_dir, "heartbeat")
        try:
            os.makedirs(os.path.dirname(heartbeat_path), exist_ok=True)
            with open(heartbeat_path, "w") as f:
                f.write(datetime.now().isoformat())
        except Exception as e:
            logger.error(f"❌ Heartbeat güncelleme hatası: {e}")

    async def _cleanup_logs(self) -> None:
        """Eski log dosyalarını temizle (7 günden eski)."""
        import glob
        import os
        import time

        log_dir = self.config.log_dir
        if not os.path.exists(log_dir):
            return

        cutoff = time.time() - (7 * 24 * 60 * 60)  # 7 gün
        cleaned = 0

        for log_file in glob.glob(os.path.join(log_dir, "*.log*")):
            try:
                if os.path.getmtime(log_file) < cutoff:
                    os.remove(log_file)
                    cleaned += 1
            except Exception:
                pass

        if cleaned > 0:
            logger.info(f"🧹 {cleaned} eski log dosyası temizlendi")

    def start(self) -> None:
        """Scheduler'ı başlat."""
        self.setup_schedules()
        self.scheduler.start()
        logger.info("✅ Scheduler başlatıldı — 7/24 çalışmaya hazır")

    def stop(self) -> None:
        """Scheduler'ı durdur."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("⏹️ Scheduler durduruldu")

    def get_next_run_times(self) -> list[dict[str, str]]:
        """Yaklaşan job çalışma zamanlarını listele."""
        jobs = []
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name or job.id,
                    "next_run": (
                        next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else "N/A"
                    ),
                }
            )
        return jobs
