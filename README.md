# 專案說明書

## 專案架構
- 前端 (Frontend): 設計師的操作介面
- 後端 (Backend): Flask API 服務
- Worker: 任務處理器
- ComfyUIworkflow: ComfyUI 的原始腳本
- Storage: 存算分離的核心共享區

## 資料夾結構
```
├── .env                     # [設定] 全域環境變數 (ComfyUI IP, Redis 密碼, API Keys)
├── .gitignore               # [設定] Git 忽略檔 (忽略 venv, storage, .env)
├── docker-compose.yml       # [核心] 啟動腳本 (一次開啟 Web, API, Redis, Worker)
├── README.md                # [文件] 專案說明書
│
├── openspec/                # [AI 指揮中心] 存放給 Cursor/Windsurf 看的規格書
│   ├── project.md           # 專案架構與技術堆疊定義
│   └── changes/             # 每次衝刺的任務清單 (e.g., phase-1-mvp)
│
├── frontend/                # [前端 Frontend] 設計師的操作介面
│   ├── index.html           # 主頁面 (輸入 Prompt, 上傳圖片的 UI)
│   ├── style.css            # 介面樣式
│   ├── app.js               # 前端邏輯 (呼叫後端 API, 更新進度條)
│   └── nginx.conf           # (未來) 上線時用的 Nginx 設定檔
│
├── backend/                 # [後端 Master] 接待員：Flask API 服務
│   ├── Dockerfile           # 定義 API 容器環境
│   ├── requirements.txt     # API 需要的 Python 套件 (Flask, Redis...)
│   └── src/
│       ├── app.py           # 程式入口 (Entry Point)
│       ├── routes.py        # 定義路徑 (POST /generate, GET /status/<id>)
│       └── utils.py         # 工具函式 (驗證輸入資料)
│
├── worker/                  # [後端 Worker] 二廚：任務處理器
│   ├── Dockerfile           # 定義 Worker 容器環境
│   ├── requirements.txt     # Worker 需要的 Python 套件 (Requests, WebSocket...)
│   └── src/
│       ├── main.py          # 程式入口 (無限迴圈監聽 Redis)
│       ├── comfy_client.py  # 負責跟 ComfyUI 溝通 (WebSocket 連線/API 發送)
│       └── json_parser.py   # 負責修改 JSON 參數 (把 Prompt 填入 workflow)
│
├── ComfyUIworkflow/         # [資產 Assets] ComfyUI 的原始腳本
│   ├── txt2img_sdxl.json    # 文生圖樣板
│   ├── img2video_svd.json   # 圖生影片樣板
│   └── ...
│
└── storage/                 # [資料 Data] 存算分離的核心共享區 (模擬 NAS/HFS)
    ├── inputs/              # 設計師上傳的參考圖 (Init Images)
    ├── outputs/             # ComfyUI 算完的成品 (Result Images/Videos)
    └── models/              # (選用) 用於掛載模型檔案
```

## 啟動方式
1. 安裝 Docker 與 Docker Compose
2. 執行 `docker-compose up` 啟動所有服務

