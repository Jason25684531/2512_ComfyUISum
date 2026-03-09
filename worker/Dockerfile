FROM python:3.10-slim

WORKDIR /worker

# 安裝依賴（使用根目錄的統一 requirements.txt）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製共用模組（Worker 需要 shared.utils, shared.config_base, shared.database）
COPY shared/ shared/

# 複製 Worker 程式
COPY worker/src/ src/

# 複製 Workflow 定義檔
COPY ComfyUIworkflow/ ComfyUIworkflow/

# 設定 PYTHONPATH 以正確載入 shared 模組
ENV PYTHONPATH=/worker

# 啟動 Worker
CMD ["python", "src/main.py"]