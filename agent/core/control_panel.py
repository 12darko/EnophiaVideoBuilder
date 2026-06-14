"""
AI Agent — Control Panel (Web Kontrol Paneli)
===============================================
Hafif bir FastAPI paneli: durum izleme, üretilen videoları
listeleme/izleme/silme ve "şu konuda üret" manuel tetikleme.

Scheduler ile aynı event loop'ta uvicorn olarak çalışır.
Basic Auth ile korunur (şifre boşsa salt-okunur mod).
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from typing import Any, Optional

from loguru import logger

from config import AgentConfig
from core.storage_manager import StorageManager


def create_app(orchestrator: Any, config: AgentConfig) -> Any:
    """FastAPI uygulamasını oluştur."""
    from fastapi import Depends, FastAPI, HTTPException, status
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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

    # ── İstatistik ───────────────────────────────────────────
    @app.get("/api/stats")
    async def get_stats() -> dict[str, Any]:
        stats = orchestrator.get_stats()
        total = await asyncio.to_thread(storage.total_size_bytes)
        stats["storage_total_mb"] = round(total / (1024 * 1024), 2)
        stats["read_only"] = not bool(panel_cfg.password)
        return stats

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
    async def delete_video(task_id: str, _: bool = Depends(require_auth)) -> dict[str, Any]:
        ok = await asyncio.to_thread(storage.delete_video, task_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Silinemedi veya bulunamadı")
        return {"deleted": task_id}

    # ── Geçmiş ───────────────────────────────────────────────
    @app.get("/api/history")
    async def get_history(limit: int = 20) -> list[dict[str, Any]]:
        history_dir = os.path.join(config.data_dir, "history")
        if not os.path.isdir(history_dir):
            return []
        files = sorted(
            (f for f in os.listdir(history_dir) if f.endswith(".json")),
            reverse=True,
        )[:limit]
        out: list[dict[str, Any]] = []
        for f in files:
            try:
                with open(os.path.join(history_dir, f), encoding="utf-8") as fh:
                    out.append(json.load(fh))
            except Exception:
                continue
        return out

    # ── Profiller (çoklu kanal) ──────────────────────────────
    from dataclasses import asdict

    @app.get("/api/profiles")
    async def list_profiles() -> list[dict[str, Any]]:
        return [asdict(p) for p in orchestrator.profiles.list()]

    @app.post("/api/profiles")
    async def create_profile(
        payload: dict[str, Any], _: bool = Depends(require_auth)
    ) -> dict[str, Any]:
        return asdict(orchestrator.profiles.create(payload))

    @app.put("/api/profiles/{profile_id}")
    async def update_profile(
        profile_id: str, payload: dict[str, Any], _: bool = Depends(require_auth)
    ) -> dict[str, Any]:
        p = orchestrator.profiles.update(profile_id, payload)
        if not p:
            raise HTTPException(status_code=404, detail="Profil bulunamadı")
        return asdict(p)

    @app.delete("/api/profiles/{profile_id}")
    async def delete_profile(
        profile_id: str, _: bool = Depends(require_auth)
    ) -> dict[str, Any]:
        if not orchestrator.profiles.delete(profile_id):
            raise HTTPException(
                status_code=400, detail="Silinemedi (varsayılan veya yok)"
            )
        return {"deleted": profile_id}

    # ── Manuel tetikleme ─────────────────────────────────────
    @app.post("/api/trigger")
    async def trigger(
        payload: Optional[dict[str, Any]] = None,
        _: bool = Depends(require_auth),
    ) -> dict[str, Any]:
        payload = payload or {}
        topic = payload.get("topic")
        profile_id = payload.get("profile_id")
        logger.info(
            f"🖱️ Panelden manuel tetikleme (profil={profile_id!r}, konu={topic!r})"
        )
        # Arka planda çalıştır — isteği bloke etme
        asyncio.create_task(
            orchestrator.run_production_cycle(
                topic_override=topic, profile_id=profile_id
            )
        )
        return {"status": "triggered", "topic": topic, "profile_id": profile_id}

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

    app = create_app(orchestrator, config)
    port = config.control_panel.port
    auth_note = "🔒 auth aktif" if config.control_panel.password else "⚠️ salt-okunur (şifre yok)"
    logger.info(f"🌐 Kontrol paneli başlıyor → :{port} ({auth_note})")

    server = uvicorn.Server(
        uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    )
    await server.serve()


_DASHBOARD_HTML = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🏭 Video Fabrikası — Panel</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}
 header{background:#1e293b;padding:16px 24px;font-size:20px;font-weight:600}
 main{padding:24px;max-width:1000px;margin:0 auto}
 .card{background:#1e293b;border-radius:12px;padding:20px;margin-bottom:20px}
 .stats{display:flex;gap:16px;flex-wrap:wrap}
 .stat{background:#334155;border-radius:8px;padding:12px 18px;min-width:120px}
 .stat b{display:block;font-size:24px}
 button{background:#6366f1;color:#fff;border:0;border-radius:8px;padding:10px 16px;cursor:pointer;font-size:14px}
 button.danger{background:#ef4444}
 input{background:#334155;border:1px solid #475569;color:#fff;border-radius:8px;padding:10px;width:60%}
 table{width:100%;border-collapse:collapse;margin-top:8px}
 td,th{text-align:left;padding:8px;border-bottom:1px solid #334155;font-size:14px}
 .muted{color:#94a3b8;font-size:13px}
</style></head><body>
<header>🏭 Otonom Video Fabrikası — Kontrol Paneli</header>
<main>
 <div class="card"><div class="stats" id="stats">Yükleniyor…</div></div>
 <div class="card">
   <h3>🎬 Manuel Üretim</h3>
   <p class="muted">Profil seç (kanal), konu yaz (boşsa AI üretir).</p>
   <select id="profileSel"></select>
   <input id="topic" placeholder="Konu (opsiyonel)" style="width:45%">
   <button onclick="trigger()">Üret</button>
   <span id="trigMsg" class="muted"></span>
 </div>
 <div class="card">
   <h3>📺 Kanallar / Profiller</h3>
   <table id="profiles"><thead><tr><th>Ad</th><th>Niche</th><th>Dil</th><th>Platformlar</th><th></th></tr></thead><tbody></tbody></table>
   <h4 style="margin-top:16px">➕ Yeni Kanal</h4>
   <input id="pName" placeholder="Kanal adı" style="width:30%">
   <input id="pNiche" placeholder="niche (motivation)" style="width:20%">
   <input id="pLang" placeholder="dil (tr)" style="width:12%">
   <input id="pPlat" placeholder="platformlar: youtube,tiktok" style="width:30%">
   <br><br>
   <input id="pTags" placeholder="hashtagler: #shorts,#viral" style="width:45%">
   <input id="pPool" placeholder="konu havuzu (virgüllü, opsiyonel)" style="width:30%">
   <button onclick="addProfile()">Ekle</button>
   <span id="pMsg" class="muted"></span>
 </div>
 <div class="card">
   <h3>📦 Üretilen Videolar</h3>
   <table id="videos"><thead><tr><th>Task</th><th>Boyut</th><th>Tarih</th><th></th></tr></thead><tbody></tbody></table>
 </div>
</main>
<script>
async function load(){
 const s=await (await fetch('./api/stats')).json();
 document.getElementById('stats').innerHTML=
   `<div class="stat"><span class="muted">Üretilen</span><b>${s.successful_videos||0}</b></div>`+
   `<div class="stat"><span class="muted">Paylaşım</span><b>${s.successful_posts||0}/${s.total_posts||0}</b></div>`+
   `<div class="stat"><span class="muted">Başarısız</span><b>${s.failed_videos||0}</b></div>`+
   `<div class="stat"><span class="muted">Depolama</span><b>${s.storage_total_mb||0}MB</b></div>`+
   (s.read_only?`<div class="stat"><span class="muted">Mod</span><b>👁️ R/O</b></div>`:'');
 const v=await (await fetch('./api/videos')).json();
 const tb=document.querySelector('#videos tbody');tb.innerHTML='';
 if(!v.length){tb.innerHTML='<tr><td colspan=4 class="muted">Henüz video yok</td></tr>';}
 v.forEach(x=>{const tr=document.createElement('tr');
   tr.innerHTML=`<td>${x.task_id}</td><td>${x.size_mb}MB</td><td class="muted">${x.modified}</td>`+
   `<td><a href="./api/videos/${x.task_id}/file" target="_blank"><button>İzle</button></a> `+
   `<button class="danger" onclick="del('${x.task_id}')">Sil</button></td>`;tb.appendChild(tr);});
}
async function loadProfiles(){
 const ps=await (await fetch('./api/profiles')).json();
 const sel=document.getElementById('profileSel');
 sel.innerHTML=ps.map(p=>`<option value="${p.id}">${p.name}</option>`).join('');
 const tb=document.querySelector('#profiles tbody');tb.innerHTML='';
 ps.forEach(p=>{const tr=document.createElement('tr');
   const plat=(p.enabled_platforms||[]).join(', ')||'(ortak)';
   tr.innerHTML=`<td>${p.name}</td><td>${p.niche}</td><td>${p.language}</td><td class="muted">${plat}</td>`+
   `<td><button onclick="trigP('${p.id}')">Üret</button> `+
   (p.id!=='default'?`<button class="danger" onclick="delP('${p.id}')">Sil</button>`:'')+`</td>`;
   tb.appendChild(tr);});
}
async function trigger(){
 const t=document.getElementById('topic').value.trim();
 const pid=document.getElementById('profileSel').value;
 const m=document.getElementById('trigMsg');m.textContent='Tetikleniyor…';
 const r=await fetch('./api/trigger',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic:t||null,profile_id:pid||null})});
 m.textContent=r.ok?'✅ Üretim başladı (loglardan takip et)':'❌ '+(await r.json()).detail;
}
async function trigP(id){
 const r=await fetch('./api/trigger',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({profile_id:id})});
 alert(r.ok?'✅ Üretim başladı':'❌ '+(await r.json()).detail);
}
async function addProfile(){
 const body={name:pName.value.trim(),niche:pNiche.value.trim()||'motivation',language:pLang.value.trim()||'tr',
   enabled_platforms:pPlat.value.split(',').map(x=>x.trim()).filter(Boolean),hashtags:pTags.value.trim(),topic_pool:pPool.value.trim()};
 const m=document.getElementById('pMsg');
 if(!body.name){m.textContent='Ad gerekli';return;}
 const r=await fetch('./api/profiles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(r.ok){pName.value=pNiche.value=pLang.value=pPlat.value=pTags.value=pPool.value='';m.textContent='✅ Eklendi';loadProfiles();}
 else{m.textContent='❌ '+(await r.json()).detail;}
}
async function delP(id){
 if(!confirm('Kanal silinsin mi?'))return;
 const r=await fetch('./api/profiles/'+id,{method:'DELETE'});
 if(r.ok){loadProfiles();}else{alert('Silinemedi: '+(await r.json()).detail);}
}
async function del(id){
 if(!confirm(id+' silinsin mi?'))return;
 const r=await fetch('./api/videos/'+id,{method:'DELETE'});
 if(r.ok){load();}else{alert('Silinemedi: '+(await r.json()).detail);}
}
load();loadProfiles();setInterval(load,15000);
</script>
</body></html>"""
