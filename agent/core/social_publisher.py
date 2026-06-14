"""
AI Agent — Social Publisher (Facade)
======================================
Tüm sosyal medya publisher'larını tek bir arayüzden yönetir.
Platform seçimi, paylaşım kuyruğu ve sonuç takibi.
"""

from __future__ import annotations

import os
from typing import Any

from loguru import logger

from config import AgentConfig
from publishers.base import BasePublisher, PublishResult, PublishStatus, VideoPost
from publishers.tiktok import TikTokPublisher
from publishers.instagram import InstagramPublisher
from publishers.youtube import YouTubePublisher


class SocialPublisher:
    """
    Sosyal medya paylaşım facade'ı.

    Tüm aktif platform publisher'larını yönetir ve
    videoyu sırayla her platforma paylaşır.
    """

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._publishers: dict[str, BasePublisher] = {}
        self._init_publishers()

    def _init_publishers(self) -> None:
        """Aktif platform publisher'larını başlat."""
        enabled = [
            p.strip().lower()
            for p in self.config.social_media.enabled_platforms.split(",")
            if p.strip()
        ]

        # Paylaşım stratejisi → hangi yöntemlere izin verilecek
        # api    → sadece resmi API publisher'ları (YouTube)
        # browser→ sadece browser-use publisher'ları (TikTok, Instagram)
        # hybrid → her ikisi
        strategy = (self.config.social_media.publish_strategy or "hybrid").lower()
        allowed_methods = {
            "api": {"api"},
            "browser": {"browser"},
            "hybrid": {"api", "browser"},
        }.get(strategy, {"api", "browser"})

        publisher_map: dict[str, type[BasePublisher]] = {
            "tiktok": TikTokPublisher,
            "instagram": InstagramPublisher,
            "youtube": YouTubePublisher,
        }

        for platform in enabled:
            if platform not in publisher_map:
                logger.warning(f"⚠️ Bilinmeyen platform: {platform}")
                continue

            publisher_cls = publisher_map[platform]
            if publisher_cls.publish_method not in allowed_methods:
                logger.info(
                    f"⏭️ {platform} ({publisher_cls.publish_method}) "
                    f"'{strategy}' stratejisi dışında, atlanıyor"
                )
                continue

            try:
                self._publishers[platform] = publisher_cls(self.config)
                logger.info(f"📱 Publisher başlatıldı: {platform}")
            except Exception as e:
                logger.error(f"❌ Publisher başlatma hatası ({platform}): {e}")

        logger.info(
            f"📱 Aktif publisher'lar: {list(self._publishers.keys()) or 'Yok'}"
        )

    async def publish_to_all(
        self, video_path: str, metadata: dict[str, str], topic: str
    ) -> list[PublishResult]:
        """
        Videoyu tüm aktif platformlara paylaş.

        Args:
            video_path: Video dosyasının tam yolu
            metadata: {"title", "description", "hashtags"}
            topic: Video konusu

        Returns:
            list[PublishResult]: Her platform için paylaşım sonucu
        """
        if not self._publishers:
            logger.warning("⚠️ Hiçbir sosyal medya publisher'ı aktif değil")
            return []

        # Video dosyası kontrolü
        if not os.path.exists(video_path):
            logger.error(f"❌ Video dosyası bulunamadı: {video_path}")
            return [
                PublishResult(
                    platform="all",
                    status=PublishStatus.FAILED,
                    message=f"Video file not found: {video_path}",
                )
            ]

        # VideoPost oluştur
        post = VideoPost(
            video_path=video_path,
            title=metadata.get("title", topic[:100]),
            description=metadata.get("description", ""),
            hashtags=metadata.get("hashtags", "#shorts #viral"),
            topic=topic,
            language=self.config.content.language,
        )

        # Tüm platformlara sırayla paylaş
        results: list[PublishResult] = []

        for platform_name, publisher in self._publishers.items():
            logger.info(f"📤 Paylaşım başlıyor: {platform_name}")
            result = await publisher.safe_publish(post)
            results.append(result)

            # Platform arası bekleme (rate limiting koruması)
            if result.status == PublishStatus.SUCCESS:
                import asyncio
                await asyncio.sleep(5)  # 5 saniye bekleme

        # Özet logla
        success_count = sum(
            1 for r in results if r.status == PublishStatus.SUCCESS
        )
        total = len(results)
        logger.info(
            f"📊 Paylaşım özeti: {success_count}/{total} başarılı | "
            f"Konu: '{topic[:40]}...'"
        )

        return results

    async def publish_to_platform(
        self,
        platform: str,
        video_path: str,
        metadata: dict[str, str],
        topic: str,
    ) -> PublishResult:
        """Belirli bir platforma paylaş."""
        publisher = self._publishers.get(platform)
        if not publisher:
            return PublishResult(
                platform=platform,
                status=PublishStatus.SKIPPED,
                message=f"Publisher '{platform}' bulunamadı veya aktif değil",
            )

        post = VideoPost(
            video_path=video_path,
            title=metadata.get("title", topic[:100]),
            description=metadata.get("description", ""),
            hashtags=metadata.get("hashtags", "#shorts #viral"),
            topic=topic,
            language=self.config.content.language,
        )

        return await publisher.safe_publish(post)

    def get_active_platforms(self) -> list[str]:
        """Aktif platform listesi."""
        return list(self._publishers.keys())
