FROM python:3.10-slim

WORKDIR /worker

# 安裝依賴（不保留緩存）
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 複製 Worker 程式
COPY src/ src/

# 啟動 Worker
CMD ["python", "src/main.py"]