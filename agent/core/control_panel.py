"""
AI Agent — Control Panel (Basit Yönetim Paneli)
================================================
Amaç (kullanıcı isteği):
  1) Sosyal hesapları gir (Instagram / YouTube / TikTok) ve
     videoların hangi platformlara otomatik gideceğini seç.
  2) Üretilen videoları listele ve gerek kalmayanları sil.

MoneyPrinterTurbo arayüzü AYRIDIR ve bu panel ona dokunmaz.
Scheduler ile aynı event loop'ta uvicorn olarak çalışır.
Basic Auth ile korunur (şifre yoksa salt-okunur mod).
"""

from __future__ import annotations

import asyncio
import os
import secrets
from typing import Any, Optional

from loguru import logger

from config import AgentConfig
from core.storage_manager import StorageManager


def create_app(orchestrator: Any, config: AgentConfig) -> Any:
    """FastAPI uygulamasını oluştur."""
    from fastapi import Depends, FastAPI, HTTPException, status
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.security import HTTPBasic, HTTPBasicCredentials

    panel_cfg = config.control_panel
    storage = StorageManager(config)
    security = HTTPBasic(auto_error=False)

    app = FastAPI(title="Video Factory — Kontrol Paneli", docs_url=None, redoc_url=None)

    def require_auth(
        credentials: Optional[HTTPBasicCredentials] = Depends(security),
    ) -> bool:
        """Mutasyon endpoint'leri için basic auth zorunlu."""
        if not panel_cfg.password:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Panel salt-okunur: PANEL_PASSWORD ayarlanmamış",
            )
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Kimlik doğrulama gerekli",
                headers={"WWW-Authenticate": "Basic"},
            )
        user_ok = secrets.compare_digest(credentials.username, panel_cfg.username)
        pass_ok = secrets.compare_digest(credentials.password, panel_cfg.password)
        if not (user_ok and pass_ok):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Geçersiz kimlik bilgileri",
                headers={"WWW-Authenticate": "Basic"},
            )
        return True

    # ── Sağlık ───────────────────────────────────────────────
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # ── Sosyal hesaplar (oku) ────────────────────────────────
    @app.get("/api/social")
    async def get_social() -> dict[str, Any]:
        data = orchestrator.social_publisher.store.masked()
        data["read_only"] = not bool(panel_cfg.password)
        return data

    # ── Sosyal hesaplar (kaydet) ─────────────────────────────
    @app.post("/api/social")
    async def save_social(
        payload: dict[str, Any], _: bool = Depends(require_auth)
    ) -> dict[str, Any]:
        store = orchestrator.social_publisher.store
        await asyncio.to_thread(store.save, payload)
        # Publisher'ları yeni bilgilerle yeniden kur
        orchestrator.social_publisher.refresh()
        active = orchestrator.social_publisher.get_active_platforms()
        logger.info(f"💾 Sosyal hesaplar güncellendi → aktif: {active or 'Yok'}")
        return {"saved": True, "active_platforms": active}

    # ── Videolar ─────────────────────────────────────────────
    @app.get("/api/videos")
    async def list_videos() -> list[dict[str, Any]]:
        return await asyncio.to_thread(storage.list_videos)

    @app.get("/api/videos/{task_id}/file")
    async def get_video_file(task_id: str) -> Any:
        videos = await asyncio.to_thread(storage.list_videos)
        item = next((v for v in videos if v["task_id"] == task_id), None)
        if not item or not item["files"]:
            raise HTTPException(status_code=404, detail="Video bulunamadı")
        path = os.path.join(storage.base, task_id, item["files"][0])
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="Dosya bulunamadı")
        return FileResponse(path, media_type="video/mp4")

    @app.delete("/api/videos/{task_id}")
    async def delete_video(
        task_id: str, _: bool = Depends(require_auth)
    ) -> dict[str, Any]:
        ok = await asyncio.to_thread(storage.delete_video, task_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Silinemedi veya bulunamadı")
        return {"deleted": task_id}

    # ── Dashboard (HTML) ─────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> str:
        return _DASHBOARD_HTML

    return app


async def run_panel(orchestrator: Any, config: AgentConfig) -> None:
    """Paneli uvicorn ile başlat (event loop içinde)."""
    if not config.control_panel.enabled:
        logger.info("🌐 Kontrol paneli devre dışı (PANEL_ENABLED=false)")
        return
    try:
        import uvicorn
    except ImportError:
        logger.warning("⚠️ uvicorn/fastapi kurulu değil, panel başlatılamadı")
        return

    try:
        app = create_app(orchestrator, config)
    except Exception as e:
        logger.error(f"❌ Kontrol paneli oluşturulamadı: {e!r}")
        return

    port = config.control_panel.port
    auth_note = (
        "🔒 auth aktif" if config.control_panel.password
        else "⚠️ salt-okunur (PANEL_PASSWORD yok)"
    )
    logger.info(f"🌐 Kontrol paneli başlıyor → http://0.0.0.0:{port} ({auth_note})")

    server = uvicorn.Server(
        uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    )
    try:
        await server.serve()
    except Exception as e:
        logger.error(f"❌ Kontrol paneli sunucusu durdu: {e!r}")


_DASHBOARD_HTML = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Video Fabrikası — Hesaplar & Videolar</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}
 header{background:#1e293b;padding:16px 24px;font-size:20px;font-weight:600}
 main{padding:24px;max-width:880px;margin:0 auto}
 .card{background:#1e293b;border-radius:12px;padding:20px;margin-bottom:20px}
 h3{margin-top:0}
 label{display:block;margin:10px 0 4px;font-size:13px;color:#cbd5e1}
 input[type=text],input[type=password]{background:#334155;border:1px solid #475569;color:#fff;border-radius:8px;padding:10px;width:100%;box-sizing:border-box}
 .row{display:flex;gap:16px;flex-wrap:wrap}
 .row>div{flex:1;min-width:220px}
 .platforms{display:flex;gap:18px;margin:8px 0 4px}
 .platforms label{display:flex;align-items:center;gap:6px;margin:0;font-size:14px}
 button{background:#6366f1;color:#fff;border:0;border-radius:8px;padding:10px 18px;cursor:pointer;font-size:14px}
 button.danger{background:#ef4444}
 table{width:100%;border-collapse:collapse;margin-top:8px}
 td,th{text-align:left;padding:8px;border-bottom:1px solid #334155;font-size:14px}
 .muted{color:#94a3b8;font-size:13px}
 .ro{background:#7f1d1d;color:#fecaca;padding:8px 12px;border-radius:8px;font-size:13px;margin-bottom:12px;display:none}
 fieldset{border:1px solid #334155;border-radius:8px;margin:14px 0;padding:12px 14px}
 legend{padding:0 6px;color:#a5b4fc;font-size:13px}
</style></head><body>
<header>🎯 Video Fabrikası — Hesaplar & Videolar</header>
<main>
 <div class="card">
   <div id="ro" class="ro">⚠️ Salt-okunur mod: PANEL_PASSWORD ayarlanmadığı için kaydetme kapalı.</div>
   <h3>📲 Sosyal Hesaplar</h3>
   <p class="muted">Videolar hangi platformlara otomatik yüklensin? İşaretle ve hesap bilgilerini gir.</p>
   <div class="platforms">
     <label><input type="checkbox" id="p_youtube"> YouTube</label>
     <label><input type="checkbox" id="p_instagram"> Instagram</label>
     <label><input type="checkbox" id="p_tiktok"> TikTok</label>
   </div>

   <fieldset><legend>YouTube</legend>
     <div class="row">
       <div><label>Client ID</label><input type="text" id="youtube_client_id" placeholder="xxxxx.apps.googleusercontent.com"></div>
       <div><label>Client Secret</label><input type="password" id="youtube_client_secret" placeholder="••••••"></div>
     </div>
     <label>Refresh Token</label><input type="password" id="youtube_refresh_token" placeholder="••••••">
   </fieldset>

   <fieldset><legend>Instagram</legend>
     <div class="row">
       <div><label>Kullanıcı adı</label><input type="text" id="instagram_username" placeholder="kullanici_adi"></div>
       <div><label>Şifre</label><input type="password" id="instagram_password" placeholder="••••••"></div>
     </div>
   </fieldset>

   <fieldset><legend>TikTok</legend>
     <label>Session Cookie</label><input type="password" id="tiktok_session_cookie" placeholder="sessionid=••••••">
   </fieldset>

   <br>
   <button id="saveBtn" onclick="saveSocial()">💾 Kaydet</button>
   <span id="msg" class="muted"></span>
 </div>

 <div class="card">
   <h3>📦 Üretilen Videolar</h3>
   <p class="muted">Yer kaplayan videoları buradan silebilirsin.</p>
   <table id="videos"><thead><tr><th>Task</th><th>Boyut</th><th>Tarih</th><th></th></tr></thead><tbody></tbody></table>
 </div>
</main>
<script>
const SECRET_IDS=['instagram_password','youtube_client_secret','youtube_refresh_token','tiktok_session_cookie'];
let readOnly=false;

async function loadSocial(){
 const d=await (await fetch('./api/social')).json();
 readOnly=!!d.read_only;
 document.getElementById('ro').style.display=readOnly?'block':'none';
 document.getElementById('saveBtn').disabled=readOnly;
 const set=(id)=>{const el=document.getElementById(id);if(el&&d[id]!=null)el.value=d[id];};
 ['youtube_client_id','youtube_client_secret','youtube_refresh_token',
  'instagram_username','instagram_password','tiktok_session_cookie'].forEach(set);
 const plats=(d.enabled_platforms||[]);
 document.getElementById('p_youtube').checked=plats.includes('youtube');
 document.getElementById('p_instagram').checked=plats.includes('instagram');
 document.getElementById('p_tiktok').checked=plats.includes('tiktok');
}

async function saveSocial(){
 const m=document.getElementById('msg');
 const enabled=[];
 if(document.getElementById('p_youtube').checked)enabled.push('youtube');
 if(document.getElementById('p_instagram').checked)enabled.push('instagram');
 if(document.getElementById('p_tiktok').checked)enabled.push('tiktok');
 const body={enabled_platforms:enabled};
 ['youtube_client_id','youtube_client_secret','youtube_refresh_token',
  'instagram_username','instagram_password','tiktok_session_cookie'].forEach(id=>{
   let v=document.getElementById(id).value.trim();
   // Maskeli (dokunulmamış) sır alanını gönderme — eskisi korunur
   if(SECRET_IDS.includes(id)&&v.startsWith('••'))return;
   body[id]=v;
 });
 m.textContent='Kaydediliyor...';
 const r=await fetch('./api/social',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(r.ok){const j=await r.json();m.textContent='✅ Kaydedildi — aktif: '+(j.active_platforms.join(', ')||'yok');loadSocial();}
 else{m.textContent='❌ '+((await r.json()).detail||'Hata');}
}

async function loadVideos(){
 const v=await (await fetch('./api/videos')).json();
 const tb=document.querySelector('#videos tbody');tb.innerHTML='';
 if(!v.length){tb.innerHTML='<tr><td colspan=4 class="muted">Henüz video yok</td></tr>';return;}
 v.forEach(x=>{const tr=document.createElement('tr');
   tr.innerHTML=`<td>${x.task_id}</td><td>${x.size_mb}MB</td><td class="muted">${x.modified}</td>`+
   `<td><a href="./api/videos/${x.task_id}/file" target="_blank"><button>İzle</button></a> `+
   `<button class="danger" onclick="del('${x.task_id}')">Sil</button></td>`;tb.appendChild(tr);});
}

async function del(id){
 if(!confirm(id+' silinsin mi?'))return;
 const r=await fetch('./api/videos/'+id,{method:'DELETE'});
 if(r.ok){loadVideos();}else{alert('Silinemedi: '+((await r.json()).detail||''));}
}

loadSocial();loadVideos();setInterval(loadVideos,15000);
</script>
</body></html>"""
