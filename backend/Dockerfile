FROM python:3.10-slim

WORKDIR /app

# 安裝依賴（使用根目錄的統一 requirements.txt）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製共用模組（Backend 和 Worker 都需要）
COPY shared/ shared/
COPY migrations/ migrations/
COPY scripts/migrate_database.py scripts/migrate_database.py

# 複製應用程式（保留 backend/src/ 層級，與本地路徑一致）
# app.py 用 ../../frontend 計算前端目錄，需要 /app/backend/src/app.py 結構
COPY backend/src/ backend/src/

# 複製前端靜態檔案（供 Flask 直接提供）
COPY frontend/ frontend/

# 設定 PYTHONPATH 以正確載入 shared 模組
ENV PYTHONPATH=/app

# 健康檢查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/health')" || exit 1

# 啟動應用
CMD ["sh", "-c", "python scripts/migrate_database.py && python backend/src/app.py"]
