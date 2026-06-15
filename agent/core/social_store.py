"""
AI Agent — Social Accounts Store
=================================
Sosyal medya hesap bilgileri UI'dan girilir ve burada (JSON) saklanır.
Publisher'lar yayın anında buradan okur (env üzerine yazar).
Böylece kullanıcı Instagram/YouTube/TikTok hesaplarını panelden girer.
"""

from __future__ import annotations

import json
import os
from typing import Any

from loguru import logger

# UI'dan kabul edilen alanlar
FIELDS = [
    "instagram_username",
    "instagram_password",
    "youtube_client_id",
    "youtube_client_secret",
    "youtube_refresh_token",
    "tiktok_session_cookie",
    "enabled_platforms",  # list[str]
]

_SECRET_FIELDS = {
    "instagram_password",
    "youtube_client_secret",
    "youtube_refresh_token",
    "tiktok_session_cookie",
}


class SocialStore:
    """Sosyal hesap bilgilerini saklar; env + kayıt birleşik döndürür."""

    def __init__(self, config: Any) -> None:
        self._config = config
        self.path = os.path.join(config.data_dir, "social_accounts.json")

    def load(self) -> dict[str, Any]:
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"⚠️ Sosyal hesap kaydı okunamadı: {e}")
        return {}

    def save(self, data: dict[str, Any]) -> dict[str, Any]:
        """UI'dan gelen veriyi kaydet (sadece tanımlı alanlar, boşları atla)."""
        current = self.load()
        for k in FIELDS:
            if k not in data:
                continue
            v = data[k]
            if k == "enabled_platforms":
                if isinstance(v, list):
                    current[k] = [str(x).strip().lower() for x in v if str(x).strip()]
            else:
                # Boş gönderilen sırrı silme — eskisini koru (maskeli geldiyse)
                if v == "" or (isinstance(v, str) and set(v) <= {"•"}):
                    continue
                current[k] = v
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        logger.info("💾 Sosyal hesap ayarları kaydedildi")
        return current

    def effective(self) -> dict[str, Any]:
        """Env varsayılanları + kayıtlı override'lar birleşik."""
        sm = self._config.social_media
        eff: dict[str, Any] = {
            "instagram_username": sm.instagram_username,
            "instagram_password": sm.instagram_password,
            "youtube_client_id": sm.youtube_client_id,
            "youtube_client_secret": sm.youtube_client_secret,
            "youtube_refresh_token": sm.youtube_refresh_token,
            "tiktok_session_cookie": sm.tiktok_session_cookie,
            "enabled_platforms": [
                p.strip().lower()
                for p in sm.enabled_platforms.split(",")
                if p.strip()
            ],
        }
        for k, v in self.load().items():
            if v not in (None, "", []):
                eff[k] = v
        return eff

    def masked(self) -> dict[str, Any]:
        """GET için — sırları maskele (UI'da gösterim)."""
        eff = self.effective()
        out: dict[str, Any] = {}
        for k, v in eff.items():
            if k in _SECRET_FIELDS and v:
                out[k] = "••••••" + (str(v)[-2:] if len(str(v)) > 2 else "")
            else:
                out[k] = v
        return out
