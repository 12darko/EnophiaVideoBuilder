"""
AI Agent — Orchestrator (Ana İş Akışı Beyni)
===============================================
Video üretimi → Sosyal medya paylaşımı → Hata yönetimi
döngüsünü yöneten ana orkestratör.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Optional

from loguru import logger

from config import AgentConfig
from core.content_brain import ContentBrain
from core.profiles import Profile, ProfileStore
from core.self_healer import SelfHealer
from core.social_publisher import SocialPublisher
from core.video_client import VideoGeneratorClient


class Orchestrator:
    """
    Otonom video fabrikasının ana orkestratörü.

    İş akışı:
    1. LLM ile konu/senaryo üret
    2. MoneyPrinterTurbo API'ye video üretim isteği gönder
    3. Video hazır olana kadar bekle
    4. Sosyal medya metadata üret
    5. Tüm aktif platformlara paylaş
    6. Sonuçları logla

    Her adımda hata olursa SelfHealer devreye girer.
    """

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.video_client = VideoGeneratorClient(config)
        self.content_brain = ContentBrain(config)
        self.social_publisher = SocialPublisher(config)
        self.self_healer = SelfHealer(config)

        # Çoklu kanal profilleri (varsayılan env'den seed edilir)
        self.profiles = ProfileStore(config)
        self.profiles.ensure_default()

        # İstatistikler
        self._stats = {
            "total_attempts": 0,
            "successful_videos": 0,
            "failed_videos": 0,
            "total_posts": 0,
            "successful_posts": 0,
        }

        # Çalışma kilidi — aynı anda tek video üretimi
        self._production_lock = asyncio.Lock()

        # Hız sınırlama durumu (min aralık + günlük limit)
        self._last_cycle_start: Optional[datetime] = None
        self._daily_count_date: Optional[str] = None
        self._daily_count: int = 0

    async def run_production_cycle(
        self,
        topic_override: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Tam bir video üretim döngüsü çalıştır.

        Args:
            topic_override: Verilirse LLM konu üretmez, bu konu kullanılır
                (panelden "şu konuda üret" komutu için).
            profile_id: Verilirse o profilin (kanalın) ayarlarıyla üretir;
                None ise varsayılan profil kullanılır.

        Returns:
            dict: Döngü sonuç raporu
        """
        # Profili çöz
        profile = (
            self.profiles.get(profile_id) if profile_id else None
        ) or self.profiles.ensure_default()
        if self._production_lock.locked():
            logger.warning(
                "⚠️ Bir üretim döngüsü zaten çalışıyor, bu tetikleme atlanıyor"
            )
            return {"status": "skipped", "reason": "production_in_progress"}

        # ── Minimum aralık kontrolü ──────────────────────────
        min_interval = self.config.scheduler.min_interval_minutes
        if self._last_cycle_start and min_interval > 0:
            elapsed_min = (
                datetime.now() - self._last_cycle_start
            ).total_seconds() / 60
            if elapsed_min < min_interval:
                logger.warning(
                    f"⚠️ Son üretimden bu yana {elapsed_min:.0f} dk geçti, "
                    f"minimum {min_interval} dk — tetikleme atlanıyor"
                )
                return {"status": "skipped", "reason": "min_interval_not_met"}

        # ── Günlük üretim limiti kontrolü ────────────────────
        today = datetime.now().strftime("%Y-%m-%d")
        if self._daily_count_date != today:
            self._daily_count_date = today
            self._daily_count = 0
        daily_cap = self.config.scheduler.daily_video_count
        if daily_cap > 0 and self._daily_count >= daily_cap:
            logger.warning(
                f"⚠️ Günlük üretim limiti ({daily_cap}) doldu — atlanıyor"
            )
            return {"status": "skipped", "reason": "daily_cap_reached"}

        async with self._production_lock:
            self._last_cycle_start = datetime.now()
            self._daily_count += 1
            return await self._execute_cycle(topic_override, profile)

    async def _execute_cycle(
        self,
        topic_override: Optional[str] = None,
        profile: Optional[Profile] = None,
    ) -> dict[str, Any]:
        """Üretim döngüsünün iç implementasyonu."""
        if profile is None:
            profile = self.profiles.ensure_default()
        cycle_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._stats["total_attempts"] += 1

        logger.info(f"{'='*60}")
        logger.info(
            f"🎬 Üretim döngüsü başladı: {cycle_id} | "
            f"Profil: {profile.name} ({profile.niche}/{profile.language})"
        )
        logger.info(f"{'='*60}")

        result = {
            "cycle_id": cycle_id,
            "status": "unknown",
            "profile_id": profile.id,
            "profile_name": profile.name,
            "topic": None,
            "video_task_id": None,
            "video_path": None,
            "publish_results": [],
            "error": None,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            # ── Adım 0: Video Generator sağlık kontrolü ─────
            logger.info("🏥 Adım 0/5: Video generator sağlık kontrolü...")
            healthy = await self.video_client.is_healthy()
            if not healthy:
                logger.warning(
                    "⚠️ Video generator hazır değil, bekleniyor..."
                )
                healthy = await self.video_client.wait_until_healthy(
                    max_wait=180
                )
                if not healthy:
                    raise ConnectionError(
                        "Video generator 180s içinde hazır olmadı"
                    )

            # ── Adım 1: Konu üret (veya manuel konu) ────────
            if topic_override:
                topic = topic_override.strip()
                logger.info(f"📝 Adım 1/5: Manuel konu kullanılıyor: '{topic}'")
            else:
                logger.info("📝 Adım 1/5: Konu üretiliyor...")
                topic = await self._with_healing(
                    self.content_brain.generate_topic,
                    heal_id=f"{cycle_id}_topic",
                    niche=profile.niche,
                    language=profile.language,
                    topic_pool=profile.topic_pool,
                )
            result["topic"] = topic
            logger.info(f"✅ Konu: '{topic}'")

            # ── Adım 2: Senaryo üret ────────────────────────
            logger.info("📜 Adım 2/5: Senaryo üretiliyor...")
            script = await self._with_healing(
                self.content_brain.generate_script,
                heal_id=f"{cycle_id}_script",
                topic=topic,
                language=profile.language,
                duration=profile.target_duration,
            )
            logger.info(f"✅ Senaryo: {len(script)} karakter")

            # ── Adım 3: Video üret ──────────────────────────
            logger.info("🎥 Adım 3/5: Video üretiliyor...")
            video_params = {
                "video_subject": topic,
                "video_script": script,
                "video_aspect": self.config.video_generator.default_aspect,
                "voice_name": self.config.video_generator.default_voice,
                "video_source": self.config.video_generator.default_video_source,
                "video_clip_duration": self.config.video_generator.default_clip_duration,
                "video_count": 1,
            }

            create_result = await self._with_healing(
                self.video_client.create_video,
                heal_id=f"{cycle_id}_create",
                params=video_params,
            )

            task_id = create_result.get("data", {}).get("task_id")
            if not task_id:
                raise RuntimeError("Video task ID alınamadı")

            result["video_task_id"] = task_id

            # Video tamamlanmasını bekle
            completion = await self._with_healing(
                self.video_client.wait_for_completion,
                heal_id=f"{cycle_id}_wait",
                task_id=task_id,
            )

            # Video dosya yolunu al
            video_url = await self.video_client.get_video_file_url(task_id)
            result["video_path"] = video_url

            self._stats["successful_videos"] += 1
            logger.info(f"🎉 Video hazır! Task: {task_id}")

            # ── Adım 4: Sosyal medya metadata üret ──────────
            logger.info("🏷️ Adım 4/5: Sosyal medya metadata üretiliyor...")
            metadata = await self._with_healing(
                self.content_brain.generate_social_metadata,
                heal_id=f"{cycle_id}_metadata",
                topic=topic,
                language=profile.language,
                hashtags=profile.hashtags,
            )

            # ── Adım 5: Sosyal medyaya paylaş ───────────────
            logger.info("📤 Adım 5/5: Sosyal medyaya paylaşılıyor...")

            # Video dosyasını al (output volume'dan)
            video_local_path = await self._resolve_video_path(task_id)

            if video_local_path:
                # Paylaşım gecikmesi
                delay = self.config.scheduler.post_delay_minutes * 60
                if delay > 0:
                    logger.info(
                        f"⏳ Paylaşım gecikmesi: {delay}s bekleniyor..."
                    )
                    await asyncio.sleep(delay)

                publish_results = await self.social_publisher.publish_to_all(
                    video_path=video_local_path,
                    metadata=metadata,
                    topic=topic,
                    platforms=profile.enabled_platforms or None,
                )
                result["publish_results"] = [
                    {
                        "platform": r.platform,
                        "status": r.status.value,
                        "url": r.post_url,
                        "message": r.message,
                    }
                    for r in publish_results
                ]

                self._stats["total_posts"] += len(publish_results)
                self._stats["successful_posts"] += sum(
                    1 for r in publish_results if r.status.value == "success"
                )
            else:
                logger.warning(
                    "⚠️ Video dosyası bulunamadı, sosyal medya paylaşımı atlanıyor"
                )

            result["status"] = "success"
            self.self_healer.reset_retry_count(cycle_id)

        except Exception as e:
            self._stats["failed_videos"] += 1
            result["status"] = "failed"
            result["error"] = str(e)
            logger.error(f"❌ Üretim döngüsü başarısız: {e}")

        # ── Sonuç raporu ─────────────────────────────────────
        self._log_cycle_result(result)
        self._save_cycle_result(result)

        return result

    async def _with_healing(
        self,
        func: Any,
        heal_id: str,
        max_attempts: int = 3,
        **kwargs: Any,
    ) -> Any:
        """
        Bir fonksiyonu self-healing sarmalayıcısı ile çalıştır.
        Hata olursa SelfHealer stratejisine göre yeniden dene.

        Args:
            func: Çalıştırılacak (async ya da sync) fonksiyon
            heal_id: Self-healing retry sayacı için etiket (func'a geçmez)
            **kwargs: Doğrudan ``func``'a iletilecek argümanlar
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                return await func(**kwargs) if asyncio.iscoroutinefunction(func) else func(**kwargs)
            except Exception as e:
                last_error = e
                logger.warning(
                    f"⚠️ Hata (deneme {attempt}/{max_attempts}): {e}"
                )

                # Self-healing
                healing_result = await self.self_healer.heal(
                    error=e,
                    task_id=heal_id,
                    context=kwargs,
                )

                if not healing_result["should_retry"]:
                    raise

                wait_secs = healing_result.get("wait_seconds", 10)
                if wait_secs > 0:
                    logger.info(f"⏳ {wait_secs}s bekleniyor...")
                    await asyncio.sleep(wait_secs)

                # Parametre değişikliği varsa uygula.
                # SelfHealer, context ile aynı şekilde anahtarlanmış bir sözlük
                # döndürür (ör. {"params": {...}}), bu yüzden doğrudan birleştirilir.
                if "modified_params" in healing_result:
                    kwargs.update(healing_result["modified_params"])

        raise last_error or RuntimeError("Unknown error after all retries")

    async def _resolve_video_path(self, task_id: str) -> Optional[str]:
        """
        Video dosyasının yerel (container içi) yolunu çöz.
        Shared output volume'dan dosyayı bul.
        """
        # MoneyPrinterTurbo output dizini (shared volume)
        output_base = "/shared_output"

        # Task ID'ye göre dosya ara
        if os.path.exists(output_base):
            for root, dirs, files in os.walk(output_base):
                for f in files:
                    if task_id in root and f.endswith(".mp4"):
                        path = os.path.join(root, f)
                        logger.info(f"📁 Video dosyası bulundu: {path}")
                        return path

        # Alternatif: doğrudan task_id klasöründe ara
        task_dir = os.path.join(output_base, task_id)
        if os.path.exists(task_dir):
            for f in os.listdir(task_dir):
                if f.endswith(".mp4"):
                    path = os.path.join(task_dir, f)
                    logger.info(f"📁 Video dosyası bulundu: {path}")
                    return path

        logger.warning(
            f"⚠️ Video dosyası bulunamadı: task_id={task_id}, "
            f"output_base={output_base}"
        )
        return None

    def _log_cycle_result(self, result: dict[str, Any]) -> None:
        """Döngü sonucunu detaylı logla."""
        status_emoji = "✅" if result["status"] == "success" else "❌"
        logger.info(f"{'='*60}")
        logger.info(f"{status_emoji} Döngü Raporu: {result['cycle_id']}")
        logger.info(f"  Durum: {result['status']}")
        logger.info(f"  Konu: {result.get('topic', 'N/A')}")
        logger.info(f"  Task ID: {result.get('video_task_id', 'N/A')}")

        if result.get("publish_results"):
            for pr in result["publish_results"]:
                logger.info(
                    f"  📱 {pr['platform']}: {pr['status']} | {pr.get('url', '')}"
                )

        if result.get("error"):
            logger.error(f"  Hata: {result['error']}")

        logger.info(f"📊 Toplam İstatistik: {json.dumps(self._stats, indent=2)}")
        logger.info(f"{'='*60}")

    def _save_cycle_result(self, result: dict[str, Any]) -> None:
        """Döngü sonucunu dosyaya kaydet (kalıcılık)."""
        try:
            history_dir = os.path.join(self.config.data_dir, "history")
            os.makedirs(history_dir, exist_ok=True)

            filename = f"{result['cycle_id']}.json"
            filepath = os.path.join(history_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            logger.debug(f"💾 Döngü sonucu kaydedildi: {filepath}")
        except Exception as e:
            logger.error(f"❌ Döngü sonucu kaydetme hatası: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Agent istatistiklerini döndür."""
        return {
            **self._stats,
            "healing_stats": self.self_healer.get_stats(),
            "active_platforms": self.social_publisher.get_active_platforms(),
        }

    async def shutdown(self) -> None:
        """Orkestratörü kapat."""
        logger.info("🔻 Orchestrator kapatılıyor...")
        await self.video_client.close()
        logger.info("✅ Orchestrator kapatıldı")
