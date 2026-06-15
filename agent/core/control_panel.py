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

    # ── Giriş doğrulama (login formu için) ───────────────────
    @app.get("/api/auth/check")
    async def auth_check(_: bool = Depends(require_auth)) -> dict[str, Any]:
        return {"ok": True, "username": panel_cfg.username}

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

    # ── Hermes sohbeti ───────────────────────────────────────
    @app.get("/api/chat/status")
    async def chat_status() -> dict[str, Any]:
        h = config.hermes
        return {"enabled": bool(h.enabled and h.api_key), "model": h.model}

    @app.post("/api/chat")
    async def chat(
        payload: dict[str, Any], _: bool = Depends(require_auth)
    ) -> dict[str, Any]:
        h = config.hermes
        if not (h.enabled and h.api_key):
            raise HTTPException(
                status_code=503,
                detail="Hermes bağlı değil (HERMES_ENABLED / HERMES_API_KEY ayarlayın)",
            )
        message = (payload.get("message") or "").strip()
        if not message:
            raise HTTPException(status_code=400, detail="Boş mesaj")
        history = payload.get("history") or []

        # Hermes'e sistemimizi tanıtan kısa yönerge
        system = (
            "Sen bu video fabrikasının asistanısın. Kullanıcı Türkçe konuşur. "
            "MoneyPrinterTurbo video API'si: "
            f"{config.video_generator.api_base_url} "
            "(POST /api/v1/videos ile video üret, GET /api/v1/tasks/{id} ile durum). "
            "Yönetim paneli API'si: http://localhost:"
            f"{config.control_panel.port} "
            "(/api/social hesaplar, /api/videos liste/sil). "
            "Sunucu ayarını değiştirmeden veya dosya silmeden önce kullanıcıya sor."
        )
        messages = [{"role": "system", "content": system}]
        for m in history[-10:]:
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": str(content)})
        messages.append({"role": "user", "content": message})

        import httpx

        try:
            async with httpx.AsyncClient(timeout=h.timeout) as client:
                resp = await client.post(
                    h.api_url,
                    headers={"Authorization": f"Bearer {h.api_key}"},
                    json={"model": h.model, "messages": messages},
                )
                resp.raise_for_status()
                data = resp.json()
            reply = data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Hermes API hatası: {e.response.status_code}")
            raise HTTPException(
                status_code=502, detail=f"Hermes hatası: {e.response.status_code}"
            )
        except Exception as e:
            logger.error(f"❌ Hermes'e ulaşılamadı: {e!r}")
            raise HTTPException(
                status_code=502, detail="Hermes'e ulaşılamadı (API server çalışıyor mu?)"
            )
        return {"reply": reply}

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
 #chatlog{background:#0b1220;border:1px solid #334155;border-radius:8px;padding:12px;height:280px;overflow-y:auto;margin-bottom:10px}
 .msg{margin:6px 0;padding:8px 12px;border-radius:10px;max-width:85%;white-space:pre-wrap;line-height:1.4}
 .me{background:#3730a3;margin-left:auto}
 .bot{background:#334155}
 .chatrow{display:flex;gap:8px}
 .chatrow input{flex:1}
 .badge{font-size:12px;padding:2px 8px;border-radius:6px;margin-left:8px}
 .on{background:#14532d;color:#bbf7d0}
 .off{background:#7f1d1d;color:#fecaca}
 .logincard{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
 .logincard input{width:auto;max-width:180px}
</style></head><body>
<header>🎯 Video Fabrikası — Hermes & Hesaplar & Videolar</header>
<main>
 <div class="card logincard">
   <span id="authState" class="muted">🔒 Oturum: giriş yapılmadı</span>
   <button id="loginBtn" onclick="toggleLogin()">🔐 Giriş Yap</button>
   <span id="loginForm" style="display:none">
     <input type="text" id="loginUser" placeholder="Kullanıcı adı" value="admin">
     <input type="password" id="loginPass" placeholder="Şifre" onkeydown="if(event.key==='Enter')doLogin()">
     <button onclick="doLogin()">Giriş</button>
     <span id="loginMsg" class="muted"></span>
   </span>
 </div>
 <div class="card">
   <h3>🤖 Hermes ile Sohbet <span id="hbadge" class="badge off">bağlı değil</span></h3>
   <p class="muted">"Şu konuda video üret", "bunu YouTube'a yolla", "eski videoları sil" gibi yaz. Hermes MoneyPrinterTurbo'yu ve bu paneli kontrol eder.</p>
   <div id="chatlog"></div>
   <div class="chatrow">
     <input type="text" id="chatInput" placeholder="Hermes'e yaz..." onkeydown="if(event.key==='Enter')sendChat()">
     <button id="chatSend" onclick="sendChat()">Gönder</button>
   </div>
 </div>
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
let chatHistory=[];
let hermesOn=false;
let authHeader=null;

// ── Giriş / oturum ──────────────────────────────────────────
function hdrs(json){const h={};if(json)h['Content-Type']='application/json';if(authHeader)h['Authorization']=authHeader;return h;}
function toggleLogin(){const f=document.getElementById('loginForm');f.style.display=(f.style.display==='none'?'inline':'none');if(f.style.display!=='none')document.getElementById('loginPass').focus();}
function setLoggedIn(user){
 authHeader&&sessionStorage.setItem('auth',authHeader);
 document.getElementById('authState').textContent='🔓 Oturum: '+(user||'giriş yapıldı');
 document.getElementById('loginForm').style.display='none';
 const b=document.getElementById('loginBtn');b.textContent='Çıkış';b.setAttribute('onclick','doLogout()');
}
function doLogout(){
 authHeader=null;sessionStorage.removeItem('auth');
 document.getElementById('authState').textContent='🔒 Oturum: giriş yapılmadı';
 const b=document.getElementById('loginBtn');b.textContent='🔐 Giriş Yap';b.setAttribute('onclick','toggleLogin()');
}
async function doLogin(){
 const u=document.getElementById('loginUser').value.trim();
 const p=document.getElementById('loginPass').value;
 const m=document.getElementById('loginMsg');
 const hdr='Basic '+btoa(unescape(encodeURIComponent(u+':'+p)));
 m.textContent='Kontrol ediliyor...';
 try{
   const r=await fetch('./api/auth/check',{headers:{'Authorization':hdr}});
   if(r.ok){authHeader=hdr;m.textContent='';document.getElementById('loginPass').value='';setLoggedIn(u);}
   else if(r.status===403){m.textContent='❌ Sunucuda PANEL_PASSWORD ayarlı değil';}
   else{m.textContent='❌ Hatalı kullanıcı adı/şifre';}
 }catch(e){m.textContent='❌ Bağlantı hatası';}
}
function needLogin(){
 if(authHeader)return false;
 document.getElementById('loginForm').style.display='inline';
 document.getElementById('loginMsg').textContent='⚠️ Önce giriş yapın';
 document.getElementById('loginPass').focus();
 return true;
}
async function restoreAuth(){
 const saved=sessionStorage.getItem('auth');
 if(!saved)return;
 try{
   const r=await fetch('./api/auth/check',{headers:{'Authorization':saved}});
   if(r.ok){authHeader=saved;const j=await r.json();setLoggedIn(j.username);}
   else{sessionStorage.removeItem('auth');}
 }catch(e){}
}

function addMsg(role,text){
 const log=document.getElementById('chatlog');
 const d=document.createElement('div');
 d.className='msg '+(role==='user'?'me':'bot');
 d.textContent=text;
 log.appendChild(d);log.scrollTop=log.scrollHeight;
}

async function chatStatus(){
 try{
   const s=await (await fetch('./api/chat/status')).json();
   hermesOn=!!s.enabled;
 }catch(e){hermesOn=false;}
 const b=document.getElementById('hbadge');
 b.textContent=hermesOn?'bağlı':'bağlı değil';
 b.className='badge '+(hermesOn?'on':'off');
 document.getElementById('chatInput').disabled=!hermesOn;
 document.getElementById('chatSend').disabled=!hermesOn;
 if(!hermesOn&&!document.getElementById('chatlog').children.length){
   addMsg('bot','Hermes henüz bağlı değil. Sunucuda Hermes API server\\'ı açıp HERMES_ENABLED=true + HERMES_API_KEY ayarlayın.');
 }
}

async function sendChat(){
 const inp=document.getElementById('chatInput');
 const text=inp.value.trim();if(!text||!hermesOn)return;
 if(needLogin())return;
 inp.value='';addMsg('user',text);
 chatHistory.push({role:'user',content:text});
 const btn=document.getElementById('chatSend');btn.disabled=true;
 addMsg('bot','...');
 const log=document.getElementById('chatlog');const ph=log.lastChild;
 try{
   const r=await fetch('./api/chat',{method:'POST',headers:hdrs(true),
     body:JSON.stringify({message:text,history:chatHistory})});
   const j=await r.json();
   if(r.ok){ph.textContent=j.reply;chatHistory.push({role:'assistant',content:j.reply});}
   else{ph.textContent='❌ '+(j.detail||'Hata');}
 }catch(e){ph.textContent='❌ Bağlantı hatası';}
 btn.disabled=false;inp.focus();
}

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
 if(needLogin()){m.textContent='⚠️ Önce giriş yapın';return;}
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
 const r=await fetch('./api/social',{method:'POST',headers:hdrs(true),body:JSON.stringify(body)});
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
 if(needLogin()){alert('Önce 🔐 Giriş Yap');return;}
 if(!confirm(id+' silinsin mi?'))return;
 const r=await fetch('./api/videos/'+id,{method:'DELETE',headers:hdrs()});
 if(r.ok){loadVideos();}else{alert('Silinemedi: '+((await r.json()).detail||''));}
}

restoreAuth();chatStatus();loadSocial();loadVideos();setInterval(loadVideos,15000);
</script>
</body></html>"""
