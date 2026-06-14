"""
AI Agent — TikTok Publisher
=============================
TikTok'a video paylaşımı.
Strateji: browser-use ile otonom paylaşım (API alternatifi hazır).
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from loguru import logger

from publishers.base import (
    BasePublisher,
    PublishResult,
    PublishStatus,
    VideoPost,
    browser_run_succeeded as _browser_run_succeeded,
    build_headless_browser as _build_headless_browser,
)


class TikTokPublisher(BasePublisher):
    """
    TikTok video paylaşımcısı.

    Birincil: browser-use ile otonom tarayıcı paylaşımı
    Alternatif: TikTok Content Posting API (developer hesabı gerekir)
    """

    platform_name = "tiktok"
    publish_method = "browser"

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.session_cookie = config.social_media.tiktok_session_cookie
        self._data_dir = getattr(config, "data_dir", "/agent/data")

    async def is_available(self) -> bool:
        """TikTok publisher'ın kullanılabilirliğini kontrol et."""
        if not self.session_cookie:
            logger.debug("TikTok: Session cookie tanımlı değil, atlanıyor")
            return False
        return True

    async def authenticate(self) -> bool:
        """TikTok oturum doğrulama."""
        # browser-use ile oturum cookie'si üzerinden çalışır
        if self.session_cookie:
            logger.info("🔐 TikTok: Session cookie mevcut")
            return True
        return False

    # ── Cookie / Tarayıcı Yardımcıları ───────────────────────

    def _build_cookies_file(self) -> Optional[str]:
        """
        SOCIAL_TIKTOK_SESSION_COOKIE değerini Playwright formatında bir
        cookies JSON dosyasına çevir ve yolunu döndür.

        Üç giriş formatı desteklenir:
          1. JSON dizisi  → tam çerez ihracı (tarayıcı eklentisinden)
          2. Header dizgi → "sessionid=abc; tt_csrf=xyz"
          3. Tek değer    → yalnızca sessionid değeri
        """
        raw = (self.session_cookie or "").strip()
        if not raw:
            return None

        cookies: list[dict[str, Any]] = []

        # 1) JSON dizisi mi?
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    cookies = parsed
            except json.JSONDecodeError:
                logger.warning(
                    "⚠️ TikTok cookie JSON olarak ayrıştırılamadı, "
                    "header dizgisi olarak denenecek"
                )

        # 2) "k=v; k2=v2" header dizgisi mi?
        if not cookies and "=" in raw:
            for pair in raw.split(";"):
                pair = pair.strip()
                if "=" not in pair:
                    continue
                name, _, value = pair.partition("=")
                cookies.append({"name": name.strip(), "value": value.strip()})

        # 3) Çıplak değer → sessionid varsay
        if not cookies:
            cookies.append({"name": "sessionid", "value": raw})

        # Playwright domain/path gerektirir — eksikse tamamla
        for c in cookies:
            c.setdefault("domain", ".tiktok.com")
            c.setdefault("path", "/")

        path = os.path.join(self._data_dir, "tiktok_cookies.json")
        try:
            os.makedirs(self._data_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cookies, f)
            logger.info(f"🍪 TikTok cookie dosyası hazırlandı ({len(cookies)} çerez)")
            return path
        except Exception as e:
            logger.error(f"❌ TikTok cookie dosyası yazılamadı: {e}")
            return None

    async def publish(self, post: VideoPost) -> PublishResult:
        """TikTok'a video paylaş — browser-use ile."""
        try:
            return await self._publish_via_browser(post)
        except Exception as e:
            logger.error(f"❌ TikTok browser publish hatası: {e}")
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                message=str(e),
            )

    async def _publish_via_browser(self, post: VideoPost) -> PublishResult:
        """browser-use kütüphanesi ile TikTok'a paylaşım."""
        try:
            from browser_use import Agent
            from langchain_google_genai import ChatGoogleGenerativeAI

            # Video dosyasının varlığını kontrol et
            if not os.path.exists(post.video_path):
                return PublishResult(
                    platform=self.platform_name,
                    status=PublishStatus.FAILED,
                    message=f"Video dosyası bulunamadı: {post.video_path}",
                )

            # Kapsiyon oluştur
            caption = f"{post.title}\n\n{post.description}\n\n{post.hashtags}"

            # LLM'i yapılandır (browser-use'un beyni)
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=self.config.llm.api_key,
            )

            # Oturum cookie'sini headless tarayıcıya yükle
            cookies_file = self._build_cookies_file()
            browser = _build_headless_browser(cookies_file)
            session_note = (
                "Oturum cookie ile zaten açık; giriş yapman gerekmez."
                if browser is not None
                else "Oturum açık değilse giriş ekranını bekle."
            )

            # Browser-use agent görevi
            task = f"""
            TikTok'a bir video yükle. Adımlar:
            1. https://www.tiktok.com/upload adresine git
            2. {session_note}
            3. '{post.video_path}' dosyasını yükle
            4. Açıklama alanına şunu yaz: {caption}
            5. 'Post' veya 'Paylaş' butonuna tıkla
            6. Yükleme tamamlanana kadar bekle
            """

            try:
                if browser is not None:
                    agent = Agent(task=task, llm=llm, browser=browser)
                else:
                    agent = Agent(task=task, llm=llm)
                result = await agent.run()
            finally:
                # Tarafımızca oluşturulan tarayıcının yaşam döngüsünü kapat
                if browser is not None:
                    try:
                        await browser.close()
                    except Exception:
                        pass

            logger.info(f"🤖 TikTok browser-use sonucu: {result}")

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
                metadata={"method": "browser-use", "cookies_loaded": browser is not None},
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
            logger.error(f"❌ TikTok browser-use hatası: {e}")
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                message=str(e),
            )
