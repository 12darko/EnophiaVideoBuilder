# 🧠 Hermes Agent + Enophia Video Builder Entegrasyonu

Videodaki "terminalden konuşulan, hesaba girip işlem yapan" ajan
[**Nous Research — Hermes Agent**](https://github.com/nousresearch/hermes-agent).
Bu, sunucuyu yöneten **genel amaçlı** bir asistan (Claude Code / Devin muadili).

Bizim **Enophia Video Builder** ise tek amaçlı **video fabrikası**. İkisi yarışmaz —
**Hermes = operatör/beyin**, **Enophia = güvenli üretim bandı**.

```
SEN ──konuş──> HERMES (host'ta, her şeyi yapar)
                  │  HTTP
                  ▼
            ENOPHIA PANEL API (:8090)  ──> video üret / listele / sil
```

---

## 1. İki Ayrı Şey — Karıştırma

| | Hermes Agent | Enophia Video Builder |
|---|---|---|
| Nerede | **Host'a kurulur** (curl install) | Coolify'da **container** |
| Ne yapar | Her şey: shell, repo, firewall, hesap | Sadece video üretir/paylaşır |
| Yetki | Host'ta tam (güçlü + riskli) | Sandbox (güvenli) |
| Sen nasıl kullanırsın | Konuşarak (terminal/Telegram) | Otomatik + panel |

> **Enophia, Hermes'e muhtaç DEĞİL.** Kendi başına 7/24 çalışır. Hermes'i sadece
> "doğal dille komut vermek" istersen eklersin.

---

## 2. Hermes Kurulumu (host'ta)

```bash
# Linux/macOS/WSL2 sunucuda:
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```
Kurulumda bir LLM sağlayıcı API key'i ister (OpenRouter/OpenAI/Anthropic/Nous).
Detay: https://github.com/nousresearch/hermes-agent

---

## 3. Panele Erişim — 3 Senaryo (port derdi burada çözülür)

### A) Hermes host'ta → panel host-local (ÖNERİLEN, ekstra domain YOK)
`docker-compose.yaml`'de ai-agent altındaki satırı aç:
```yaml
    ports:
      - "127.0.0.1:8090:8090"   # sadece host, internete kapalı
```
Artık Hermes panele `http://127.0.0.1:8090` üzerinden ulaşır. **Domain/SSL/ekstra
public port gerekmez.** İnternete de açık değildir → güvenli.

### B) Sen tarayıcıdan açmak istersen → Coolify'da tek satır
ai-agent servisi → **Domains** alanına:
```
https://panel.senindomain.com:8090
```
yaz, Save. SSL otomatik. (DNS'e `panel` A kaydı ekle.) `PANEL_PASSWORD` koy!

### C) Hiç panel istemiyorsan
Bırak `expose` kalsın, hiçbir şey açma. Sistem otonom çalışmaya devam eder.

---

## 4. Hermes'e Verebileceğin Komutlar (örnek)

`PANEL_PASSWORD`'ü ayarladıysan, Hermes şu çağrıları yapar:

**"Enophia'da 'sabah rutini' konulu video üret ve paylaş":**
```bash
curl -u admin:$PANEL_PASSWORD -X POST http://127.0.0.1:8090/api/trigger \
     -H "Content-Type: application/json" -d '{"topic":"sabah rutini"}'
```

**"Üretilen videoları listele":**
```bash
curl http://127.0.0.1:8090/api/videos
```

**"Şu task'ı sil":**
```bash
curl -u admin:$PANEL_PASSWORD -X DELETE http://127.0.0.1:8090/api/videos/TASK_ID
```

**"Durumu söyle":**
```bash
curl http://127.0.0.1:8090/api/stats
```

> Hermes'e bir "skill" olarak bunları öğretirsen, artık düz Türkçe konuşursun:
> *"Enophia'da yeni motivasyon videosu üret"* → Hermes uygun curl'ü çalıştırır.

---

## 5. Panel API Referansı

| Method | Endpoint | Auth | Ne yapar |
|--------|----------|------|----------|
| GET | `/api/stats` | — | İstatistik + depolama |
| GET | `/api/videos` | — | Video listesi |
| GET | `/api/videos/{id}/file` | — | Videoyu indir/izle |
| GET | `/api/history` | — | Son üretim döngüleri |
| POST | `/api/trigger` | 🔒 | Üretim tetikle `{"topic": "..."}` (topic opsiyonel) |
| DELETE | `/api/videos/{id}` | 🔒 | Video sil |

🔒 = `PANEL_PASSWORD` + Basic Auth gerekir. Şifre boşsa bu uçlar kapalıdır (salt-okunur).

---

## 6. Güvenlik

- **Hermes host'ta tam yetkili** — yanlış komut sunucuyu bozabilir. Üretim sunucusunda
  dikkatli kullan; mümkünse ayrı/izole bir kullanıcıyla çalıştır.
- **Paneli internete açıyorsan** `PANEL_PASSWORD` + Coolify Basic Auth **şart**.
- En güvenli kurulum: panel **host-local** (Senaryo A), Hermes onu içeriden sürer,
  dışarıya hiç açılmaz.
