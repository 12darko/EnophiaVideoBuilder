"""
AI Agent — Content Brain (İçerik Üretim Beyni)
================================================
LLM (Gemini/OpenAI) ile video konusu, senaryo ve
hashtag üretimi. Niche bazlı içerik stratejisi.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
from collections import deque
from typing import Any, Optional

from loguru import logger

from config import AgentConfig

# Tekrarı önlemek için hatırlanacak son konu sayısı
_RECENT_TOPICS_LIMIT = 30


class ContentBrain:
    """
    LLM tabanlı içerik üretim modülü.

    Görevleri:
    - Niche'e uygun video konuları üretmek
    - Video senaryoları yazmak
    - Sosyal medya başlıkları ve hashtag'ler oluşturmak
    """

    def __init__(self, config: AgentConfig) -> None:
        self.llm_config = config.llm
        self.content_config = config.content
        self.social_config = config.social_media
        self._client: Any = None

        # Üretilen son konuları kalıcı tut → tekrarı önle
        self._recent_topics_path = os.path.join(
            config.data_dir, "recent_topics.json"
        )
        self._recent_topics: deque[str] = deque(maxlen=_RECENT_TOPICS_LIMIT)
        self._load_recent_topics()

    def _load_recent_topics(self) -> None:
        """Diskten son konuları yükle (yeniden başlatmaya dayanıklı)."""
        try:
            if os.path.exists(self._recent_topics_path):
                with open(self._recent_topics_path, encoding="utf-8") as f:
                    topics = json.load(f)
                if isinstance(topics, list):
                    self._recent_topics.extend(str(t) for t in topics)
                    logger.debug(
                        f"📚 {len(self._recent_topics)} önceki konu yüklendi"
                    )
        except Exception as e:
            logger.warning(f"⚠️ Son konular yüklenemedi: {e}")

    def _remember_topic(self, topic: str) -> None:
        """Konuyu hafızaya ekle ve diske yaz."""
        self._recent_topics.append(topic)
        try:
            os.makedirs(os.path.dirname(self._recent_topics_path), exist_ok=True)
            with open(self._recent_topics_path, "w", encoding="utf-8") as f:
                json.dump(list(self._recent_topics), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"⚠️ Son konular kaydedilemedi: {e}")

    def _get_client(self) -> Any:
        """LLM client'ını başlat."""
        if self._client is not None:
            return self._client

        if self.llm_config.provider == "gemini":
            import google.generativeai as genai

            genai.configure(api_key=self.llm_config.api_key)
            self._client = genai.GenerativeModel(self.llm_config.model_name)

        elif self.llm_config.provider in ("openai", "deepseek"):
            from openai import OpenAI

            self._client = OpenAI(
                api_key=(
                    self.llm_config.openai_api_key or self.llm_config.api_key
                ),
                base_url=self.llm_config.openai_base_url,
            )

        else:
            raise ValueError(f"Desteklenmeyen LLM provider: {self.llm_config.provider}")

        return self._client

    # ── Konu Üretimi ─────────────────────────────────────────

    async def generate_topic(self) -> str:
        """Niche'e uygun benzersiz bir video konusu üret."""

        # Eğer önceden tanımlı konu havuzu varsa, oradan seç
        if self.content_config.topic_pool:
            topics = [
                t.strip()
                for t in self.content_config.topic_pool.split(",")
                if t.strip()
            ]
            if topics:
                topic = random.choice(topics)
                logger.info(f"📝 Konu havuzundan seçildi: '{topic}'")
                return topic

        # LLM ile üret
        lang_map = {"tr": "Türkçe", "en": "English", "multi": "English"}
        lang = lang_map.get(self.content_config.language, "Türkçe")

        niche_descriptions = {
            "motivation": "motivasyon, kişisel gelişim, başarı hikayeleri",
            "finance": "finans, yatırım, para yönetimi, kripto",
            "tech": "teknoloji, yapay zeka, yazılım, inovasyon",
            "education": "eğitim, bilim, ilginç bilgiler, tarih",
            "travel": "seyahat, keşfet, dünya kültürleri",
            "health": "sağlık, fitness, beslenme",
            "comedy": "komedi, eğlence, günlük hayat",
        }
        niche_desc = niche_descriptions.get(
            self.content_config.niche, self.content_config.niche
        )

        # Son üretilen konuları prompt'a ekle → tekrarı engelle
        avoid_block = ""
        if self._recent_topics:
            recent_list = "\n".join(f"- {t}" for t in self._recent_topics)
            avoid_block = (
                "\nAşağıdaki konular YAKIN ZAMANDA kullanıldı, "
                "bunlardan FARKLI ve yeni bir konu üret:\n"
                f"{recent_list}\n"
            )

        prompt = f"""Sen bir viral video içerik uzmanısın.
{lang} dilinde, "{niche_desc}" niche'inde kısa video (60 saniye) için
ilgi çekici, viral potansiyeli yüksek BİR adet video konusu öner.
{avoid_block}
Kurallar:
- Konu net ve spesifik olmalı (genel değil)
- İnsanların durup izlemek isteyeceği ilginç bir konu seç
- Sadece konu başlığını yaz, başka bir şey yazma
- Emoji kullanma

Konu:"""

        topic = await self._call_llm(prompt)
        topic = topic.strip().strip('"').strip("'")
        self._remember_topic(topic)
        logger.info(f"📝 LLM konu üretti: '{topic}'")
        return topic

    # ── Senaryo Üretimi ──────────────────────────────────────

    async def generate_script(self, topic: str) -> str:
        """Video konusuna uygun senaryo üret."""

        lang_map = {"tr": "Türkçe", "en": "English", "multi": "English"}
        lang = lang_map.get(self.content_config.language, "Türkçe")
        duration = self.content_config.target_duration_seconds

        prompt = f"""Sen profesyonel bir kısa video senaryo yazarısın.
"{topic}" konusunda {lang} dilinde yaklaşık {duration} saniyelik bir 
kısa video senaryosu yaz.

Kurallar:
- Anlatıcı (voiceover) formatında yaz
- İlk 3 saniyede dikkat çekici bir hook ile başla
- Kısa, net cümleler kullan
- Merak uyandıran bilgiler ekle
- Sonunda güçlü bir kapanış yap
- Sadece senaryoyu yaz, yönerge/açıklama ekleme
- {duration} saniyede okunabilecek uzunlukta olmalı (yaklaşık {duration * 2} kelime)

Senaryo:"""

        script = await self._call_llm(prompt)
        script = script.strip()
        logger.info(
            f"📜 Senaryo üretildi: {len(script)} karakter | Konu: '{topic[:40]}...'"
        )
        return script

    # ── Sosyal Medya Metadata ────────────────────────────────

    async def generate_social_metadata(
        self, topic: str, platform: str = "general"
    ) -> dict[str, str]:
        """Sosyal medya başlığı, açıklaması ve hashtag'leri üret."""

        lang_map = {"tr": "Türkçe", "en": "English", "multi": "English"}
        lang = lang_map.get(self.content_config.language, "Türkçe")

        prompt = f"""Sen bir sosyal medya uzmanısın. 
"{topic}" konusundaki kısa video için {lang} dilinde sosyal medya paylaşım metni hazırla.
Platform: {platform}

Aşağıdaki JSON formatında yanıt ver (başka hiçbir şey yazma):
{{
    "title": "Video başlığı (kısa, dikkat çekici, max 100 karakter)",
    "description": "Video açıklaması (2-3 cümle, merak uyandırıcı)",
    "hashtags": "#hashtag1 #hashtag2 #hashtag3 #hashtag4 #hashtag5"
}}"""

        response = await self._call_llm(prompt)

        try:
            # JSON parse et
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            metadata = json.loads(response)
        except (json.JSONDecodeError, IndexError):
            logger.warning("⚠️ LLM JSON parse hatası, fallback metadata kullanılıyor")
            # Yapılandırılmış varsayılan hashtag'ler (virgülleri boşluğa çevir)
            fallback_tags = " ".join(
                t.strip()
                for t in self.social_config.default_hashtags.split(",")
                if t.strip()
            )
            metadata = {
                "title": topic[:100],
                "description": topic,
                "hashtags": fallback_tags or f"#{self.content_config.niche} #shorts #viral",
            }

        logger.info(f"🏷️ Sosyal medya metadata üretildi: {metadata.get('title', '')}")
        return metadata

    # ── LLM Çağrısı (Internal) ───────────────────────────────

    async def _call_llm(self, prompt: str) -> str:
        """
        LLM'e prompt gönder ve yanıt al.

        Gemini/OpenAI SDK çağrıları senkron (bloke edici) olduğundan
        ``asyncio.to_thread`` ile ayrı bir thread'de çalıştırılır;
        böylece event loop (ve heartbeat) bloke olmaz.
        """
        client = self._get_client()

        def _sync_call() -> str:
            if self.llm_config.provider == "gemini":
                response = client.generate_content(prompt)
                return response.text

            elif self.llm_config.provider in ("openai", "deepseek"):
                model = (
                    self.llm_config.openai_model_name or self.llm_config.model_name
                )
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.8,
                    max_tokens=1000,
                )
                return response.choices[0].message.content or ""

            raise ValueError(
                f"Desteklenmeyen provider: {self.llm_config.provider}"
            )

        try:
            return await asyncio.to_thread(_sync_call)
        except Exception as e:
            logger.error(f"❌ LLM çağrı hatası: {e}")
            raise
