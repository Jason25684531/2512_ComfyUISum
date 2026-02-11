# ============================================
# StudioCore Frontend - Dockerfile
# Base: nginx:alpine (輕量級靜態檔案服務)
# 功能：靜態檔案 + API 反向代理 + 環境變數注入
# ============================================

FROM nginx:alpine

LABEL maintainer="StudioCore Team"
LABEL description="StudioCore Frontend - Nginx + Static Files"

# --- 安裝 envsubst（已包含在 alpine 的 gettext 中）---
RUN apk add --no-cache gettext

# --- 移除預設 Nginx 設定 ---
RUN rm -f /etc/nginx/conf.d/default.conf

# --- 複製 Nginx 設定 ---
COPY nginx.conf /etc/nginx/conf.d/default.conf

# --- 複製靜態檔案 ---
COPY *.html       /usr/share/nginx/html/
COPY *.css        /usr/share/nginx/html/
COPY *.js         /usr/share/nginx/html/
COPY front/       /usr/share/nginx/html/front/
COPY image/       /usr/share/nginx/html/image/

# --- 複製 entrypoint（環境變數注入）---
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# --- 預設環境變數（可透過 K8s ConfigMap/Secret 覆蓋）---
ENV API_BASE_URL=""
ENV FEATURE_FLAGS=""

# --- 健康檢查 ---
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost/healthz || exit 1

# --- 暴露端口 ---
EXPOSE 80

# --- 啟動指令 ---
ENTRYPOINT ["/docker-entrypoint.sh"]
