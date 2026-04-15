# Environment Boundary Guide

本文件是 `environment-spec` 的實作入口，對應 [environment_boundary_manifest.json](../environment_boundary_manifest.json)。

## Canonical 邊界

| 環境 | Canonical 資產 | Env 契約 | 說明 |
|------|----------------|----------|------|
| 本地 | `docker-compose.yml`、`.env.local`、`ComfyUIworkflow/` | `.env.local` | 本地開發、WSL/Windows Compose 與工作流調整都以這組為準。 |
| TWCC | `docker-compose.unified.yml`、`nginx/`、`docs/TWCC_HFS_COS_Mount_Guide.md` | `.env.twcc` 或部署注入 | 雲端部署入口、對外反向代理與 HFS/COS 掛載說明都以這組為準。 |

## 受治理範圍

`environment_boundary_manifest.json` 將檔案分成三類：

- `governed_paths.common`: 所有環境都要遵守的規劃、README、env contract 範例與載入邏輯。
- `governed_paths.local`: 只屬於本地 canonical 邊界或本地相容腳本的檔案。
- `governed_paths.twcc`: TWCC 雲端資產、長期維護文件與雲端 worker 啟動模板。

以下檔案仍會被治理，但不屬於任何 canonical 邊界：

- `docker-compose.base.yml`
- `docker-compose.dev.yml`
- `docker-compose.dev-s3.yml`
- `ComfyUIworkflow_Windows/`
- `.env.unified.example`

以下資產已明確視為 deprecated，不得再當成正式環境輸入或長期維護基線：

- `openspec/specs/project.md`
- `*.backup`
- 任何殘留的 `/k8s`、Helm chart 或 Kubernetes manifest

## Env 契約

- 本地 canonical 指令：`docker compose -f docker-compose.yml --env-file .env.local up -d`
- TWCC canonical 指令：`docker compose -f docker-compose.unified.yml --env-file .env.twcc --profile linux-prod up -d`
- Python 直接啟動時，請顯式設定 `STUDIO_ENV_FILE=.env.local` 或 `STUDIO_ENV_FILE=.env.twcc`
- `shared/utils.py` 目前支援 `STUDIO_ENV_FILE`、`STUDIO_ENV`、`.env.local`、`.env` 的顯式/相容載入順序

## 維護腳本

- 統一維護入口為 `scripts/maintenance.sh`
- 腳本會優先依 `STUDIO_ENV_FILE` 或 `STUDIO_ENV` 判定環境；若未顯式指定，則依 env contract 與執行環境訊號自動判定
- 若無法明確區分 local / twcc，腳本會 fail closed 並停止清理
- local 模式只清理可重建快取與暫存；twcc 模式只修正 `frontend/` 權限並清理 Docker dangling images

## 禁止事項

- 受治理檔案不得硬編碼任何 TWCC gateway IP literal
- 本地文件不得把 `docker-compose.unified.yml` 或 `nginx/` 當成 canonical 本地輸入
- TWCC 文件不得把 `docker-compose.yml` 或 `ComfyUIworkflow/` 當成正式雲端邊界

## 驗證

使用以下指令檢查邊界是否仍符合規範：

```bash
python scripts/validate_environment_boundary.py --environment local --env-file .env.local
python scripts/validate_environment_boundary.py --environment twcc --env-file .env.twcc --format json
```

驗證工具只會掃描 manifest allowlist 內的 repo 路徑，並在輸出中將所有字串欄位做安全轉義。