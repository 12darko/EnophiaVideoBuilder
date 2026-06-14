"""
AI Agent — Self-Healing Module
================================
Hata algılama, sınıflandırma ve otomatik iyileşme.
Docker loglarını okur, hata tipini analiz eder,
uygun stratejiyle yeniden deneme yapar.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional

from loguru import logger
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import AgentConfig


class ErrorType(str, Enum):
    """Algılanabilen hata tipleri."""

    OOM = "out_of_memory"
    API_TIMEOUT = "api_timeout"
    FFMPEG_CRASH = "ffmpeg_crash"
    CONTAINER_DOWN = "container_down"
    NETWORK_ERROR = "network_error"
    LLM_ERROR = "llm_error"
    RATE_LIMIT = "rate_limit"
    UNKNOWN = "unknown"


class HealingAction(str, Enum):
    """İyileşme aksiyonları."""

    RETRY_IMMEDIATE = "retry_immediate"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    WAIT_AND_RETRY = "wait_and_retry"
    MODIFY_PARAMS = "modify_params"
    SKIP_AND_ALERT = "skip_and_alert"
    COOLDOWN = "cooldown"


# ── Hata Kalıpları (Error Patterns) ─────────────────────────
ERROR_PATTERNS: dict[str, ErrorType] = {
    "oom": ErrorType.OOM,
    "out of memory": ErrorType.OOM,
    "killed": ErrorType.OOM,
    "cannot allocate memory": ErrorType.OOM,
    "memoryerror": ErrorType.OOM,
    "timeout": ErrorType.API_TIMEOUT,
    "timed out": ErrorType.API_TIMEOUT,
    "read timeout": ErrorType.API_TIMEOUT,
    "connect timeout": ErrorType.API_TIMEOUT,
    "ffmpeg": ErrorType.FFMPEG_CRASH,
    "moviepy": ErrorType.FFMPEG_CRASH,
    "error writing trailer": ErrorType.FFMPEG_CRASH,
    "broken pipe": ErrorType.FFMPEG_CRASH,
    "connection refused": ErrorType.CONTAINER_DOWN,
    "connection reset": ErrorType.NETWORK_ERROR,
    "name resolution": ErrorType.NETWORK_ERROR,
    "dns": ErrorType.NETWORK_ERROR,
    "ssl": ErrorType.NETWORK_ERROR,
    "rate limit": ErrorType.RATE_LIMIT,
    "429": ErrorType.RATE_LIMIT,
    "too many requests": ErrorType.RATE_LIMIT,
    "quota": ErrorType.RATE_LIMIT,
    "invalid api key": ErrorType.LLM_ERROR,
    "authentication": ErrorType.LLM_ERROR,
    "unauthorized": ErrorType.LLM_ERROR,
}

# ── Hata Tipi → İyileşme Stratejisi Haritası ────────────────
HEALING_STRATEGIES: dict[ErrorType, HealingAction] = {
    ErrorType.OOM: HealingAction.COOLDOWN,
    ErrorType.API_TIMEOUT: HealingAction.RETRY_WITH_BACKOFF,
    ErrorType.FFMPEG_CRASH: HealingAction.MODIFY_PARAMS,
    ErrorType.CONTAINER_DOWN: HealingAction.WAIT_AND_RETRY,
    ErrorType.NETWORK_ERROR: HealingAction.WAIT_AND_RETRY,
    ErrorType.LLM_ERROR: HealingAction.SKIP_AND_ALERT,
    ErrorType.RATE_LIMIT: HealingAction.RETRY_WITH_BACKOFF,
    ErrorType.UNKNOWN: HealingAction.RETRY_WITH_BACKOFF,
}


class SelfHealer:
    """
    Kendi kendine iyileşme orkestratörü.

    Hata loglarını analiz eder, hata tipini sınıflandırır
    ve uygun stratejiyle kurtarma işlemi yapar.
    """

    def __init__(self, config: AgentConfig) -> None:
        self.config = config.self_healing
        self.notify_config = config.notification
        self._retry_counts: dict[str, int] = {}
        self._last_oom_time: Optional[datetime] = None
        self._consecutive_failures: int = 0

    def classify_error(self, error_message: str) -> ErrorType:
        """Hata mesajını analiz edip tipini belirle."""
        lower_msg = error_message.lower()
        for pattern, error_type in ERROR_PATTERNS.items():
            if pattern in lower_msg:
                logger.info(
                    f"🔍 Hata sınıflandırıldı: '{pattern}' → {error_type.value}"
                )
                return error_type
        logger.warning(f"⚠️ Bilinmeyen hata tipi: {error_message[:200]}")
        return ErrorType.UNKNOWN

    def get_healing_action(self, error_type: ErrorType) -> HealingAction:
        """Hata tipine göre iyileşme aksiyonunu belirle."""
        return HEALING_STRATEGIES.get(error_type, HealingAction.RETRY_WITH_BACKOFF)

    async def heal(
        self,
        error: Exception,
        task_id: str,
        retry_func: Optional[Callable] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Hata iyileşme ana metodu.

        Returns:
            dict: {
                "action": HealingAction,
                "success": bool,
                "message": str,
                "should_retry": bool,
                "wait_seconds": int,
            }
        """
        error_msg = str(error)
        error_type = self.classify_error(error_msg)

        # Exception'dan sınıflandırılamadıysa video-generator container
        # loglarını oku — OOM/FFmpeg gibi hatalar çoğu zaman yalnızca orada
        # görünür, ajana sadece "connection reset" olarak yansır.
        if error_type in (ErrorType.UNKNOWN, ErrorType.NETWORK_ERROR, ErrorType.CONTAINER_DOWN):
            log_error_type = await self._classify_from_container_logs()
            if log_error_type is not None and log_error_type != ErrorType.UNKNOWN:
                logger.info(
                    f"🔍 Container logundan yeniden sınıflandırıldı: "
                    f"{error_type.value} → {log_error_type.value}"
                )
                error_type = log_error_type

        action = self.get_healing_action(error_type)

        # Retry sayacını güncelle
        retry_key = f"{task_id}:{error_type.value}"
        self._retry_counts[retry_key] = self._retry_counts.get(retry_key, 0) + 1
        current_retry = self._retry_counts[retry_key]

        logger.warning(
            f"🩺 Self-Healing aktif | Task: {task_id} | "
            f"Hata: {error_type.value} | Aksiyon: {action.value} | "
            f"Deneme: {current_retry}/{self.config.max_retries}"
        )

        # Max retry aşıldı mı?
        if current_retry > self.config.max_retries:
            logger.error(
                f"🚨 Max retry aşıldı ({self.config.max_retries}) | "
                f"Task: {task_id} | Hata: {error_type.value}"
            )
            self._retry_counts.pop(retry_key, None)
            await self._send_alert(
                f"🚨 CRITICAL: Task {task_id} başarısız!\n"
                f"Hata: {error_type.value}\n"
                f"Mesaj: {error_msg[:500]}\n"
                f"Max retry ({self.config.max_retries}) aşıldı."
            )
            return {
                "action": action,
                "success": False,
                "message": f"Max retry exceeded for {error_type.value}",
                "should_retry": False,
                "wait_seconds": 0,
            }

        # Aksiyon bazlı iyileşme
        result = await self._execute_healing(
            action, error_type, task_id, current_retry, context
        )

        return result

    async def _execute_healing(
        self,
        action: HealingAction,
        error_type: ErrorType,
        task_id: str,
        retry_count: int,
        context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Spesifik iyileşme aksiyonunu çalıştır."""

        if action == HealingAction.COOLDOWN:
            # OOM — ciddi sorun, uzun bekleme
            wait_secs = self.config.oom_cooldown_seconds
            self._last_oom_time = datetime.now()
            logger.warning(
                f"⏸️ OOM Cooldown: {wait_secs}s bekleniyor | Task: {task_id}"
            )
            await self._send_alert(
                f"⚠️ OOM algılandı! {wait_secs}s cooldown. Task: {task_id}"
            )
            return {
                "action": action,
                "success": True,
                "message": f"OOM cooldown: {wait_secs}s",
                "should_retry": True,
                "wait_seconds": wait_secs,
            }

        elif action == HealingAction.RETRY_WITH_BACKOFF:
            # Exponential backoff hesapla
            wait_secs = min(
                self.config.initial_backoff_seconds * (2 ** (retry_count - 1)),
                self.config.max_backoff_seconds,
            )
            logger.info(
                f"🔄 Backoff retry: {wait_secs}s sonra | "
                f"Task: {task_id} | Deneme: {retry_count}"
            )
            return {
                "action": action,
                "success": True,
                "message": f"Retry with {wait_secs}s backoff",
                "should_retry": True,
                "wait_seconds": wait_secs,
            }

        elif action == HealingAction.WAIT_AND_RETRY:
            # Container/network sorunu — sabit bekleme
            wait_secs = 60 * retry_count  # Her denemede 1 dk artan bekleme
            logger.info(
                f"⏳ Container/network sorunu: {wait_secs}s bekleniyor | "
                f"Task: {task_id}"
            )
            return {
                "action": action,
                "success": True,
                "message": f"Wait {wait_secs}s for recovery",
                "should_retry": True,
                "wait_seconds": wait_secs,
            }

        elif action == HealingAction.MODIFY_PARAMS:
            # FFmpeg crash — parametreleri değiştir
            logger.info(
                f"🔧 FFmpeg crash: parametreler değiştirilecek | Task: {task_id}"
            )
            modified_context = self._suggest_param_changes(context or {})
            return {
                "action": action,
                "success": True,
                "message": "Parameters modified for retry",
                "should_retry": True,
                "wait_seconds": 10,
                "modified_params": modified_context,
            }

        elif action == HealingAction.SKIP_AND_ALERT:
            # Kurtarılamaz hata — atla ve bildir
            logger.error(
                f"🛑 Kurtarılamaz hata: {error_type.value} | Task: {task_id}"
            )
            await self._send_alert(
                f"🛑 Kurtarılamaz hata!\n"
                f"Tip: {error_type.value}\n"
                f"Task: {task_id}\n"
                f"Lütfen API key/config ayarlarını kontrol edin."
            )
            return {
                "action": action,
                "success": False,
                "message": f"Unrecoverable error: {error_type.value}",
                "should_retry": False,
                "wait_seconds": 0,
            }

        # Fallback
        return {
            "action": action,
            "success": True,
            "message": "Default retry",
            "should_retry": True,
            "wait_seconds": self.config.initial_backoff_seconds,
        }

    def _suggest_param_changes(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        FFmpeg crash durumunda alternatif parametreler öner.

        Orchestrator video parametrelerini ``{"params": {...}}`` altında
        sarmalar; dönüş değeri aynı şekilde anahtarlanır ki çağıran taraf
        doğrudan ``kwargs.update(...)`` ile birleştirebilsin.
        """
        if isinstance(context.get("params"), dict):
            modified_params = dict(context["params"])
            self._tweak_video_params(modified_params)
            logger.info(f"🔧 Değiştirilen video parametreleri: {modified_params}")
            return {"params": modified_params}

        # Fallback: context doğrudan video parametre sözlüğü
        modified = dict(context)
        self._tweak_video_params(modified)
        logger.info(f"🔧 Değiştirilen parametreler: {modified}")
        return modified

    @staticmethod
    def _tweak_video_params(params: dict[str, Any]) -> None:
        """Render yükünü azaltacak şekilde video parametrelerini yerinde değiştir."""
        # Video klip süresini düşür
        if "video_clip_duration" in params:
            params["video_clip_duration"] = max(
                3, params["video_clip_duration"] - 1
            )

        # Video sayısını 1'e düşür
        params["video_count"] = 1

        # Transition'ı kapat (render yükünü azalt)
        params["video_transition_mode"] = None

    def reset_retry_count(self, task_id: str) -> None:
        """Başarılı task sonrası retry sayacını sıfırla."""
        keys_to_remove = [k for k in self._retry_counts if k.startswith(task_id)]
        for key in keys_to_remove:
            self._retry_counts.pop(key, None)
        self._consecutive_failures = 0
        logger.debug(f"✅ Retry sayacı sıfırlandı: {task_id}")

    def is_in_oom_cooldown(self) -> bool:
        """OOM cooldown süresi aktif mi?"""
        if self._last_oom_time is None:
            return False
        elapsed = (datetime.now() - self._last_oom_time).total_seconds()
        return elapsed < self.config.oom_cooldown_seconds

    async def _classify_from_container_logs(self) -> Optional[ErrorType]:
        """
        Hedef container'ın son loglarını oku ve hata tipini sınıflandır.

        Docker SDK çağrıları bloke edicidir → ``asyncio.to_thread`` ile
        çalıştırılır. Socket erişilemezse sessizce ``None`` döner.
        """
        try:
            logs = await asyncio.to_thread(self._read_container_logs)
        except Exception as e:
            logger.debug(f"🐳 Container logları okunamadı: {e}")
            return None

        if not logs:
            return None

        error_type = self.classify_error(logs)
        return error_type if error_type != ErrorType.UNKNOWN else None

    def _read_container_logs(self) -> str:
        """Hedef container'ın son N satır logunu (senkron) oku."""
        import docker  # lazy import — docker SDK opsiyonel

        client = docker.from_env()
        try:
            container = client.containers.get(self.config.target_container_name)
            raw = container.logs(tail=self.config.docker_log_tail_lines)
            return raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw)
        finally:
            client.close()

    async def _send_alert(self, message: str) -> None:
        """Telegram bildirimi gönder (yapılandırılmışsa)."""
        if not self.notify_config.enabled:
            logger.info(f"📢 Alert (bildirim kapalı): {message}")
            return

        if (
            not self.notify_config.telegram_bot_token
            or not self.notify_config.telegram_chat_id
        ):
            logger.warning("⚠️ Telegram token/chat_id eksik, bildirim gönderilemedi")
            return

        try:
            from telegram import Bot

            bot = Bot(token=self.notify_config.telegram_bot_token)
            await bot.send_message(
                chat_id=self.notify_config.telegram_chat_id,
                text=f"🤖 Video Factory Agent\n\n{message}",
                parse_mode="HTML",
            )
            logger.info("📨 Telegram bildirimi gönderildi")
        except Exception as e:
            logger.error(f"❌ Telegram bildirim hatası: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Mevcut self-healing istatistikleri."""
        return {
            "active_retries": dict(self._retry_counts),
            "consecutive_failures": self._consecutive_failures,
            "in_oom_cooldown": self.is_in_oom_cooldown(),
            "last_oom_time": (
                self._last_oom_time.isoformat() if self._last_oom_time else None
            ),
        }
