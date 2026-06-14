"""
config.toml env enjeksiyonu
============================
Coolify env değişkenleri (kalıcı) → MoneyPrinterTurbo config.toml.
Her container açılışında çalışır; config_data volume kaybolsa bile
anahtarlar env'den gelir. Mevcut UI ayarlarını KORUR (merge).

Video kaynakları:  PEXELS_API_KEY, PIXABAY_API_KEY, COVERR_API_KEY
                   VIDEO_SOURCE (pexels | pixabay | coverr)
LLM sağlayıcılar:  GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY
                   <PROVIDER>_MODEL_NAME (ör. GROQ_MODEL_NAME)
                   MPT_LLM_PROVIDER (hangi sağlayıcı aktif olsun — opsiyonel)
"""

import os

CONFIG = "/MoneyPrinterTurbo/config_data/config.toml"

# env değişkeni -> config.toml [app] alanı (liste tipi)
VIDEO_KEYS = {
    "PEXELS_API_KEY": "pexels_api_keys",
    "PIXABAY_API_KEY": "pixabay_api_keys",
    "COVERR_API_KEY": "coverr_api_keys",
}

# provider -> (env_var, api_key_field, model_field, default_model)
LLM_PROVIDERS = {
    "gemini": ("GEMINI_API_KEY", "gemini_api_key", "gemini_model_name", "gemini-2.0-flash"),
    "groq": ("GROQ_API_KEY", "groq_api_key", "groq_model_name", "llama-3.3-70b-versatile"),
    "openai": ("OPENAI_API_KEY", "openai_api_key", "openai_model_name", "gpt-4o-mini"),
    "deepseek": ("DEEPSEEK_API_KEY", "deepseek_api_key", "deepseek_model_name", "deepseek-chat"),
}


def main() -> None:
    try:
        import toml
    except Exception:
        print("[inject] 'toml' modulu yok — env enjeksiyonu atlandi")
        return

    try:
        data = toml.load(CONFIG) if os.path.exists(CONFIG) else {}
    except Exception as e:
        print(f"[inject] config.toml okunamadi ({e}), sifirdan")
        data = {}

    app = data.get("app") or {}
    applied = []

    # ── Video kaynak anahtarları ─────────────────────────────
    for env, field in VIDEO_KEYS.items():
        val = os.environ.get(env, "").strip()
        if val:
            app[field] = [val]
            applied.append(env.lower())

    source = os.environ.get("VIDEO_SOURCE", "").strip()
    if source:
        app["video_source"] = source
        applied.append(f"source={source}")
    elif os.environ.get("PEXELS_API_KEY", "").strip():
        app.setdefault("video_source", "pexels")

    # ── LLM sağlayıcılar ─────────────────────────────────────
    provided = []
    for prov, (env, akey, mkey, defmodel) in LLM_PROVIDERS.items():
        val = os.environ.get(env, "").strip()
        if val:
            app[akey] = val
            model = os.environ.get(f"{prov.upper()}_MODEL_NAME", "").strip() or defmodel
            app.setdefault(mkey, model)
            provided.append(prov)
            applied.append(env.lower())

    # Aktif sağlayıcı: MPT_LLM_PROVIDER varsa o, yoksa verilen ilk anahtar
    chosen = os.environ.get("MPT_LLM_PROVIDER", "").strip().lower()
    if chosen:
        app["llm_provider"] = chosen
    elif provided:
        app["llm_provider"] = provided[0]

    if not applied:
        print("[inject] Env anahtari verilmemis — config.toml UI'dan yonetiliyor")
        return

    data["app"] = app
    try:
        with open(CONFIG, "w", encoding="utf-8") as f:
            toml.dump(data, f)
        print(
            f"[inject] config.toml'a islendi: {', '.join(applied)} | "
            f"llm_provider={app.get('llm_provider', '?')}"
        )
    except Exception as e:
        print(f"[inject] config.toml yazilamadi: {e}")


if __name__ == "__main__":
    main()
