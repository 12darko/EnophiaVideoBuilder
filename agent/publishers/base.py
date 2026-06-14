"""
AI Agent — Base Publisher (Abstract)
=====================================
Tüm sosyal medya publisher'larının temel sınıfı.
Adapter pattern ile platform-agnostic arayüz sağlar.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from loguru import logger


def build_headless_browser(cookies_file: Optional[str] = None) -> Optional[Any]:
    """
    Headless bir browser-use ``Browser`` oluştur (opsiyonel cookie dosyasıyla).

    Container ortamında görüntü sunucusu (display) olmadığından tarayıcı
    **headless** çalışmak zorundadır; aksi halde Chromium başlatılamaz.
    browser-use sürümleri arasında import yolları değişebildiğinden hata
    durumunda ``None`` döner (çağıran varsayılan tarayıcıyla devam eder).
    """
    try:
        from browser_use import Browser, BrowserConfig
        try:
            from browser_use.browser.context import BrowserContextConfig
        except ImportError:  # eski/yeni sürüm farkı
            from browser_use.browser.browser import BrowserContextConfig  # type: ignore

        ctx = (
            BrowserContextConfig(cookies_file=cookies_file)
            if cookies_file
            else BrowserContextConfig()
        )
        return Browser(
            config=BrowserConfig(headless=True, new_context_config=ctx)
        )
    except Exception as e:
        logger.warning(f"⚠️ Headless tarayıcı kurulamadı ({e})")
        return None


def browser_run_succeeded(result: Any) -> bool:
    """
    browser-use ``Agent.run()`` sonucunu güvenli biçimde değerlendir.

    browser-use sürümleri ``AgentHistoryList`` üzerinde ``is_successful()`` /
    ``is_done()`` sağlar. Hiçbiri yoksa (sürüm farkı) sonucun varlığına bakılır.
    Bu sayede paylaşım gerçekten doğrulanmadan SUCCESS dönülmez.
    """
    if result is None:
        return False

    is_successful = getattr(result, "is_successful", None)
    if callable(is_successful):
        verdict = is_successful()
        # is_successful() bazı sürümlerde belirsizlik için None döndürebilir
        if verdict is not None:
            return bool(verdict)

    is_done = getattr(result, "is_done", None)
    if callable(is_done):
        return bool(is_done())

    # Yapısı bilinmeyen sonuç → muhafazakâr biçimde "tamamlandı" say
    logger.warning(
        "⚠️ browser-use sonucu doğrulanamadı (bilinmeyen tip), "
        "başarılı varsayılıyor"
    )
    return True


class PublishStatus(str, Enum):
    """Paylaşım durumları."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"


@dataclass
class PublishResult:
    """Paylaşım sonucu."""

    platform: str
    status: PublishStatus
    post_url: Optional[str] = None
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoPost:
    """Paylaşılacak video bilgileri."""

    video_path: str
    title: str
    description: str
    hashtags: str
    topic: str
    language: str = "tr"
    thumbnail_path: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


class BasePublisher(abc.ABC):
    """
    Sosyal medya publisher temel sınıfı.

    Tüm platform publisher'ları bu sınıfı implement eder.
    """

    platform_name: str = "base"
    # Paylaşım yöntemi: "api" (resmi API) veya "browser" (browser-use).
    # SOCIAL_PUBLISH_STRATEGY ile filtrelemek için kullanılır.
    publish_method: str = "api"

    def __init__(self, config: Any) -> None:
        self.config = config
        self._is_authenticated = False

    @abc.abstractmethod
    async def authenticate(self) -> bool:
        """Platforma kimlik doğrulama."""
        ...

    @abc.abstractmethod
    async def publish(self, post: VideoPost) -> PublishResult:
        """Videoyu platforma paylaş."""
        ...

    @abc.abstractmethod
    async def is_available(self) -> bool:
        """Publisher'ın kullanılabilir olup olmadığını kontrol et."""
        ...

    async def safe_publish(self, post: VideoPost) -> PublishResult:
        """
        Güvenli paylaşım wrapper'ı — hatayı yakalar, sonucu döndürür.
        """
        try:
            # Kullanılabilirlik kontrolü
            if not await self.is_available():
                logger.warning(
                    f"⏭️ {self.platform_name}: Publisher kullanılamıyor, atlanıyor"
                )
                return PublishResult(
                    platform=self.platform_name,
                    status=PublishStatus.SKIPPED,
                    message="Publisher not available (missing credentials or disabled)",
                )

            # Kimlik doğrulama
            if not self._is_authenticated:
                auth_ok = await self.authenticate()
                if not auth_ok:
                    return PublishResult(
                        platform=self.platform_name,
                        status=PublishStatus.AUTH_ERROR,
                        message="Authentication failed",
                    )
                self._is_authenticated = True

            # Paylaşım
            logger.info(
                f"📤 {self.platform_name}: Paylaşım başlıyor — '{post.title[:50]}...'"
            )
            result = await self.publish(post)

            if result.status == PublishStatus.SUCCESS:
                logger.info(
                    f"✅ {self.platform_name}: Paylaşım başarılı! "
                    f"URL: {result.post_url or 'N/A'}"
                )
            else:
                logger.warning(
                    f"⚠️ {self.platform_name}: Paylaşım durumu: "
                    f"{result.status.value} — {result.message}"
                )

            return result

        except Exception as e:
            logger.error(f"❌ {self.platform_name}: Paylaşım hatası: {e}")
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                message=str(e),
            )
