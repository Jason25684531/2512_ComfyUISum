# Phase 7 壓力測試套件

## 目錄結構

```
tests/
├── assets/                 # 測試用圖片素材
│   ├── small_512.png      # 512x512 測試圖片
│   ├── medium_1024.png    # 1024x1024 測試圖片
│   └── large_2048.png     # 2048x2048 測試圖片
├── test_prompts.json      # 20 組測試 Prompt
├── locustfile.py          # Locust 壓力測試腳本
└── README.md              # 本說明文件

## 測試素材準備

### 圖片素材
請手動準備以下三張測試圖片並放入 `assets/` 目錄：
- `small_512.png` - 512x512 像素
- `medium_1024.png` - 1024x1024 像素
- `large_2048.png` - 2048x2048 像素

或使用以下命令自動生成純色測試圖片 (需安裝 Pillow)：

```bash
python -c "from PIL import Image; Image.new('RGB', (512, 512), 'blue').save('tests/assets/small_512.png')"
python -c "from PIL import Image; Image.new('RGB', (1024, 1024), 'green').save('tests/assets/medium_1024.png')"
python -c "from PIL import Image; Image.new('RGB', (2048, 2048), 'red').save('tests/assets/large_2048.png')"
```

## 執行測試

### 1. 安裝 Locust
```bash
pip install locust
```

### 2. 啟動測試
```bash
cd d:\01_Project\2512_ComfyUISum
locust -f tests/locustfile.py --host=http://localhost:5000
```

### 3. 開啟 Web UI
瀏覽器訪問 http://localhost:8089

### 4. 測試場景

#### 冒煙測試 (Smoke Test)
- Users: 1
- Spawn Rate: 1
- Duration: 1m
- 目的：驗證基本功能

#### 負載測試 (Load Test)
- Users: 10
- Spawn Rate: 2
- Duration: 5m
- 目的：模擬日常使用

#### 壓力測試 (Stress Test)
- Users: 50+
- Spawn Rate: 5
- Duration: 10m
- 目的：找出系統瓶頸

## 監控指標

執行測試期間，同時監控以下指標：

### Backend
- API 響應時間
- 錯誤率 (500/404)
- 請求吞吐量 (RPS)

### Redis
- 佇列深度 (`LLEN job_queue`)
- 記憶體使用量

### Worker
- GPU VRAM 使用率
- 任務處理時間
- ComfyUI 狀態

### MySQL
- 連接池使用率
- 慢查詢日誌

## 參考命令

```bash
# 監控 Redis 佇列
redis-cli LLEN job_queue

# 檢查 MySQL 連接數
mysql -u root -p -e "SHOW PROCESSLIST;"

# 查看 GPU 使用率 (Linux)
nvidia-smi

# 查看容器資源使用
docker stats
```
