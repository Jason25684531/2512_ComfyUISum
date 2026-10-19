# 前端導航與部署

`/` 與 `/dashboard.html` 直接進入 Prompt Hub，不需要登入。`index.html`、舊 `login.html`、`profile.html` 維持 302 導向 `/dashboard.html`；前端不再包含登入或會員元件，也不呼叫 `/api/me`。

| Hash 路由 | 畫面 |
|---|---|
| `#/home` | 探索、提示詞入口、14 個工具與最近作品 |
| `#/image/<tool_id>` | 圖片工具；預設 `text_to_image` |
| `#/video/<tool_id>` | 影片工具；預設 `ltx_i2v` |
| `#/avatar` | 數位人像 |
| `#/gallery` | 全站共享作品庫，預設只顯示完成任務 |

未知工具回到該類別預設工具。瀏覽器上一頁、重新整理與深層連結均由 hash 還原，不用 `localStorage.currentView`。

首頁與工作區共用工具設定和草稿。比例為 16:9、9:16、2:3 的工具支援子集，解析度為 720P／1080P；GPT 只有 1080P，隱藏解析度列；放大、retake 等依輸入尺寸的工具隱藏比例與解析度。首頁條件齊全直接生成，缺檔則開工作區提示；BBox 與多角度編輯器留在工作區。

頂列「我的佇列」用 `GET /api/queue/me` 還原最近 24 小時最多 50 筆任務。`studio_tc` 是自動核發的 HttpOnly cookie，伺服器只儲存 HMAC 標籤，顯示 `U-xxxxxx` 臨時代碼。任務依工具從舊到新編號；抽屜開啟或有進行中任務時每 5 秒更新，個別任務每 2 秒更新進度、最多 40 分鐘。清除 cookie、無痕或換瀏覽器後無法還原原佇列，作品仍在作品庫。佇列查詢失敗可重試，不影響生成。

`POST /api/cancel/<job_id>` 比對 cookie 身分，非本人或舊 `IP#` 任務回 403。取消先顯示「取消中…」，待 worker 確認 ComfyUI 已中斷才顯示「已取消」。Worker 以 prompt_id 刪除 pending／中斷 running，不影響其他 prompt。結果舞台單張滿版 contain、多張格狀，點選可放大；下載、再生成與原生全螢幕按鈕疊於媒體上，缺檔時移除下載與全螢幕。

`GET /api/history` 不使用 cookie／使用者篩選，所有人看到同一份作品與 prompt。預設 `status=completed`，可切換 `all`、`running`（含 queued）、`failed`（含 cancelled），`offset` 預設 0、`limit` 預設 24、上限 100。回應只有 `items/total/offset/limit`，不提供舊 `history/jobs` 欄位。所有字串由後端 HTML 編碼，前端以 `textContent` 顯示，只接受 `/outputs/` 下的安全 basename。

作品對所有 Web 使用者可見；LINE Bot 來源（dispatch payload 的 `user_label=line`）不列入 Web 作品庫、首頁最近作品或分頁總數。LINE 的檔案、推播與下載流程不變。作品庫不提供刪除。資料來源為既有 MySQL `jobs/job_outputs/job_dispatches`，migration 004 加入來源標籤索引。MySQL 無法使用或記錄功能關閉時回受控 503，畫面顯示錯誤與重試。手動清理 storage 後，舊任務紀錄保留；缺檔媒體顯示提示並移除無效下載連結。

## local-dev 與 TWCC 部署前提

- 後端需要 `JOB_OBSERVABILITY_ENABLED=true`，並可連線到現有 MySQL；預設程式設定為 false，compose 已開啟。
- Phase 1 與 Phase 2 使用相同程式碼；部署 TWCC 時需另確認 twcc-base-vm 的 MySQL 連線與上述開關。
- 沒有新增環境變數；HTTPS 設定 `SESSION_COOKIE_SECURE=true`，輪替 `SECRET_KEY` 會讓既有佇列對應失效。
- 先套用 migration 004，再部署 worker，最後部署 backend／frontend；ComfyUI 最低 0.34.2。1080P 約兩倍像素，失敗可改 720P 重試；未傳 `resolution` 的 LINE／API 呼叫維持舊尺寸。
- repo 找不到 `deployment_matrix.yaml` 與 `validate_deployment_matrix.py`，無法執行矩陣驗證；部署負責人需在外部拓撲文件確認 MySQL 與開關。
