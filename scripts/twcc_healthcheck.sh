#!/usr/bin/env bash
# =====================================================
# TWCC 健康檢查腳本
# 用途：檢查 Base VM 上所有服務的運行狀態
# 執行：bash scripts/twcc_healthcheck.sh
# =====================================================

set -euo pipefail

# --- 顏色定義 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS="${GREEN}[PASS]${NC}"
FAIL="${RED}[FAIL]${NC}"
WARN="${YELLOW}[WARN]${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
NGINX_CONTAINER="studio-nginx"
BACKEND_CONTAINER="studio-backend"
REDIS_CONTAINER="studio-redis"

# 載入環境變數
if [ -f "$PROJECT_DIR/.env.twcc" ]; then
    set -a
    source "$PROJECT_DIR/.env.twcc"
    set +a
elif [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

REDIS_PASSWORD="${REDIS_PASSWORD:-}"

echo "=========================================="
echo "  Studio Core — TWCC 健康檢查"
echo "  時間: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""

TOTAL=0
PASSED=0
FAILED=0
WARNED=0

check() {
    TOTAL=$((TOTAL + 1))
    local name="$1"
    local cmd="$2"
    local result

    if result=$(eval "$cmd" 2>&1); then
        echo -e "$PASS $name"
        PASSED=$((PASSED + 1))
        return 0
    else
        echo -e "$FAIL $name"
        echo "       → $result"
        FAILED=$((FAILED + 1))
        return 1
    fi
}

warn_check() {
    TOTAL=$((TOTAL + 1))
    local name="$1"
    local cmd="$2"
    local result

    if result=$(eval "$cmd" 2>&1); then
        echo -e "$PASS $name"
        PASSED=$((PASSED + 1))
    else
        echo -e "$WARN $name"
        echo "       → $result"
        WARNED=$((WARNED + 1))
    fi
}

# ==========================================
# 1. Docker 服務檢查
# ==========================================
echo "--- Docker 容器狀態 ---"

check "Docker daemon 運行中" \
    "docker info > /dev/null 2>&1"

# 檢查各容器是否 running
warn_check "容器 [studio-nginx] 運行中" \
    "docker ps --filter name=${NGINX_CONTAINER} --filter status=running --format '{{.Names}}' | grep -q ${NGINX_CONTAINER}"
warn_check "容器 [studio-backend] 運行中" \
    "docker ps --filter name=${BACKEND_CONTAINER} --filter status=running --format '{{.Names}}' | grep -q ${BACKEND_CONTAINER}"
warn_check "容器 [studio-redis] 運行中" \
    "docker ps --filter name=${REDIS_CONTAINER} --filter status=running --format '{{.Names}}' | grep -q ${REDIS_CONTAINER}"
echo ""

# ==========================================
# 2. Redis 檢查
# ==========================================
echo "--- Redis ---"

if [ -n "$REDIS_PASSWORD" ]; then
    check "Redis PING 回應" \
        "docker exec ${REDIS_CONTAINER} redis-cli -a '${REDIS_PASSWORD}' --no-auth-warning ping | grep -q PONG"

    warn_check "Redis 記憶體使用率 < 80%" \
        "docker exec ${REDIS_CONTAINER} redis-cli -a '${REDIS_PASSWORD}' --no-auth-warning info memory | grep used_memory_peak_human"

    # 任務佇列
    QUEUE_LEN=$(docker exec ${REDIS_CONTAINER} redis-cli -a "${REDIS_PASSWORD}" --no-auth-warning LLEN job_queue 2>/dev/null || echo "0")
    if [ "$QUEUE_LEN" -gt 10 ] 2>/dev/null; then
        TOTAL=$((TOTAL + 1))
        WARNED=$((WARNED + 1))
        echo -e "$WARN 任務佇列長度: $QUEUE_LEN (> 10，可能需要關注)"
    else
        TOTAL=$((TOTAL + 1))
        PASSED=$((PASSED + 1))
        echo -e "$PASS 任務佇列長度: $QUEUE_LEN"
    fi
else
    TOTAL=$((TOTAL + 1))
    WARNED=$((WARNED + 1))
    echo -e "$WARN REDIS_PASSWORD 未設定，跳過 Redis 驗證"
fi
echo ""

# ==========================================
# 3. Nginx / HTTP 檢查
# ==========================================
echo "--- Nginx / HTTP ---"

check "Nginx 回應 (HTTP 200)" \
    "curl -sf -o /dev/null -w '%{http_code}' http://localhost | grep -q 200"

warn_check "Flask API 回應" \
    "curl -sf http://localhost/api/health > /dev/null 2>&1 || curl -sf http://localhost/health > /dev/null 2>&1"
if [ -n "${LB_DOMAIN:-}" ]; then
    warn_check "LB / Edge health 回應" \
        "curl -sf https://${LB_DOMAIN}/health > /dev/null 2>&1 || curl -sf https://${LB_DOMAIN}/api/health > /dev/null 2>&1"
fi
echo ""

# ==========================================
# 4. Worker 心跳檢查
# ==========================================
echo "--- Worker 心跳 ---"

HEARTBEAT=$(docker exec ${REDIS_CONTAINER} redis-cli -a "${REDIS_PASSWORD}" --no-auth-warning GET worker:heartbeat 2>/dev/null || echo "")
if [ -z "$HEARTBEAT" ]; then
    TOTAL=$((TOTAL + 1))
    WARNED=$((WARNED + 1))
    echo -e "$WARN Worker 心跳不存在（Worker 可能未啟動或 GPU VM 已關機）"
else
    HEARTBEAT_TTL=$(docker exec ${REDIS_CONTAINER} redis-cli -a "${REDIS_PASSWORD}" --no-auth-warning TTL worker:heartbeat 2>/dev/null || echo "-1")
    if [ "$HEARTBEAT_TTL" -le 0 ] 2>/dev/null; then
        TOTAL=$((TOTAL + 1))
        WARNED=$((WARNED + 1))
        echo -e "$WARN Worker 心跳鍵存在但 TTL 異常（ttl=${HEARTBEAT_TTL}），建議檢查 Worker 狀態"
    else
        TOTAL=$((TOTAL + 1))
        PASSED=$((PASSED + 1))
        echo -e "$PASS Worker 心跳正常（TTL 剩餘 ${HEARTBEAT_TTL}s）"
    fi
fi
echo ""

# ==========================================
# 5. 磁碟空間檢查
# ==========================================
echo "--- 磁碟空間 ---"

DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_USAGE" -gt 85 ]; then
    TOTAL=$((TOTAL + 1))
    WARNED=$((WARNED + 1))
    echo -e "$WARN 根磁碟使用率 ${DISK_USAGE}% (> 85%，建議清理)"
else
    TOTAL=$((TOTAL + 1))
    PASSED=$((PASSED + 1))
    echo -e "$PASS 根磁碟使用率 ${DISK_USAGE}%"
fi
echo ""

# ==========================================
# 總結
# ==========================================
echo "=========================================="
echo "  檢查結果總結"
echo "  總計: $TOTAL | 通過: $PASSED | 失敗: $FAILED | 警告: $WARNED"
echo "=========================================="

if [ "$FAILED" -gt 0 ]; then
    echo -e "${RED}❌ 有 $FAILED 項檢查失敗，請立即處理！${NC}"
    exit 1
elif [ "$WARNED" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  有 $WARNED 項警告，建議關注。${NC}"
    exit 0
else
    echo -e "${GREEN}✅ 所有檢查通過！${NC}"
    exit 0
fi
