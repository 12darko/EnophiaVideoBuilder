"""
AI Agent — Storage Manager (Depolama Yöneticisi)
==================================================
Üretilen videoları listeler, siler ve otomatik temizlik
(retention + boyut limiti) uygular. shared_output volume'ünü yönetir.
"""

from __future__ import annotations

import os
import shutil
import time
from typing import Any

from loguru import logger

from config import AgentConfig

_VIDEO_EXTS = (".mp4", ".mov", ".webm")


class StorageManager:
    """shared_output volume'ündeki üretilmiş videoları yönetir."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config.storage
        self.base = self.config.shared_output_dir

    # ── Listeleme ────────────────────────────────────────────

    def list_videos(self) -> list[dict[str, Any]]:
        """
        Üretilen videoları task bazında listele.

        shared_output altındaki her alt dizin bir task kabul edilir.
        Returns: [{task_id, size_bytes, size_mb, modified, files:[...]}]
        """
        items: list[dict[str, Any]] = []
        if not os.path.isdir(self.base):
            return items

        for entry in os.scandir(self.base):
            if not entry.is_dir():
                continue
            files: list[str] = []
            total = 0
            latest = 0.0
            for root, _dirs, names in os.walk(entry.path):
                for n in names:
                    if n.lower().endswith(_VIDEO_EXTS):
                        fp = os.path.join(root, n)
                        try:
                            st = os.stat(fp)
                        except OSError:
                            continue
                        files.append(os.path.relpath(fp, entry.path))
                        total += st.st_size
                        latest = max(latest, st.st_mtime)
            if not files:
                continue
            items.append(
                {
                    "task_id": entry.name,
                    "size_bytes": total,
                    "size_mb": round(total / (1024 * 1024), 2),
                    "modified": time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(latest)
                    ),
                    "modified_ts": latest,
                    "files": files,
                }
            )

        items.sort(key=lambda x: x["modified_ts"], reverse=True)
        return items

    def total_size_bytes(self) -> int:
        """shared_output toplam boyutu (byte)."""
        total = 0
        if not os.path.isdir(self.base):
            return 0
        for root, _dirs, names in os.walk(self.base):
            for n in names:
                try:
                    total += os.path.getsize(os.path.join(root, n))
                except OSError:
                    pass
        return total

    # ── Silme ────────────────────────────────────────────────

    def delete_video(self, task_id: str) -> bool:
        """Bir task'ın tüm çıktısını sil (rw erişim gerekir)."""
        # Path traversal koruması
        safe = os.path.basename(task_id.strip("/\\"))
        if not safe or safe in (".", ".."):
            logger.warning(f"⚠️ Geçersiz task_id silme isteği: {task_id!r}")
            return False

        target = os.path.join(self.base, safe)
        if not os.path.isdir(target):
            logger.warning(f"⚠️ Silinecek video bulunamadı: {target}")
            return False

        try:
            shutil.rmtree(target)
            logger.info(f"🗑️ Video silindi: {safe}")
            return True
        except Exception as e:
            logger.error(f"❌ Video silinemedi ({safe}): {e}")
            return False

    # ── Otomatik Temizlik ────────────────────────────────────

    def cleanup(self) -> dict[str, Any]:
        """
        retention_days + max_storage_gb politikalarını uygula.
        Returns: {deleted: int, freed_mb: float}
        """
        deleted = 0
        freed = 0

        # 1) Yaş bazlı temizlik
        retention = self.config.retention_days
        if retention > 0:
            cutoff = time.time() - retention * 86400
            for v in self.list_videos():
                if v["modified_ts"] < cutoff and self.delete_video(v["task_id"]):
                    deleted += 1
                    freed += v["size_bytes"]

        # 2) Boyut bazlı temizlik (güncel diske göre, en eskiden başla)
        max_bytes = int(self.config.max_storage_gb * 1024**3)
        if max_bytes > 0:
            total = self.total_size_bytes()
            remaining = sorted(self.list_videos(), key=lambda x: x["modified_ts"])
            for v in remaining:
                if total <= max_bytes:
                    break
                if self.delete_video(v["task_id"]):
                    deleted += 1
                    freed += v["size_bytes"]
                    total -= v["size_bytes"]

        if deleted:
            logger.info(
                f"🧹 Depolama temizliği: {deleted} video silindi, "
                f"{round(freed / (1024*1024), 1)} MB boşaltıldı"
            )
        return {"deleted": deleted, "freed_mb": round(freed / (1024 * 1024), 2)}
