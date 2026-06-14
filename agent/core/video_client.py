"""
AI Agent — Video Generator API Client
=======================================
MoneyPrinterTurbo FastAPI backend'ine HTTP istekleri gönderir.
Video üretim tetikleme, durum sorgulama ve dosya erişimi.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import httpx
from loguru import logger

from config import AgentConfig


class VideoGeneratorClient:
    """
    MoneyPrinterTurbo FastAPI backend'i ile iletişim kurar.

    Endpoints:
        POST /api/v1/videos       → video üretim tetikleme
        GET  /api/v1/tasks/{id}   → task durum sorgulama
    """

    # MoneyPrinterTurbo task state sabitleri (app/models/const.py)
    STATE_FAILED = -1
    STATE_COMPLETE = 1
    STATE_PROCESSING = 4

    def __init__(self, config: AgentConfig) -> None:
        self.base_url = config.video_generator.api_base_url.rstrip("/")
        self.timeout = config.video_generator.api_timeout
        self.health_url = config.video_generator.health_check_url
        self.defaults = config.video_generator
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=30.0),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """HTTP client'ı kapat."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Health Check ─────────────────────────────────────────

    async def is_healthy(self) -> bool:
        """Video generator servisinin sağlıklı olup olmadığını kontrol et."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # FastAPI health
                resp = await client.get(f"{self.base_url}/")
                api_ok = resp.status_code < 500

                # Streamlit health (opsiyonel)
                try:
                    resp2 = await client.get(self.health_url)
                    ui_ok = resp2.status_code == 200
                except Exception:
                    ui_ok = False

            healthy = api_ok
            logger.debug(
                f"🏥 Health check: API={'✅' if api_ok else '❌'} | "
                f"UI={'✅' if ui_ok else '❌'}"
            )
            return healthy
        except Exception as e:
            logger.warning(f"🏥 Health check başarısız: {e}")
            return False

    async def wait_until_healthy(
        self, max_wait: int = 300, interval: int = 10
    ) -> bool:
        """Servis sağlıklı olana kadar bekle."""
        logger.info(
            f"⏳ Video generator'ın hazır olması bekleniyor (max {max_wait}s)..."
        )
        elapsed = 0
        while elapsed < max_wait:
            if await self.is_healthy():
                logger.info("✅ Video generator hazır!")
                return True
            await asyncio.sleep(interval)
            elapsed += interval
            logger.debug(f"⏳ Bekleniyor... ({elapsed}/{max_wait}s)")

        logger.error(f"❌ Video generator {max_wait}s içinde hazır olmadı!")
        return False

    # ── Video Üretim ─────────────────────────────────────────

    async def create_video(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Video üretim task'ı oluştur.

        Args:
            params: VideoParams schema'sına uygun parametreler
                - video_subject: str (zorunlu)
                - video_script: str (opsiyonel, LLM otomatik üretir)
                - video_aspect: str (varsayılan: 9:16)
                - voice_name: str
                - video_source: str
                - video_clip_duration: int
                - video_count: int

        Returns:
            dict: {"task_id": "xxx", "status": "pending", ...}
        """
        # Varsayılan değerleri uygula
        request_body = {
            "video_subject": params.get("video_subject", ""),
            "video_script": params.get("video_script", ""),
            "video_terms": params.get("video_terms"),
            "video_aspect": params.get("video_aspect", self.defaults.default_aspect),
            "video_concat_mode": params.get("video_concat_mode", "random"),
            "video_clip_duration": params.get(
                "video_clip_duration", self.defaults.default_clip_duration
            ),
            "video_count": params.get(
                "video_count", self.defaults.default_video_count
            ),
            "video_source": params.get(
                "video_source", self.defaults.default_video_source
            ),
            "voice_name": params.get("voice_name", self.defaults.default_voice),
            "voice_volume": params.get("voice_volume", 1.0),
            "bgm_type": params.get("bgm_type", "random"),
            "bgm_volume": params.get("bgm_volume", 0.2),
            "subtitle_enabled": params.get("subtitle_enabled", True),
        }

        logger.info(
            f"🎬 Video üretim isteği gönderiliyor: "
            f"'{request_body['video_subject'][:50]}...'"
        )

        client = await self._get_client()
        response = await client.post("/api/v1/videos", json=request_body)
        response.raise_for_status()

        result = response.json()
        task_id = result.get("data", {}).get("task_id", "unknown")
        logger.info(f"✅ Video task oluşturuldu: {task_id}")

        return result

    # ── Task Durum Sorgulama ─────────────────────────────────

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Task durumunu sorgula."""
        client = await self._get_client()
        response = await client.get(f"/api/v1/tasks/{task_id}")
        response.raise_for_status()
        return response.json()

    async def wait_for_completion(
        self,
        task_id: str,
        poll_interval: int = 15,
        max_wait: int = 900,  # 15 dakika
    ) -> dict[str, Any]:
        """
        Task tamamlanana kadar polling yap.

        Returns:
            dict: Son task durumu (videos, durum vb.)

        Raises:
            TimeoutError: max_wait aşıldığında
            RuntimeError: task başarısız olduğunda
        """
        logger.info(
            f"⏳ Video üretimi bekleniyor: {task_id} (max {max_wait}s)..."
        )
        elapsed = 0
        last_progress = ""

        while elapsed < max_wait:
            try:
                result = await self.get_task_status(task_id)
                data = result.get("data", {})
                # MoneyPrinterTurbo state'i integer döndürür
                # (-1=failed, 1=complete, 4=processing)
                state = data.get("state")
                progress = data.get("progress", 0)

                # Durum değişikliğini logla
                current_progress = f"{state}:{progress}"
                if current_progress != last_progress:
                    logger.info(
                        f"📊 Task {task_id}: state={state} progress={progress}%"
                    )
                    last_progress = current_progress

                if state == self.STATE_COMPLETE:
                    logger.info(f"🎉 Video üretimi tamamlandı: {task_id}")
                    return result

                if state == self.STATE_FAILED:
                    error_msg = data.get("message", "Bilinmeyen hata")
                    logger.error(f"❌ Video üretimi başarısız: {task_id} — {error_msg}")
                    raise RuntimeError(
                        f"Video generation failed: {error_msg}"
                    )

            except httpx.HTTPError as e:
                logger.warning(
                    f"⚠️ Task durum sorgulama hatası: {e} — tekrar denenecek"
                )

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(
            f"Video generation timed out after {max_wait}s: {task_id}"
        )

    # ── Dosya Erişimi ────────────────────────────────────────

    async def get_video_file_url(self, task_id: str) -> Optional[str]:
        """Tamamlanmış videonun URL'sini al."""
        try:
            result = await self.get_task_status(task_id)
            data = result.get("data", {})

            # Önce birleştirilmiş video, yoksa tekil videolar
            videos = data.get("combined_videos") or data.get("videos") or []
            if videos:
                first = videos[0]
                first_video = first if isinstance(first, str) else first.get("url", "")
                if first_video:
                    return f"{self.base_url}/{first_video.lstrip('/')}"

            return None
        except Exception as e:
            logger.error(f"❌ Video URL alınamadı: {e}")
            return None
