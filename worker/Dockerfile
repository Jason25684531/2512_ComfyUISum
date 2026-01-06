FROM python:3.10-slim

WORKDIR /worker

# 安裝依賴（使用根目錄的統一 requirements.txt）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製 Worker 程式
COPY worker/src/ src/

# 啟動 Worker
CMD ["python", "src/main.py"]