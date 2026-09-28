# Storage Strategy

目前 runtime 使用 local filesystem storage，不啟動額外 object-storage service。

## Canonical paths

- STORAGE_DIR：storage/
- STORAGE_INPUT_DIR：storage/inputs/
- STORAGE_OUTPUT_DIR：storage/outputs/
- Workflow assets：ComfyUIworkflow/

Backend 與 Worker 透過 Compose mount 共用 storage/。job output receipt 儲存相對 output path，並由 shared/path_utils.py 驗證 root、traversal、absolute path 與 UNC path。

## Local configuration

~~~ini
STORAGE_DIR=./storage
STORAGE_OUTPUT_DIR=./storage/outputs
~~~

輸出服務只允許 storage root 內的相對路徑。不要把主機絕對路徑或 credential 寫入 job payload、資料庫或 repository。

## Future provider work

本 repository 目前沒有 active generic object-storage implementation；因此本 Change 不新增 provider abstraction，也不保留未使用的 provider branch。若未來需要 object storage，必須另立 OpenSpec change，先定義 caller、credential contract、Compose mount 與 API behavior，再加入測試。

## Verification

~~~powershell
docker compose --env-file .env.local config
python -m pytest tests/unit/test_comfy_paths.py tests/integration/test_reconciliation.py -q
~~~
