# 🏭 Otonom Video Fabrikası

**MoneyPrinterTurbo + AI Agent** — Tam otomatik, 7/24 çalışan yapay zeka destekli video üretim ve sosyal medya paylaşım sistemi.

Tek bir `docker compose up` komutuyla veya **Coolify** üzerinden deploy ederek kendi otonom video fabrikasınızı kurun.

---

## 🎯 Ne Yapar?

Bu sistem iki katmanlı bir mimariyle çalışır:

| Katman | Görev |
|---|---|
| **📹 Video Generator** | MoneyPrinterTurbo — AI ile kısa video üretir (senaryo, seslendirme, stok görsel, altyazı, montaj) |
| **🤖 AI Agent** | Otonom ajan — konu üretir, video üretimini tetikler, sosyal medyaya paylaşır, hataları kendi çözer |

### Tam Otomasyon Döngüsü

```
⏰ Zamanlanmış tetikleme (günde 3x)
    ↓
📝 LLM (Gemini/OpenAI) ile viral konu üret
    ↓
📜 Konu için voiceover senaryosu yaz
    ↓
🎥 MoneyPrinterTurbo API'ye video üretim isteği gönder
    ↓
⏳ Video render tamamlanmasını bekle
    ↓
🏷️ Başlık, açıklama ve hashtag üret
    ↓
📤 TikTok / Instagram Reels / YouTube Shorts'a paylaş
    ↓
📊 Sonucu logla, bir sonraki schedule'ı bekle
    ↓
🔄 Hata olursa → kendi kendine çöz (self-healing)
```

---

## 🛠️ Teknoloji Yığını

| Bileşen | Teknoloji |
|---|---|
| Video Motoru | [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) (Streamlit + FastAPI) |
| AI Beyni | Google Gemini / OpenAI / DeepSeek |
| Tarayıcı Otomasyon | [browser-use](https://github.com/browser-use/browser-use) + Playwright |
| Zamanlayıcı | APScheduler (cron tabanlı, 7/24) |
| Hata Yönetimi | Tenacity (exponential backoff) + özel self-healing modülü |
| Konteyner | Docker Compose (çift katmanlı) |
| PaaS | [Coolify](https://coolify.io) + Traefik reverse proxy |
| Bildirim | Telegram Bot API (opsiyonel) |

---

## 📁 Proje Yapısı

```
├── Dockerfile                    # Video generator imajı (Python + FFmpeg + supervisord)
├── supervisord.conf              # Streamlit + FastAPI process yönetimi
├── docker-compose.yml            # Çift katmanlı Coolify uyumlu compose
├── .env.example                  # Ortam değişkenleri şablonu
├── README.md                     # Bu dosya
│
└── agent/                        # 🤖 Otonom AI Agent
    ├── Dockerfile                # Agent imajı (Python + Playwright + Chromium)
    ├── requirements.txt          # Python bağımlılıkları
    ├── config.py                 # Pydantic Settings konfigürasyon
    ├── main.py                   # Giriş noktası (7/24 çalışır)
    │
    ├── core/                     # Çekirdek modüller
    │   ├── orchestrator.py       # Ana iş akışı orkestratörü
    │   ├── video_client.py       # MoneyPrinterTurbo API client
    │   ├── content_brain.py      # LLM ile içerik üretimi
    │   ├── social_publisher.py   # Sosyal medya yönetim facade
    │   ├── self_healer.py        # Otomatik hata çözme
    │   ├── storage_manager.py    # Video depolama (listele/sil/temizlik)
    │   ├── control_panel.py      # Web kontrol paneli (FastAPI, :8090)
    │   └── scheduler.py          # APScheduler zamanlayıcı
    │
    └── publishers/               # Platform adaptörleri
        ├── base.py               # Abstract publisher
        ├── tiktok.py             # TikTok (browser-use)
        ├── instagram.py          # Instagram (browser-use)
        └── youtube.py            # YouTube (resmi Data API v3)
```

---

## 🚀 Hızlı Başlangıç

> **Not:** Bu repo **kendi başına** çalışır — MoneyPrinterTurbo, video-generator
> imajı build edilirken otomatik klonlanır. Artık MPT fork'una elle dosya kopyalamaya
> gerek yok. Coolify'ı doğrudan bu repoya bağlaman yeterli.

### 1. Repoyu Hazırla

```bash
git clone https://github.com/SENIN-KULLANICIN/BU_REPO.git
cd BU_REPO
```

Belirli bir MoneyPrinterTurbo sürümüne sabitlemek istersen `Dockerfile` içindeki
`ARG MPT_REF=main` değerini değiştir (ör. `MPT_REF=v1.2.6`).

### 2. Environment Variables Ayarla

```bash
cp .env.example .env
nano .env  # API anahtarlarını gir
```

**Minimum zorunlu:**
```env
LLM_PROVIDER=gemini
LLM_API_KEY=AIzaSy...
CONTENT_LANGUAGE=tr
CONTENT_NICHE=motivation
```

### 3. Deploy Et

**Coolify ile (önerilen):**
- Coolify Dashboard → Add Resource → Git Repo → Docker Compose
- Environment Variables ekle
- Domain tanımla: `https://video.domain.com:8501`
- 🔒 UI'a **Basic Auth** ekle (şifresiz bırakma!)
- Deploy tıkla

👉 Adım adım domain + SSL + güvenlik için: **[DOMAIN_KURULUM.md](DOMAIN_KURULUM.md)**

**Veya lokal Docker ile:**
```bash
docker compose up -d --build
```

### 4. config.toml Ayarla

Deploy sonrası `https://video.domain.com` adresine gidip sol panelden Pexels API key ve LLM ayarlarını girin.

> 💡 **Kontrol paneli:** Agent'ın kendi web paneli `:8090`'da çalışır (durum, video
> listele/izle/sil, "şu konuda üret" tetikleme). Erişim opsiyoneldir — detay
> [DOMAIN_KURULUM.md](DOMAIN_KURULUM.md) §6.5.
>
> 🧠 **Hermes ile doğal dil kontrolü:** Sunucuda
> [Hermes Agent](https://github.com/nousresearch/hermes-agent) kurarsan, ona Türkçe
> "yeni video üret ve at" diyerek bu sistemi sürebilirsin —
> [HERMES_ENTEGRASYON.md](HERMES_ENTEGRASYON.md).

---

## ⚙️ Yapılandırma

Tüm ayarlar ortam değişkenleri üzerinden yönetilir. Detaylar için [.env.example](.env.example) dosyasına bakın.

### Temel Ayar Grupları

| Prefix | Açıklama | Örnek |
|---|---|---|
| `LLM_` | Yapay zeka beyni | `LLM_PROVIDER=gemini` |
| `CONTENT_` | İçerik stratejisi | `CONTENT_NICHE=finance` |
| `SCHEDULER_` | Zamanlama | `SCHEDULER_PRODUCTION_HOURS=9,14,19` |
| `SOCIAL_` | Sosyal medya | `SOCIAL_ENABLED_PLATFORMS=tiktok,youtube` |
| `HEAL_` | Self-healing | `HEAL_MAX_RETRIES=5` |
| `NOTIFY_` | Bildirimler | `NOTIFY_ENABLED=true` |

---

## 📊 Kaynak Gereksinimleri

| Bileşen | RAM | CPU |
|---|---|---|
| video-generator | 8 GB (limit) | 3 çekirdek |
| ai-agent | 3 GB (limit) | 2 çekirdek |
| OS + Coolify + Traefik | ~5 GB | — |
| **Minimum VPS** | **16 GB** | **4 çekirdek** |

---

## 🔒 Güvenlik Notları

- Docker socket **read-only** olarak mount edilir — agent container'ları yönetemez, sadece logları okur
- Sosyal medya şifreleri ortam değişkenlerinde tutulur — Coolify UI'dan güvenle yönetilebilir
- browser-use ile sosyal medya otomasyonu **hesap ban riski** taşır — resmi API'ler tercih edilmelidir
- Tüm container'lar `unless-stopped` restart policy ile çalışır

---

## 📄 Lisans

Bu proje, [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) üzerine inşa edilmiş bir deployment ve otomasyon katmanıdır. Orijinal projenin lisans koşullarına tabidir.
