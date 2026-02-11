#!/bin/sh
# ============================================
# StudioCore Frontend - Docker Entrypoint
# 用途：啟動前透過 envsubst 注入環境變數到 config.js
# ============================================
set -e

CONFIG_TEMPLATE="/usr/share/nginx/html/config.js.template"
CONFIG_OUTPUT="/usr/share/nginx/html/config.js"

# 如果存在 template 檔案，使用 envsubst 注入環境變數
if [ -f "$CONFIG_TEMPLATE" ]; then
    echo "[entrypoint] Injecting environment variables into config.js..."
    envsubst < "$CONFIG_TEMPLATE" > "$CONFIG_OUTPUT"
    echo "[entrypoint] config.js generated successfully."
else
    echo "[entrypoint] No config.js.template found, using default config.js."
fi

# 啟動 Nginx
echo "[entrypoint] Starting Nginx..."
exec nginx -g 'daemon off;'
