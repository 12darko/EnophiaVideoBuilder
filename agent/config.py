"""
AI Agent — Configuration Module
================================
Pydantic Settings ile tüm yapılandırma env değişkenlerinden okunur.
Coolify UI'dan veya .env dosyasından ayarlanabilir.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VideoGeneratorSettings(BaseSettings):
    """MoneyPrinterTurbo API bağlantı ayarları."""

    model_config = SettingsConfigDict(env_prefix="VG_")

    # Video generator servisinin Docker internal adresi
    api_base_url: str = "http://video-generator:8080"
    api_timeout: int = 600  # 10 dakika (video render uzun sürebilir)
    health_check_url: str = "http://video-generator:8501/_stcore/health"

    # Varsayılan video parametreleri
    default_aspect: str = "9:16"  # portrait (shorts/reels)
    default_voice: str = "tr-TR-EmelNeural"  # Türkçe TTS
    default_video_source: str = "pexels"
    default_clip_duration: int = 5
    default_video_count: int = 1


class LLMSettings(BaseSettings):
    """LLM (Büyük Dil Modeli) ayarları — içerik üretimi için."""

    model_config = SettingsConfigDict(env_prefix="LLM_")

    provider: str = "gemini"  # gemini, openai, deepseek
    api_key: str = ""
    model_name: str = "gemini-2.0-flash"

    # OpenAI uyumlu alternatif
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model_name: str = "gpt-4o-mini"


class SchedulerSettings(BaseSettings):
    """Zamanlama ayarları — video üretim sıklığı."""

    model_config = SettingsConfigDict(env_prefix="SCHEDULER_")

    # Günlük video üretim sayısı
    daily_video_count: int = 3

    # Video üretim saatleri (UTC+3 Istanbul)
    # Varsayılan: 09:00, 14:00, 19:00
    production_hours: str = "9,14,19"

    # Sosyal medya paylaşım gecikmesi (dakika)
    # Video üretildikten kaç dakika sonra paylaşılsın
    post_delay_minutes: int = 5

    # Minimum aralık (dakika) — iki video arası
    min_interval_minutes: int = 60


class SocialMediaSettings(BaseSettings):
    """Sosyal medya API ayarları."""

    model_config = SettingsConfigDict(env_prefix="SOCIAL_")

    # Aktif platformlar (virgülle ayrılmış)
    enabled_platforms: str = "tiktok,instagram,youtube"

    # Paylaşım stratejisi: "api", "browser", "hybrid"
    publish_strategy: str = "hybrid"

    # ── TikTok ──
    tiktok_session_cookie: str = ""  # browser-use için oturum çerezi

    # ── Instagram ──
    instagram_username: str = ""
    instagram_password: str = ""

    # ── YouTube ──
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_refresh_token: str = ""

    # ── Genel ──
    default_hashtags: str = "#shorts,#viral,#ai,#fyp"
    max_retries_per_platform: int = 3


class SelfHealingSettings(BaseSettings):
    """Kendi kendine iyileşme (self-healing) ayarları."""

    model_config = SettingsConfigDict(env_prefix="HEAL_")

    # Maksimum yeniden deneme sayısı
    max_retries: int = 5

    # İlk bekleme süresi (saniye) — exponential backoff
    initial_backoff_seconds: int = 30

    # Maksimum bekleme süresi (saniye)
    max_backoff_seconds: int = 600  # 10 dakika

    # Docker log satır limiti (son N satır okunur)
    docker_log_tail_lines: int = 100

    # Hata anında logları okunacak hedef container (video-generator)
    target_container_name: str = "moneyprinterturbo"

    # OOM algılandığında bekleme süresi (saniye)
    oom_cooldown_seconds: int = 300  # 5 dakika


class NotificationSettings(BaseSettings):
    """Bildirim ayarları (opsiyonel)."""

    model_config = SettingsConfigDict(env_prefix="NOTIFY_")

    enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


class StorageSettings(BaseSettings):
    """Üretilen video depolama ve temizlik ayarları."""

    model_config = SettingsConfigDict(env_prefix="STORAGE_")

    # Paylaşılan output dizini (video-generator ile ortak volume)
    shared_output_dir: str = "/shared_output"

    # Bu günden eski videoları otomatik sil (0 = kapalı)
    retention_days: int = 7

    # Toplam depolama bu sınırı (GB) aşınca en eski videoları sil (0 = kapalı)
    max_storage_gb: float = 0.0


class ControlPanelSettings(BaseSettings):
    """Web kontrol paneli ayarları."""

    model_config = SettingsConfigDict(env_prefix="PANEL_")

    enabled: bool = True
    port: int = 8090
    # Basic auth — şifre boşsa panel salt-okunur açılır (mutasyon kapalı)
    username: str = "admin"
    password: str = ""


class ContentSettings(BaseSettings):
    """İçerik stratejisi ayarları."""

    model_config = SettingsConfigDict(env_prefix="CONTENT_")

    # İçerik dili
    language: str = "tr"  # tr, en, multi

    # İçerik niche/kategorisi
    niche: str = "motivation"  # motivation, finance, tech, education, travel

    # Konu havuzu (virgülle ayrılmış, boşsa LLM otomatik üretir)
    topic_pool: str = ""

    # Video süresi hedefi (saniye)
    target_duration_seconds: int = 60


class AgentConfig(BaseSettings):
    """Ana konfigürasyon — tüm alt ayarları birleştirir."""

    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Alt konfigürasyonlar
    video_generator: VideoGeneratorSettings = Field(
        default_factory=VideoGeneratorSettings
    )
    llm: LLMSettings = Field(default_factory=LLMSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    social_media: SocialMediaSettings = Field(default_factory=SocialMediaSettings)
    self_healing: SelfHealingSettings = Field(default_factory=SelfHealingSettings)
    notification: NotificationSettings = Field(default_factory=NotificationSettings)
    content: ContentSettings = Field(default_factory=ContentSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    control_panel: ControlPanelSettings = Field(default_factory=ControlPanelSettings)

    # Agent genel ayarları
    heartbeat_interval_seconds: int = 30
    data_dir: str = "/agent/data"
    log_dir: str = "/agent/logs"


# Singleton config instance
config = AgentConfig()
