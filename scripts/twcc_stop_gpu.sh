#!/bin/bash
# ============================================
# TWCC GPU VM 停止腳本（含安全檢查）
# ============================================
# 用途：透過 twccli 停止 A100 GPU VM
# Cron 使用範例: 0 18 * * 1-5 /opt/studio/scripts/twcc_stop_gpu.sh
#
# 安全機制：關機前檢查是否有進行中任務
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

while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    key=$(echo "$key" | xargs)
    value=$(echo "$value" | xargs)
    export "$key"="$value"
done < "$ENV_FILE"

# ============================================
# 驗證必要變數
# ============================================
: "${TWCC_API_KEY:?❌ TWCC_API_KEY 未設定}"
: "${TWCC_GPU_VM_ID:?❌ TWCC_GPU_VM_ID 未設定}"
: "${GPU_VM_REDIS_HOST:?❌ GPU_VM_REDIS_HOST 未設定（Base VM 內網 IP）}"
TWCCLI_PATH="${TWCCLI_PATH:-/home/ubuntu/.local/bin/twccli}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-mysecret}"

TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"
LOG_FILE="${PROJECT_DIR}/logs/twcc-schedule.log"
mkdir -p "$(dirname "$LOG_FILE")"

# ============================================
# 安全檢查：確認沒有進行中任務
# ============================================
echo "[$TIMESTAMP] 🔍 執行關機前安全檢查..."

# 檢查 Redis 佇列長度
QUEUE_LEN=$(redis-cli -h "$GPU_VM_REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" --no-auth-warning LLEN job_queue 2>/dev/null || echo "error")

if [ "$QUEUE_LEN" = "error" ]; then
    echo "[$TIMESTAMP] ⚠️ 無法連線 Redis 檢查佇列（可能已離線），繼續關機" | tee -a "$LOG_FILE"
elif [ "$QUEUE_LEN" -gt 0 ] 2>/dev/null; then
    echo "[$TIMESTAMP] ⚠️ 佇列中仍有 $QUEUE_LEN 個待處理任務，延遲關機！" | tee -a "$LOG_FILE"
    echo "[$TIMESTAMP] 請手動清空佇列或稍後再執行關機" | tee -a "$LOG_FILE"
    exit 1
fi

# 檢查 Worker 心跳（是否正在處理任務）
HEARTBEAT=$(redis-cli -h "$GPU_VM_REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" --no-auth-warning GET worker:heartbeat 2>/dev/null || echo "")

if [ "$HEARTBEAT" = "alive" ]; then
    echo "[$TIMESTAMP] 💓 Worker 心跳存活，檢查是否有進行中任務..."
    # 搜尋 processing 狀態的任務
    PROCESSING=$(redis-cli -h "$GPU_VM_REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" --no-auth-warning KEYS "job:status:*" 2>/dev/null | head -20)
    HAS_PROCESSING=false
    for key in $PROCESSING; do
        status=$(redis-cli -h "$GPU_VM_REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" --no-auth-warning HGET "$key" status 2>/dev/null)
        if [ "$status" = "processing" ]; then
            HAS_PROCESSING=true
            echo "[$TIMESTAMP] ⚠️ 發現進行中任務: $key" | tee -a "$LOG_FILE"
        fi
    done
    if [ "$HAS_PROCESSING" = true ]; then
        echo "[$TIMESTAMP] ❌ 有任務正在處理中，拒絕關機！" | tee -a "$LOG_FILE"
        exit 1
    fi
fi

echo "[$TIMESTAMP] ✅ 安全檢查通過，無進行中任務"

# ============================================
# 停止 GPU VM
# ============================================
if [ ! -x "$TWCCLI_PATH" ]; then
    echo "❌ twccli 不存在或無執行權限: $TWCCLI_PATH"
    exit 1
fi

export TWCC_API_KEY
if $TWCCLI_PATH ch vcs -sts stop -s "$TWCC_GPU_VM_ID"; then
    echo "[$TIMESTAMP] ✅ GPU VM 停止指令已發送 (ID: $TWCC_GPU_VM_ID)" | tee -a "$LOG_FILE"
else
    echo "[$TIMESTAMP] ❌ GPU VM 停止失敗" | tee -a "$LOG_FILE"
    exit 1
fi
