# ==========================================
# Worker Dockerfile - Optimized for K8s
# ==========================================
FROM python:3.10-slim

WORKDIR /app

# 設置 PYTHONPATH 以支持 shared 模組導入
ENV PYTHONPATH=/app

# 安裝系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# 複製並安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ComfyUIworkflow /app/ComfyUIworkflow

COPY worker/src /app/src

# 複製共用模組 (關鍵：Worker 依賴 shared/)
COPY shared/ shared/

# 複製 Worker 應用程式
COPY worker/src/ src/

# Worker 不需要暴露端口 (純消費者)

# 啟動 Worker 主迴圈
CMD ["python", "src/main.py"]