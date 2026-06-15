# 🧠 Hermes Agent — Entegrasyon (Container modeli)

Videodaki "konuşarak kontrol edilen ajan" =
[**Nous Research — Hermes Agent**](https://github.com/nousresearch/hermes-agent).
Artık **compose'ta bir servis** olarak çalışır: redeploy'da otomatik kurulur ve
başlar. **SSH / elle kurulum YOK.** Beyni **Groq**.

```
            ┌──────────── PANELDEN SOHBET ────────────┐
            │                                          │
  SEN ─yaz→ PANEL (:8090, "Hermes ile Sohbet") ─HTTP→ HERMES servisi (:8642)
                                                         │  (Docker ağı içinden)
                                          ┌──────────────┴───────────────┐
                                          ▼                              ▼
                                  MoneyPrinterTurbo                 Panel API
                                  (video-generator:8080)           (ai-agent:8090)
```

---

## 1. Ne kurmuş oldun

`docker-compose.yaml` içinde **3 yeni parça**:
- **hermes** servisi → resmi `nousresearch/hermes-agent` image'ı, `gateway run`.
- **hermes-init** → ilk açılışta Groq modelini seçen `config.yaml`'ı yazar (varsa dokunmaz).
- **hermes_data** volume → ayarlar kalıcı.

Panel (ai-agent) Hermes'e `http://hermes:8642` ile **iç ağdan** ulaşır —
host.docker.internal / firewall derdi yok.

---

## 2. Senin yapman gereken tek şey: 2 env

Coolify → compose kaynağı → Environment Variables:

| Değişken | Değer |
|----------|-------|
| `HERMES_API_KEY` | Panel↔Hermes ortak parolası (sen belirle, gizli) — ör. `5GRnu_xb-...` |
| `GROQ_API_KEY` | Groq anahtarın (MPT ile aynı; zaten varsa yeniden girmene gerek yok) |
| `HERMES_ENABLED` | `true` (varsayılan zaten true) |

Sonra **Redeploy**. `video-hermes` container'ı açılır, panelde
**🤖 Hermes ile Sohbet → "bağlı"** olur.

> `HERMES_API_KEY` bir siteden alınmaz — uydurduğun bir paroladır. Hermes servisi
> bunu `API_SERVER_KEY` olarak kullanır, panel de aynı parolayla bağlanır.

---

## 3. Hermes video fabrikasını nasıl sürer

Hermes aynı Docker ağında olduğu için şu uçları doğrudan çağırabilir:

**MoneyPrinterTurbo'da video ürettir:**
```bash
curl -X POST http://video-generator:8080/api/v1/videos \
     -H "Content-Type: application/json" \
     -d '{"video_subject":"sabah rutini","video_aspect":"9:16"}'
```

**Panelden video listele / sil:**
```bash
curl http://ai-agent:8090/api/videos
curl -u admin:$PANEL_PASSWORD -X DELETE http://ai-agent:8090/api/videos/TASK_ID
```

Panelden Türkçe yazarsın → Hermes uygun çağrıyı yapar.

---

## 4. Panel API Referansı

| Method | Endpoint | Auth | Ne yapar |
|--------|----------|------|----------|
| GET | `/api/chat/status` | — | Hermes bağlı mı + neden |
| POST | `/api/chat` | 🔒 | Hermes'e mesaj gönder |
| GET/POST | `/api/social` | POST 🔒 | Sosyal hesaplar |
| GET | `/api/videos` | — | Video listesi |
| DELETE | `/api/videos/{id}` | 🔒 | Video sil |
| GET | `/api/auth/check` | 🔒 | Login doğrulama |

🔒 = `PANEL_PASSWORD` + giriş gerekir.

---

## 5. Telefondan kontrol (opsiyonel — Telegram)

Hermes container'ı `gateway run` ile mesajlaşma ağ geçidini de çalıştırır.
Telegram bağlamak istersen `video-hermes` container'ında bir kez:
```bash
docker exec -it video-hermes hermes gateway setup
```
(Telegram seç, bot token gir, kendi kullanıcına kısıtla.)

---

## 6. Sorun giderme

- Panel **"ulaşılamıyor"** → `video-hermes` container'ı ayakta mı? Coolify'da loguna bak.
- Panel **"bağlı değil / API anahtarı yanlış"** → `HERMES_API_KEY` Coolify'da dolu mu,
  iki tarafta da aynı mı (panel servisi onu hem ai-agent hem hermes'e veriyor).
- Hermes cevap vermiyor / model hatası → `video-hermes` logunda Groq hatası var mı bak;
  `hermes_data` volume'undaki `config.yaml` `provider: groq` / `default: llama-3.3-70b-versatile` mi.

---

## 7. Güvenlik

- Hermes servisi **internete açılmaz** (sadece `expose`, iç ağ). Panele login + `PANEL_PASSWORD` şart.
- `HERMES_API_KEY` ve `GROQ_API_KEY` repoya yazılmaz — sadece Coolify env'inde.
- (Opsiyonel) Hermes'e container yönetimi/self-heal yetkisi vermek istersen
  docker-socket-proxy üzerinden sınırlı erişim eklenebilir — varsayılanda kapalı.
