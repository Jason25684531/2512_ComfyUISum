FROM python:3.10-slim

WORKDIR /app

# 安裝依賴（不保留緩存）
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式
COPY src/ src/

# 健康檢查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/health')" || exit 1

# 啟動應用
CMD ["python", "src/app.py"]