# Archive 資料夾

此資料夾包含已封存的舊版配置檔案，這些檔案已被 `docker-compose.unified.yml` 整合取代。

## 封存檔案清單

### docker-compose.yml.bak
- **原用途**: 生產環境全容器化部署
- **封存原因**: 功能已被 `docker-compose.unified.yml` 的 `linux-prod` profile 取代
- **封存日期**: 2026-02-13

### docker-compose.dev.yml.bak
- **原用途**: 開發環境配置（僅啟動 MySQL + Redis，Backend/Worker 本地運行）
- **封存原因**: 功能已被 `docker-compose.unified.yml` 的 `windows-dev` / `linux-dev` profile 取代
- **封存日期**: 2026-02-13

## 使用說明

**推薦使用**: `docker-compose.unified.yml`

```bash
# Windows 開發
docker-compose -f docker-compose.unified.yml --profile windows-dev up -d

# Linux 開發
docker-compose -f docker-compose.unified.yml --profile linux-dev up -d

# Linux 生產
docker-compose -f docker-compose.unified.yml --profile linux-prod up -d

# 僅基礎設施（MySQL + Redis）
docker-compose -f docker-compose.unified.yml up -d redis mysql
```

## 恢復舊版配置

如需使用舊版配置，可將 `.bak` 檔案複製回專案根目錄並重新命名：

```bash
# 恢復開發環境配置
cp archive/docker-compose.dev.yml.bak docker-compose.dev.yml

# 使用
docker-compose -f docker-compose.dev.yml up -d
```

⚠️ **注意**: 不建議恢復舊版配置，統一配置檔案提供更好的維護性和靈活性。
