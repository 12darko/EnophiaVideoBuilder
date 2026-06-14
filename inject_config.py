"""
config.toml env enjeksiyonu
============================
Coolify env değişkenleri (kalıcı) → MoneyPrinterTurbo config.toml.
Her container açılışında çalışır; volume kaybolsa bile anahtarlar
env'den gelir. Mevcut UI ayarlarını KORUR (sadece verilen anahtarları
günceller, üstüne tam yazmaz).

Desteklenen env:
  PEXELS_API_KEY, PIXABAY_API_KEY, GEMINI_API_KEY,
  GEMINI_MODEL_NAME (vars: gemini-2.0-flash), VIDEO_SOURCE
"""

import os

CONFIG = "/MoneyPrinterTurbo/config_data/config.toml"


def main() -> None:
    try:
        import toml
    except Exception:
        print("[inject] 'toml' modulu yok — env enjeksiyonu atlandi")
        return

    try:
        data = toml.load(CONFIG) if os.path.exists(CONFIG) else {}
    except Exception as e:
        print(f"[inject] config.toml okunamadi ({e}), sifirdan olusturulacak")
        data = {}

    app = data.get("app") or {}

    pexels = os.environ.get("PEXELS_API_KEY", "").strip()
    pixabay = os.environ.get("PIXABAY_API_KEY", "").strip()
    gemini = os.environ.get("GEMINI_API_KEY", "").strip()
    source = os.environ.get("VIDEO_SOURCE", "").strip()

    applied = []
    if pexels:
        app["pexels_api_keys"] = [pexels]
        app.setdefault("video_source", "pexels")
        applied.append("pexels")
    if pixabay:
        app["pixabay_api_keys"] = [pixabay]
        applied.append("pixabay")
    if gemini:
        app["llm_provider"] = "gemini"
        app["gemini_api_key"] = gemini
        app.setdefault(
            "gemini_model_name",
            os.environ.get("GEMINI_MODEL_NAME", "gemini-2.0-flash"),
        )
        applied.append("gemini")
    if source:
        app["video_source"] = source
        applied.append(f"source={source}")

    if not applied:
        print("[inject] Env anahtari verilmemis — config.toml UI'dan yonetiliyor")
        return

    data["app"] = app
    try:
        with open(CONFIG, "w", encoding="utf-8") as f:
            toml.dump(data, f)
        print(f"[inject] Env anahtarlari config.toml'a islendi: {', '.join(applied)}")
    except Exception as e:
        print(f"[inject] config.toml yazilamadi: {e}")


if __name__ == "__main__":
    main()
