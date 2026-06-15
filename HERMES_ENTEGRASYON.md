# 🧠 Hermes Agent + Enophia Video Builder Entegrasyonu

Videodaki "terminalden konuşulan, hesaba girip işlem yapan" ajan
[**Nous Research — Hermes Agent**](https://github.com/nousresearch/hermes-agent).
Sunucuyu yöneten **genel amaçlı** asistan (Claude Code / Codex muadili).

Bizim **Enophia Video Builder** ise tek amaçlı **video fabrikası**. İkisi yarışmaz —
**Hermes = operatör/beyin**, **Enophia = güvenli üretim bandı**.

```
            ┌──────────── PANELDEN SOHBET ────────────┐
            │                                          │
  SEN ─yaz→ PANEL (:8090, "Hermes ile Sohbet") ─HTTP→ HERMES (host'ta)
                                                         │  (terminal + http)
                                          ┌──────────────┼───────────────┐
                                          ▼              ▼               ▼
                                  MoneyPrinterTurbo   Panel API      Sunucu
                                  (:8080 video üret)  (:8090 sil)    (ops/debug)
```

Yani **iki yön** var:
1. **Sen → Panel chat → Hermes:** panelin "Hermes ile Sohbet" kutusundan Türkçe yazarsın.
2. **Hermes → MPT + Panel:** Hermes video ürettirir, kanala yollatır, video siler.

MoneyPrinterTurbo'nun **kendi arayüzü de açık kalır** — istersen sen elle de üretirsin.

---

## 1. İki Ayrı Şey — Karıştırma

| | Hermes Agent | Enophia Video Builder |
|---|---|---|
| Nerede | **Host'a kurulur** (curl install) | Coolify'da **container** |
| Ne yapar | Her şey: shell, repo, video ürettir | Video üretir/paylaşır + panel |
| Yetki | Host'ta tam (güçlü + riskli) | Sandbox (güvenli) |
| Sen nasıl kullanırsın | Panel chat / Telegram / terminal | MPT UI + panel |

> **Enophia, Hermes'e muhtaç DEĞİL.** Kendi başına 7/24 çalışır. Hermes'i sadece
> "doğal dille komut vermek + self-heal" istersen eklersin.

---

## 2. Tek seferlik: Swap (RAM/OOM sorununu kalıcı çözer)

Videodaki "ajan RAM'i büyüttü" sihri aslında tek seferlik bir sunucu ayarı.
Bir kere açarsan render bir daha bellek yetmezliğinden patlamaz:

```bash
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h   # swap satırı doldu mu?
```

---

## 3. Hermes Kurulumu (host'ta)

```bash
# Linux/macOS/WSL2 sunucuda:
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.bashrc

hermes model      # beyin seç: gemini (mevcut key) / claude / openai...
hermes            # test: "merhaba" yaz, cevap veriyor mu?
```

İsteğe bağlı telefon kontrolü (Telegram):
```bash
hermes gateway setup    # Telegram seç, bot token bağla, kendi kullanıcına kısıtla
```

Detay: https://hermes-agent.nousresearch.com/docs

---

## 4. Panel "Hermes ile Sohbet" kutusunu bağlama

Panelin chat kutusu, host'taki **Hermes API server**'a (OpenAI-uyumlu
`/v1/chat/completions`) proxy'ler. İki tarafı bağlamak gerekiyor:

### a) Host'ta — Hermes API server'ı aç
`~/.hermes/.env` dosyasına ekle:
```
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=8642
API_SERVER_KEY=guclu-bir-anahtar
```
Sonra başlat:
```bash
hermes gateway          # API server (8642) + varsa Telegram birlikte çalışır
```

### b) Enophia tarafı — env (Coolify/.env)
```
HERMES_ENABLED=true
HERMES_API_KEY=guclu-bir-anahtar     # API_SERVER_KEY ile AYNI
# HERMES_API_URL=http://host.docker.internal:8642/v1/chat/completions  (varsayılan)
```
> Container host'a `host.docker.internal` ile erişir; compose'da
> `extra_hosts: host.docker.internal:host-gateway` zaten ayarlı.

Redeploy sonrası panelde **🤖 Hermes ile Sohbet → "bağlı"** rozetini görürsün ve
yazışmaya başlarsın: *"şu konuda video üret"*, *"bunu YouTube'a yolla"*,
*"eski videoları sil"*.

---

## 5. Hermes video fabrikasını nasıl sürüyor

Hermes host'ta terminal + http erişimine sahip; şu uçları kullanır:

**MoneyPrinterTurbo'da video ürettir:**
```bash
curl -X POST http://localhost:8080/api/v1/videos \
     -H "Content-Type: application/json" \
     -d '{"video_subject":"sabah rutini","video_aspect":"9:16"}'
curl http://localhost:8080/api/v1/tasks/TASK_ID    # durum
```
> Not: `8080` MPT API'sidir. Container dışından erişim için Coolify'da MPT'ye
> bir (korumalı) domain ver ya da host'tan container adıyla/portuyla çağır.

**Panelden video listele / sil (sosyal hesaplar):**
```bash
curl http://localhost:8090/api/videos
curl -u admin:$PANEL_PASSWORD -X DELETE http://localhost:8090/api/videos/TASK_ID
curl http://localhost:8090/api/social
```

> Bunları Hermes'e bir "skill" olarak öğretirsen düz Türkçe konuşursun:
> *"yeni motivasyon videosu üret ve TikTok'a yolla"* → Hermes uygun çağrıları yapar.

---

## 6. Panel API Referansı

| Method | Endpoint | Auth | Ne yapar |
|--------|----------|------|----------|
| GET | `/api/chat/status` | — | Hermes bağlı mı |
| POST | `/api/chat` | 🔒 | Hermes'e mesaj gönder `{"message":"...","history":[...]}` |
| GET | `/api/social` | — | Sosyal hesaplar (sırlar maskeli) |
| POST | `/api/social` | 🔒 | Hesapları kaydet + publisher'ları yenile |
| GET | `/api/videos` | — | Üretilen video listesi |
| GET | `/api/videos/{id}/file` | — | Videoyu indir/izle |
| DELETE | `/api/videos/{id}` | 🔒 | Video sil |

🔒 = `PANEL_PASSWORD` + Basic Auth gerekir. Şifre boşsa bu uçlar kapalıdır (salt-okunur).

---

## 7. Panele erişim — port derdi

### A) Hermes host'ta → panel host-local (ÖNERİLEN, ekstra domain YOK)
`docker-compose.yaml`'de ai-agent altındaki satırı aç:
```yaml
    ports:
      - "127.0.0.1:8090:8090"   # sadece host, internete kapalı
```
Hermes panele `http://127.0.0.1:8090` üzerinden ulaşır. Domain/SSL gerekmez.

### B) Sen tarayıcıdan açmak istersen → Coolify'da tek satır
ai-agent servisi → **Domains**: `https://panel.senindomain.com:8090` → Save.
DNS'e `panel` A kaydı ekle. **`PANEL_PASSWORD` koy!**

---

## 8. Güvenlik

- **Hermes host'ta tam yetkili** — yanlış komut sunucuyu bozabilir. Sistem talimatına
  *"sunucu ayarını değiştirmeden / dosya silmeden bana sor"* ekle (panel chat bunu
  zaten gönderiyor). Mümkünse ayrı/izole kullanıcıyla çalıştır.
- **`API_SERVER_KEY` zorunlu** — Hermes API server tüm terminal araçlarına tam erişim
  verir. Anahtarı güçlü tut, `0.0.0.0`'a açtıysan sunucu firewall'ıyla 8642'yi dışarı kapat.
- **Hermes'e `.env`/secret dosyalarını okutma** (`~/.hermes/.env` hariç) — anahtarlar sızabilir.
- **Paneli internete açıyorsan** `PANEL_PASSWORD` + Coolify Basic Auth **şart**.
