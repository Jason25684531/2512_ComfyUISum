#!/bin/bash
# ============================================
# TWCC GPU VM 啟動腳本
# ============================================
# 用途：透過 twccli 啟動 A100 GPU VM
# Cron 使用範例: 0 9 * * 1-5 /opt/studio/scripts/twcc_start_gpu.sh
#
# 注意：Cron 環境不載入 .bashrc，必須用絕對路徑
# ============================================

set -euo pipefail

# ============================================
# 載入環境變數
# ============================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${PROJECT_DIR}/.env.twcc"

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ 找不到 .env.twcc: $ENV_FILE"
    exit 1
fi

# 手動解析 .env 檔案（避免依賴 source）
while IFS='=' read -r key value; do
    # 跳過空行和註解
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    # 去除前後空白
    key=$(echo "$key" | xargs)
    value=$(echo "$value" | xargs)
    export "$key"="$value"
done < "$ENV_FILE"

# ============================================
# 驗證必要變數
# ============================================
: "${TWCC_API_KEY:?❌ TWCC_API_KEY 未設定}"
: "${TWCC_GPU_VM_ID:?❌ TWCC_GPU_VM_ID 未設定}"
TWCCLI_PATH="${TWCCLI_PATH:-/home/ubuntu/.local/bin/twccli}"

if [ ! -x "$TWCCLI_PATH" ]; then
    echo "❌ twccli 不存在或無執行權限: $TWCCLI_PATH"
    echo "   請先安裝: pip install twccli"
    exit 1
fi

# ============================================
# 啟動 GPU VM
# ============================================
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"
LOG_FILE="${PROJECT_DIR}/logs/twcc-schedule.log"
mkdir -p "$(dirname "$LOG_FILE")"

echo "[$TIMESTAMP] 🚀 啟動 GPU VM (ID: $TWCC_GPU_VM_ID)..."

export TWCC_API_KEY
if $TWCCLI_PATH ch vcs -sts ready -s "$TWCC_GPU_VM_ID"; then
    echo "[$TIMESTAMP] ✅ GPU VM 啟動指令已發送" | tee -a "$LOG_FILE"
else
    echo "[$TIMESTAMP] ❌ GPU VM 啟動失敗" | tee -a "$LOG_FILE"
    exit 1
fi
