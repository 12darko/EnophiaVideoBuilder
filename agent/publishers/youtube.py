"""
AI Agent — YouTube Publisher
==============================
YouTube Shorts'a video paylaşımı.
Strateji: YouTube Data API v3 (resmi API — en güvenli yol).
"""

from __future__ import annotations

import os
from typing import Any, Optional

from loguru import logger

from publishers.base import BasePublisher, PublishResult, PublishStatus, VideoPost


class YouTubePublisher(BasePublisher):
    """
    YouTube Shorts video paylaşımcısı.

    Resmi YouTube Data API v3 kullanır.
    OAuth2 refresh token ile kimlik doğrulama.
    """

    platform_name = "youtube"
    publish_method = "api"

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.client_id = config.social_media.youtube_client_id
        self.client_secret = config.social_media.youtube_client_secret
        self.refresh_token = config.social_media.youtube_refresh_token
        self._youtube_service: Any = None

    async def is_available(self) -> bool:
        """YouTube publisher'ın kullanılabilirliğini kontrol et."""
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            logger.debug(
                "YouTube: Client ID/Secret/Refresh token eksik, atlanıyor"
            )
            return False
        return True

    async def authenticate(self) -> bool:
        """YouTube OAuth2 kimlik doğrulama."""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            credentials = Credentials(
                token=None,
                refresh_token=self.refresh_token,
                client_id=self.client_id,
                client_secret=self.client_secret,
                token_uri="https://oauth2.googleapis.com/token",
            )

            # Token'ı yenile
            credentials.refresh(Request())

            self._youtube_service = build(
                "youtube", "v3", credentials=credentials
            )

            logger.info("🔐 YouTube: OAuth2 kimlik doğrulama başarılı")
            return True

        except Exception as e:
            logger.error(f"❌ YouTube OAuth2 hatası: {e}")
            return False

    async def publish(self, post: VideoPost) -> PublishResult:
        """YouTube Shorts'a video paylaş."""
        try:
            return await self._publish_via_api(post)
        except Exception as e:
            logger.error(f"❌ YouTube API publish hatası: {e}")
            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.FAILED,
                message=str(e),
            )

    async def _publish_via_api(self, post: VideoPost) -> PublishResult:
        """YouTube Data API v3 ile video yükle."""
        try:
            from googleapiclient.http import MediaFileUpload

            if not os.path.exists(post.video_path):
                return PublishResult(
                    platform=self.platform_name,
                    status=PublishStatus.FAILED,
                    message=f"Video dosyası bulunamadı: {post.video_path}",
                )

            if not self._youtube_service:
                return PublishResult(
                    platform=self.platform_name,
                    status=PublishStatus.AUTH_ERROR,
                    message="YouTube service not initialized",
                )

            # Video başlığına #Shorts ekle (YouTube Shorts algılaması için)
            title = post.title
            if "#shorts" not in title.lower():
                title = f"{title} #Shorts"

            # Açıklama oluştur
            description = f"{post.description}\n\n{post.hashtags}"

            # YouTube geçerli BCP-47 dil kodu ister; "multi" gibi değerler
            # API hatası verir, bu yüzden bilinmeyen kodlar atlanır.
            snippet: dict[str, Any] = {
                "title": title[:100],  # YouTube max 100 char
                "description": description[:5000],  # YouTube max 5000 char
                "tags": [
                    tag.strip().lstrip("#")
                    for tag in post.hashtags.split()
                    if tag.startswith("#")
                ][:30],  # Max 30 tags
                "categoryId": "22",  # People & Blogs
            }
            valid_lang = {"tr": "tr", "en": "en"}.get(post.language)
            if valid_lang:
                snippet["defaultLanguage"] = valid_lang
                snippet["defaultAudioLanguage"] = valid_lang

            # Video metadata
            body = {
                "snippet": snippet,
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False,
                    "embeddable": True,
                },
            }

            # Video dosyasını hazırla
            media = MediaFileUpload(
                post.video_path,
                mimetype="video/mp4",
                resumable=True,
                chunksize=256 * 1024,  # 256KB chunks
            )

            # Upload isteği oluştur
            request = self._youtube_service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            # Resumable upload
            logger.info("📤 YouTube: Video yükleniyor...")
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.debug(f"📤 YouTube upload: {progress}%")

            video_id = response.get("id", "")
            video_url = f"https://youtube.com/shorts/{video_id}"

            logger.info(f"✅ YouTube: Video yüklendi! {video_url}")

            return PublishResult(
                platform=self.platform_name,
                status=PublishStatus.SUCCESS,
                post_url=video_url,
                message=f"Video uploaded: {video_id}",
                metadata={
                    "video_id": video_id,
                    "method": "youtube_data_api_v3",
                },
            )

        except Exception as e:
            error_msg = str(e)
            if "quotaExceeded" in error_msg or "rateLimitExceeded" in error_msg:
                return PublishResult(
                    platform=self.platform_name,
                    status=PublishStatus.RATE_LIMITED,
                    message=f"YouTube API quota aşıldı: {error_msg}",
                )
            raise
