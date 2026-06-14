#!/bin/sh
# ============================================================
# video-generator entrypoint
# config.toml'u kalıcı volume'e (config_data) bağlar ki
# UI'dan girilen API key'ler (Pexels vb.) restart/redeploy
# sonrası SİLİNMESİN.
# ============================================================
set -e

PERSIST_DIR=/MoneyPrinterTurbo/config_data
CONFIG_LINK=/MoneyPrinterTurbo/config.toml
EXAMPLE=/MoneyPrinterTurbo/config.example.toml

mkdir -p "$PERSIST_DIR"

# İlk çalıştırma: kalıcı dizinde config yoksa örnekten/mevcuttan oluştur
if [ ! -f "$PERSIST_DIR/config.toml" ]; then
    if [ -f "$CONFIG_LINK" ] && [ ! -L "$CONFIG_LINK" ]; then
        cp "$CONFIG_LINK" "$PERSIST_DIR/config.toml"
    elif [ -f "$EXAMPLE" ]; then
        cp "$EXAMPLE" "$PERSIST_DIR/config.toml"
    else
        touch "$PERSIST_DIR/config.toml"
    fi
    echo "[entrypoint] Kalıcı config.toml oluşturuldu: $PERSIST_DIR/config.toml"
fi

# config.toml -> kalıcı dosyaya symlink (MPT kök yoldan okur)
rm -f "$CONFIG_LINK"
ln -sf "$PERSIST_DIR/config.toml" "$CONFIG_LINK"
echo "[entrypoint] config.toml -> $PERSIST_DIR/config.toml (kalıcı)"

# supervisord'u devral
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
