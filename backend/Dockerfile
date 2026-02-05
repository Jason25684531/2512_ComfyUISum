# ==========================================
# Backend Dockerfile - Optimized for K8s
# ==========================================
FROM python:3.10-slim

WORKDIR /app

# 設置 PYTHONPATH 以支持 shared 模組導入
ENV PYTHONPATH=/app

# 安裝系統依賴 (如果需要編譯某些 Python 包)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 複製並安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製共用模組 (關鍵：Backend 依賴 shared/)
COPY shared/ shared/

# 複製 Backend 應用程式
COPY backend/src/ src/
COPY backend/Readme/ Readme/

# 暴露 Flask 端口
EXPOSE 5001

# 健康檢查 (確保服務可用)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5001/health', timeout=3)" || exit 1

# 啟動 Backend API
CMD ["python", "src/app.py"]