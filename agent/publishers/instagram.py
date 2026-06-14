"""
AI Agent — Instagram Publisher
================================
Instagram Reels'e video paylaşımı.
Strateji: browser-use ile otonom paylaşım.
"""

from __future__ import annotations

import os
from typing import Any

from loguru import logger

from publishers.base import (
    BasePublisher,
    PublishResult,
    PublishStatus,
    VideoPost,
    browser_run_succeeded as _browser_run_succeeded,
    build_headless_browser as _build_headless_browser,
)


class InstagramPublisher(BasePublisher):
    """
    Instagram Reels video paylaşımcısı.

    browser-use ile otonom tarayıcı paylaşımı.
    """

    platform_name = "instagram"
    publish_method = "browser"

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.username = config.social_media.instagram_username
        self.password = config.social_media.instagram_password

    async def is_available(self) -> bool:
        """Instagram publisher'ın kullanılabilirliğini kontrol et."""
        if not self.username or not self.password:
            logger.debug("Instagram: Kullanıcı adı/şifre tanımlı değil, atlanıyor")
            return False
        return True

    async def authenticate(self) -> bool:
        """Instagram oturum doğrulama."""
        if self.username and self.password:
            logger.info(f"🔐 Instagram: Kimlik bilgileri mevcut ({self.username})")
            return True
        return False

    async def publish(self, post: VideoPost) -> PublishResult:
        """Instagram'a video paylaş — browser-use ile."""
        try:
            return await self._publish_via_browser(post)
        except Exception as e:
            logger.error(f"❌ Instagram browser publish hatası: {e}")
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                message=str(e),
            )

    async def _publish_via_browser(self, post: VideoPost) -> PublishResult:
        """browser-use kütüphanesi ile Instagram'a paylaşım."""
        try:
            from browser_use import Agent
            from langchain_google_genai import ChatGoogleGenerativeAI

            if not os.path.exists(post.video_path):
                return PublishResult(
                    platform=self.platform_name,
                    status=PublishStatus.FAILED,
                    message=f"Video dosyası bulunamadı: {post.video_path}",
                )

            caption = f"{post.title}\n\n{post.description}\n\n{post.hashtags}"

            llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=self.config.llm.api_key,
            )

            # Şifreyi LLM'e düz metin göndermemek için browser-use'un
            # sensitive_data placeholder mekanizması kullanılır.
            sensitive_data = {
                "ig_username": self.username,
                "ig_password": self.password,
            }

            task = f"""
            Instagram'a bir Reels videosu yükle. Adımlar:
            1. https://www.instagram.com adresine git
            2. Eğer giriş sayfası gelirse:
               - Kullanıcı adı alanına ig_username placeholder'ını yaz
               - Şifre alanına ig_password placeholder'ını yaz
               ile giriş yap
            3. Yeni gönderi oluştur (+ butonuna tıkla)
            4. '{post.video_path}' dosyasını yükle
            5. 'Reels' seçeneğini seç
            6. Açıklama alanına şunu yaz: {caption}
            7. 'Paylaş' butonuna tıkla
            8. Yükleme tamamlanana kadar bekle
            """

            # Container'da tarayıcı headless çalışmalı
            browser = _build_headless_browser()
            agent_kwargs: dict[str, Any] = {"task": task, "llm": llm}
            if browser is not None:
                agent_kwargs["browser"] = browser

            try:
                try:
                    agent = Agent(sensitive_data=sensitive_data, **agent_kwargs)
                except TypeError:
                    # Eski browser-use sürümü sensitive_data desteklemiyor olabilir
                    logger.warning(
                        "⚠️ browser-use sensitive_data desteklemiyor — "
                        "kimlik bilgileri olmadan deneniyor"
                    )
                    agent = Agent(**agent_kwargs)
                result = await agent.run()
            finally:
                if browser is not None:
                    try:
                        await browser.close()
                    except Exception:
                        pass

            logger.info(f"🤖 Instagram browser-use sonucu: {result}")

            if not _browser_run_succeeded(result):
                return PublishResult(
                    platform=self.platform_name,
                    status=PublishStatus.FAILED,
                    message="browser-use görevi başarılı olarak doğrulanamadı",
                    metadata={"method": "browser-use"},
                )

            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.SUCCESS,
                message="Video browser-use ile paylaşıldı",
                metadata={"method": "browser-use"},
            )

        except ImportError:
            logger.error(
                "❌ browser-use veya langchain_google_genai kurulu değil"
            )
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                message="browser-use dependency missing",
            )
        except Exception as e:
            logger.error(f"❌ Instagram browser-use hatası: {e}")
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                message=str(e),
            )
