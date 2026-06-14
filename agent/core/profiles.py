"""
AI Agent — Profiles (Çoklu Kanal / Multi-Tenant Faz 1)
========================================================
Her profil bir "kanal" gibidir: kendi niche, dil, hedef platform,
hashtag ve konu havuzu. Panelden yönetilir, üretim profile göre yapılır.

Faz 1: içerik-seviyesi profiller (sosyal hesaplar şimdilik ortak/env).
Faz 2: profil başına zamanlama. Faz 3: çoklu kullanıcı + hesap.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from loguru import logger

from config import AgentConfig


@dataclass
class Profile:
    """Bir içerik profili / kanal."""

    id: str
    name: str
    niche: str = "motivation"
    language: str = "tr"
    target_duration: int = 60
    # Boş liste = ortak (env) varsayılan platformlar kullanılır
    enabled_platforms: list[str] = field(default_factory=list)
    hashtags: str = ""
    topic_pool: str = ""
    enabled: bool = True

    @staticmethod
    def new(name: str, **kw: Any) -> "Profile":
        # Yalnızca tanımlı alanları al; id ve name ayrıca veriliyor
        allowed = {
            k: v
            for k, v in kw.items()
            if k in Profile.__dataclass_fields__ and k not in ("id", "name")
        }
        return Profile(id=uuid.uuid4().hex[:8], name=name, **allowed)


class ProfileStore:
    """Profilleri JSON dosyasında saklayan basit CRUD deposu."""

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self.path = os.path.join(config.data_dir, "profiles.json")
        self._profiles: dict[str, Profile] = {}
        self._load()

    # ── Kalıcılık ────────────────────────────────────────────

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                p = Profile(**{k: item[k] for k in item if k in Profile.__dataclass_fields__})
                self._profiles[p.id] = p
            logger.info(f"📚 {len(self._profiles)} profil yüklendi")
        except Exception as e:
            logger.error(f"❌ Profiller yüklenemedi: {e}")

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump([asdict(p) for p in self._profiles.values()], f,
                          ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ Profiller kaydedilemedi: {e}")

    # ── Varsayılan profil (geri uyumluluk) ───────────────────

    def ensure_default(self) -> Profile:
        """Hiç profil yoksa env ayarlarından bir 'Varsayılan' profil üret."""
        existing = next(
            (p for p in self._profiles.values() if p.id == "default"), None
        )
        if existing:
            return existing

        c = self._config
        platforms = [
            p.strip().lower()
            for p in c.social_media.enabled_platforms.split(",")
            if p.strip()
        ]
        default = Profile(
            id="default",
            name="Varsayılan",
            niche=c.content.niche,
            language=c.content.language,
            target_duration=c.content.target_duration_seconds,
            enabled_platforms=platforms,
            hashtags=c.social_media.default_hashtags,
            topic_pool=c.content.topic_pool,
            enabled=True,
        )
        self._profiles[default.id] = default
        self._save()
        logger.info("📒 Varsayılan profil oluşturuldu (env ayarlarından)")
        return default

    # ── CRUD ─────────────────────────────────────────────────

    def list(self) -> list[Profile]:
        return list(self._profiles.values())

    def get(self, profile_id: str) -> Optional[Profile]:
        return self._profiles.get(profile_id)

    def create(self, data: dict[str, Any]) -> Profile:
        name = (data.get("name") or "").strip() or "İsimsiz"
        rest = {k: v for k, v in data.items() if k != "name"}
        profile = Profile.new(name, **rest)
        self._profiles[profile.id] = profile
        self._save()
        logger.info(f"➕ Profil oluşturuldu: {profile.name} ({profile.id})")
        return profile

    def update(self, profile_id: str, data: dict[str, Any]) -> Optional[Profile]:
        p = self._profiles.get(profile_id)
        if not p:
            return None
        for k, v in data.items():
            if k in Profile.__dataclass_fields__ and k != "id":
                setattr(p, k, v)
        self._save()
        logger.info(f"✏️ Profil güncellendi: {p.name} ({p.id})")
        return p

    def delete(self, profile_id: str) -> bool:
        if profile_id == "default":
            logger.warning("⚠️ Varsayılan profil silinemez")
            return False
        if profile_id in self._profiles:
            del self._profiles[profile_id]
            self._save()
            logger.info(f"🗑️ Profil silindi: {profile_id}")
            return True
        return False
