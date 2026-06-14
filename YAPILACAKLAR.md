# ✅ Yapılacaklar — Tam Kurulum Kontrol Listesi

Sıfırdan canlıya kadar yapman gereken her şey. **En hızlı yol:** sadece
🟥 ZORUNLU kısmı yap (Gemini + Pexels), sistem video üretmeye başlar.
Sosyal medyayı sonra ekle.

---

## 🟥 ZORUNLU API'ler (bunlar olmadan çalışmaz)

### 1. Gemini API Key — AI beyni (konu/senaryo üretir)
- **Nereden:** https://aistudio.google.com/apikey → "Create API key" (ücretsiz tier var)
- **Nereye:**
  - Agent için → Coolify **Environment Variables**: `LLM_API_KEY=AIza...`
  - MPT için → deploy sonrası **config.toml** (Adım 9)

### 2. Pexels API Key — video görüntü kaynağı (stok klipler)
- **Nereden:** https://www.pexels.com/api/ → ücretsiz, anında key
- **Nereye:** deploy sonrası **config.toml** (Adım 9) — `pexels_api_keys`
- *(Alternatif: Pixabay — https://pixabay.com/api/docs/)*

---

## 🟨 OPSİYONEL — Sosyal Medya (hangisini istersen)

> Hiçbirini doldurmazsan sistem yine video **üretir**, sadece paylaşmaz
> (panelden izler/indirirsin). İstediğini ekle.

### 3. YouTube (resmi API — EN SAĞLAM, ban riski yok) ⭐ önerilen
Adımlar:
1. https://console.cloud.google.com → yeni proje
2. **YouTube Data API v3**'ü etkinleştir
3. **OAuth consent screen** → External → kendini "test user" ekle → scope: `youtube.upload`
4. **Credentials → Create OAuth client ID → Desktop app** → `client_id` + `client_secret`
5. **Refresh token üret:** https://developers.google.com/oauthplayground
   - Sağ üst ⚙️ → "Use your own OAuth credentials" → client_id/secret gir
   - Scope: `https://www.googleapis.com/auth/youtube.upload` → Authorize
   - "Exchange authorization code for tokens" → **refresh_token**'ı kopyala
   - (OAuth client'ında authorized redirect'e `https://developers.google.com/oauthplayground` ekli olmalı)
- **Env:**
  ```
  SOCIAL_YOUTUBE_CLIENT_ID=...
  SOCIAL_YOUTUBE_CLIENT_SECRET=...
  SOCIAL_YOUTUBE_REFRESH_TOKEN=...
  ```

### 4. TikTok (browser-use + cookie — ⚠️ ban riski)
1. Tarayıcıda tiktok.com'a giriş yap
2. F12 → Application → Cookies → `sessionid` değerini (ideal: `tt_csrf_token`, `tt_chain_token` da) kopyala
- **Env (header formatı önerilir):**
  ```
  SOCIAL_TIKTOK_SESSION_COOKIE=sessionid=ABC; tt_csrf_token=XYZ
  ```

### 5. Instagram (browser-use + user/pass — ⚠️ ban riski, 2FA sorun olabilir)
```
SOCIAL_INSTAGRAM_USERNAME=kullanici
SOCIAL_INSTAGRAM_PASSWORD=sifre
```

### Aktif platformları seç
```
SOCIAL_ENABLED_PLATFORMS=youtube          # sadece youtube (en güvenli)
# veya: youtube,tiktok,instagram
SOCIAL_PUBLISH_STRATEGY=hybrid            # api=sadece resmi API, browser=sadece tarayıcı
```

---

## 🟦 OPSİYONEL — Bildirim & Panel

### 6. Telegram bildirimleri (kritik hatalarda uyarı)
1. Telegram'da **@BotFather** → `/newbot` → token al
2. Bot'a bir mesaj at → chat_id öğren: @userinfobot veya
   `https://api.telegram.org/bot<TOKEN>/getUpdates` → `chat.id`
```
NOTIFY_ENABLED=true
NOTIFY_TELEGRAM_BOT_TOKEN=...
NOTIFY_TELEGRAM_CHAT_ID=...
```

### 7. Kontrol paneli şifresi (panel açacaksan ZORUNLU)
```
PANEL_PASSWORD=guclu-bir-sifre
```

---

## 🟩 İçerik & Zamanlama ayarları (varsayılanlar iş görür)
```
CONTENT_LANGUAGE=tr
CONTENT_NICHE=motivation        # finance, tech, education, travel, health, comedy
CONTENT_TARGET_DURATION_SECONDS=60
SCHEDULER_PRODUCTION_HOURS=9,14,19   # günde 3 video
SCHEDULER_DAILY_VIDEO_COUNT=3
STORAGE_RETENTION_DAYS=7         # 7 günden eski videolar otomatik silinir
```

---

## 🚀 DEPLOY ADIMLARI (Coolify)

- [ ] **8.** DNS A kaydı: `video.domainin.com` → VPS IP
- [ ] **9.** Coolify → + Add Resource → Public Repository →
      `https://github.com/12darko/EnophiaVideoBuilder.git` → Branch `main` → Docker Compose
- [ ] **10.** Environment Variables gir (yukarıdaki zorunlu + seçtiğin opsiyonel)
- [ ] **11.** video-generator servisi → FQDN: `https://video.domainin.com:8501` (`:8501` ŞART)
- [ ] **12.** 🔒 video-generator'a **Basic Auth** ekle (UI şifresiz kalmasın!)
- [ ] **13.** **Deploy** → iki container "(healthy)" olana kadar bekle
- [ ] **14.** `https://video.domainin.com` → sol panelden **config.toml** ayarla:
      ```toml
      [app]
      video_source = "pexels"
      pexels_api_keys = ["PEXELS_KEY"]
      llm_provider = "gemini"
      gemini_api_key = "GEMINI_KEY"
      gemini_model_name = "gemini-2.0-flash"
      ```
      (Artık restart'ta SİLİNMEZ — kalıcı volume'e bağlı ✓)
- [ ] **15.** İlk testi tetikle: env'e `AGENT_RUN_ON_START=true` ekle → redeploy
- [ ] **16.** Logları izle: Coolify → ai-agent → Logs (veya `docker logs -f video-agent`)

---

## 🎛️ OPSİYONEL — Kontrol Paneli erişimi
- Tarayıcıdan: ai-agent servisine FQDN `https://panel.domainin.com:8090` + `PANEL_PASSWORD`
- Detay: [DOMAIN_KURULUM.md](DOMAIN_KURULUM.md) §6.5

## 🧠 OPSİYONEL — Hermes ile doğal dil kontrolü
- Sunucuya Hermes Agent kur, panel API'siyle Türkçe komut ver
- Detay: [HERMES_ENTEGRASYON.md](HERMES_ENTEGRASYON.md)

---

## ⚡ EN HIZLI BAŞLANGIÇ (5 dakika, lokalde test)
```bash
cp .env.example .env
# .env içine sadece: LLM_API_KEY + (istersen AGENT_RUN_ON_START=true)
docker compose up -d --build
# UI:    http://localhost:8501  (config.toml'a Pexels + Gemini gir)
# Panel: http://localhost:8090
docker logs -f video-agent
```

---

## 🔑 Hangi key NEREYE? (özet — en çok karıştırılan)
| Key | Yer | Neden |
|-----|-----|-------|
| `LLM_API_KEY` (Gemini) | **Env var** | Agent konu/senaryo üretir |
| Gemini key | **config.toml** | MPT kendi arama terimlerini üretir |
| Pexels key | **config.toml** | MPT stok video indirir |
| Sosyal medya | **Env var** | Agent paylaşır |
| Telegram | **Env var** | Agent hata bildirir |
