# TWCC HFS COS Mount Guide

本文件定義 TWCC canonical 雲端邊界內，HFS 與 COS 的受控掛載方式。實際主機名稱必須來自 `.env.twcc`、部署 inventory 或祕密管理，不得寫死成 repo literal IP。

## 邊界角色

- `TWCC_GATEWAY_HOST`: CPU gateway / Base VM 對外角色名稱
- `TWCC_GPU_NODE_HOST`: GPU worker / ComfyUI 節點角色名稱
- `TWCC_BASE_HOST`: 供操作文件描述 Base VM 入口時使用的 placeholder

## 建議掛載點

| 類型 | 建議掛載點 | 來源 | 用途 |
|------|------------|------|------|
| HFS | `/mnt/twcc/hfs` | TWCC HFS volume | 長期模型、共用 workflow 素材、批次輸入輸出 |
| COS | `s3://<TWCC_COS_BUCKET>` | TWCC COS / S3 API | 成品輸出、跨 VM 同步、異地備份 |

## `.env.twcc` 對應欄位

```dotenv
ENV_CONTRACT_FILE=./.env.twcc
TWCC_GATEWAY_HOST=<TWCC_GATEWAY_HOST>
TWCC_GPU_NODE_HOST=<TWCC_GPU_NODE_HOST>
S3_ENDPOINT=https://cos.twcc.ai
S3_BUCKET=<TWCC_COS_BUCKET>
STORAGE_OUTPUT_DIR=/mnt/twcc/hfs/studio/outputs
MODEL_PATH=/mnt/twcc/hfs/models
```

## 操作原則

- `docker-compose.base.yml` 是 `twcc-base-vm` 的 canonical compose 入口。
- `deployment_matrix.yaml` 與 `docs/DEPLOYMENT_MATRIX.md` 是角色邊界與 validation gates 的單一真實來源。
- `nginx/nginx.twcc.conf` 是 TWCC 對外入口的受控設定。
- `ComfyUIworkflow/` 可以作為工作流內容來源，但不是 TWCC canonical 邊界的部署入口。
- 若要同步模型或輸出到 COS，請以 `.env.twcc` 提供 bucket/endpoint，不要把雲端位址硬寫在 compose、shell script 或 README 內。

## 驗證清單

- `.env.twcc` 或部署注入中已提供 `ENV_CONTRACT_FILE`、`S3_*` 與 `TWCC_*` placeholder
- 掛載點位於受控 HFS 目錄，而不是任意主機絕對路徑
- 對外文件只出現 placeholder / inventory 名稱，不出現固定 IP literal
