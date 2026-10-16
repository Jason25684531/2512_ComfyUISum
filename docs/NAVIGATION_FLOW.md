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

工作區共用一份表單、結果舞台與本工具紀錄。圖片沿用既有 generate payload；影片沿用首尾幀、影片上傳與 retake 時段，Avatar 沿用圖片與音訊 base64。BBox 與多角度相機仍由原有編輯器產生 payload。輪詢每 2 秒一次、最多 40 分鐘；暫時斷線持續重試，取消成功後停止輪詢，失敗與逾時可保留輸入重試。

`GET /api/history` 不使用 cookie／使用者篩選，所有人看到同一份作品與 prompt。預設 `status=completed`，可切換 `all`、`running`（含 queued）、`failed`（含 cancelled），`offset` 預設 0、`limit` 預設 24、上限 100。回應只有 `items/total/offset/limit`，不提供舊 `history/jobs` 欄位。所有字串由後端 HTML 編碼，前端以 `textContent` 顯示，只接受 `/outputs/` 下的安全 basename。

作品對所有 Web 使用者可見；LINE Bot 來源（dispatch payload 的 `user_label=line`）不列入 Web 作品庫、首頁最近作品或分頁總數。LINE 的檔案、推播與下載流程不變。作品庫不提供刪除。資料來源為既有 MySQL `jobs/job_outputs/job_dispatches`，沒有 migration。MySQL 無法使用或記錄功能關閉時回受控 503，畫面顯示「作品載入失敗」與重試。手動清理 storage 後，舊任務紀錄保留；缺檔媒體顯示提示並移除無效下載連結。

## local-dev 與 TWCC 部署前提

- 後端需要 `JOB_OBSERVABILITY_ENABLED=true`，並可連線到現有 MySQL；預設程式設定為 false，compose 已開啟。
- Phase 1 與 Phase 2 使用相同程式碼；部署 TWCC 時需另確認 twcc-base-vm 的 MySQL 連線與上述開關。
- 沒有新增環境變數，不重啟 worker／ComfyUI，不改 GPU、VRAM 或批次輸出行為。
- repo 找不到 `deployment_matrix.yaml` 與 `validate_deployment_matrix.py`，無法執行矩陣驗證；部署負責人需在外部拓撲文件確認 MySQL 與開關。
