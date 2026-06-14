# 🌐 Coolify Deploy + Domain Bağlama (Hızlı Kılavuz)

Bu repo **kendi başına** Coolify'a deploy edilebilir — MoneyPrinterTurbo build sırasında
otomatik klonlanır, elle dosya kopyalamaya gerek yoktur.

---

## 1. DNS Kaydı

Domain sağlayıcında bir **A kaydı** ekle:

| Tip | Ad | Değer |
|-----|-----|-------|
| A | `video` | `VPS_IP_ADRESI` |

Sonuç: `video.senindomain.com` → VPS.

---

## 2. Coolify'da Kaynak Oluştur

1. **Coolify Dashboard → Projects → (proje) → + Add New Resource**
2. **Public Repository** (private ise GitHub App ile bağla) seç
3. Repo URL'si: `https://github.com/KULLANICIADIN/BU_REPO.git`
4. Branch: `main`
5. Build Pack: **Docker Compose** (otomatik algılanır)
6. **Save**

> Otomatik deploy: Coolify → resource → **Webhooks** veya GitHub App ile
> her `git push`'ta otomatik yeniden deploy aktifleştirilebilir.

---

## 3. Environment Variables

Resource → **Environment Variables** sekmesine `.env.example`'daki değişkenleri gir.
**Minimum zorunlu:**

```env
LLM_PROVIDER=gemini
LLM_API_KEY=AIza...
CONTENT_LANGUAGE=tr
CONTENT_NICHE=motivation
```

Sosyal medya ve bildirim anahtarlarını ihtiyacına göre ekle. **Hepsi Coolify
tarafından şifreli saklanır — repoya `.env` koymayın** (`.gitignore` zaten engelliyor).

---

## 4. Domain + SSL (API'yi domaine bağlama)

1. Resource'ta **video-generator** servisine tıkla
2. **Domains / FQDN** alanına gir:
   ```
   https://video.senindomain.com:8501
   ```
   - `:8501` → Streamlit WebUI portu. Coolify Traefik'e bu portu **iç** yönlendirme
     olarak verir; dışarıda port yazmana gerek kalmaz.
3. **Save** → Let's Encrypt SSL otomatik aktifleşir.

> ⚠️ **Port `:8501`'i yazmayı unutma**, yoksa 502 Bad Gateway alırsın.

### FastAPI (8080) hakkında
- 8080 backend portu yalnızca `expose` edilmiştir → **sadece iç ağdan** erişilir.
- ai-agent ona `http://video-generator:8080` üzerinden bağlanır.
- **Güvenlik için 8080'i domaine bağlama.** Dışarıdan API erişimi istiyorsan ayrı bir
  FQDN (`https://api.senindomain.com:8080`) tanımlayabilirsin ama önerilmez.

---

## 5. 🔒 UI'a Şifre Koy (ZORUNLU güvenlik adımı)

Streamlit UI'da kimlik doğrulama yoktur — şifresiz açık bırakırsan **herkes panele girip
API anahtarlarını harcayabilir**. Coolify Basic Auth ekle:

1. video-generator servisi → **Advanced** (veya **Settings**)
2. **Basic Authentication / HTTP Auth** bölümünü aç
3. Kullanıcı adı + şifre belirle → **Save** → Redeploy

> Coolify dışında düz Traefik kullanıyorsan, `video-generator` servisine
> `traefik.http.middlewares.auth.basicauth.users` label'ı ile aynısını yaparsın.

---

## 6. Deploy + config.toml

1. **Deploy** → build logunu izle (video-generator ~5-10 dk, ai-agent ~5-8 dk)
2. Her iki container **Running** olunca `https://video.senindomain.com`'a gir
3. Sol panelden **Pexels/Pixabay API key** + **LLM** ayarlarını gir, kaydet
4. config.toml'un kalıcılığı için Coolify **Persistent Storage**'da
   `/MoneyPrinterTurbo/config_data` zaten volume olarak bağlı.

---

## 7. Doğrulama

```bash
# Agent logları (Coolify UI → ai-agent → Logs, veya SSH):
docker logs -f video-agent --tail 100
```
Loglarda `🟢 Agent aktif` ve `📅 ... sonraki çalışma → ...` satırlarını görmelisin.

İlk videoyu hemen test etmek için env'e `AGENT_RUN_ON_START=true` ekleyip redeploy et.

---

## Mimari Özet

```
GitHub repo ──push──> Coolify ──build──> ┌─ video-generator (MPT klonlanır, 8501/8080)
                                          ├─ ai-agent (7/24 otonom)
                                          └─ docker-socket-proxy (salt-okunur log)
                                          Traefik → https://video.domain.com (Basic Auth)
```
