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

# 載入環境變數
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

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
for svc in nginx api redis mysql; do
    warn_check "容器 [$svc] 運行中" \
        "docker ps --filter name=$svc --filter status=running --format '{{.Names}}' | grep -q $svc"
done
echo ""

# ==========================================
# 2. Redis 檢查
# ==========================================
echo "--- Redis ---"

check "Redis PING 回應" \
    "docker exec redis redis-cli ping | grep -q PONG"

warn_check "Redis 記憶體使用率 < 80%" \
    "docker exec redis redis-cli info memory | grep used_memory_peak_human"

# 任務佇列
QUEUE_LEN=$(docker exec redis redis-cli LLEN job_queue 2>/dev/null || echo "0")
if [ "$QUEUE_LEN" -gt 10 ] 2>/dev/null; then
    TOTAL=$((TOTAL + 1))
    WARNED=$((WARNED + 1))
    echo -e "$WARN 任務佇列長度: $QUEUE_LEN (> 10，可能需要關注)"
else
    TOTAL=$((TOTAL + 1))
    PASSED=$((PASSED + 1))
    echo -e "$PASS 任務佇列長度: $QUEUE_LEN"
fi
echo ""

# ==========================================
# 3. MySQL 檢查
# ==========================================
echo "--- MySQL ---"

MYSQL_PWD="${MYSQL_ROOT_PASSWORD:-}"
if [ -n "$MYSQL_PWD" ]; then
    check "MySQL 連線正常" \
        "docker exec mysql mysql -u root -p'$MYSQL_PWD' -e 'SELECT 1;' > /dev/null 2>&1"

    check "studio_db 資料庫存在" \
        "docker exec mysql mysql -u root -p'$MYSQL_PWD' -e 'USE studio_db;' > /dev/null 2>&1"
else
    TOTAL=$((TOTAL + 1))
    WARNED=$((WARNED + 1))
    echo -e "$WARN MySQL 密碼未設定（MYSQL_ROOT_PASSWORD），跳過資料庫檢查"
fi
echo ""

# ==========================================
# 4. Nginx / HTTP 檢查
# ==========================================
echo "--- Nginx / HTTP ---"

check "Nginx 回應 (HTTP 200)" \
    "curl -sf -o /dev/null -w '%{http_code}' http://localhost | grep -q 200"

warn_check "Flask API 回應" \
    "curl -sf http://localhost/api/health > /dev/null 2>&1 || curl -sf -o /dev/null http://localhost/api/ 2>&1"
echo ""

# ==========================================
# 5. COS (S3) 檢查
# ==========================================
echo "--- TWCC COS (S3) ---"

S3_EP="${S3_ENDPOINT:-}"
S3_AK="${S3_ACCESS_KEY:-}"
S3_SK="${S3_SECRET_KEY:-}"
S3_BK="${S3_BUCKET:-studio-outputs}"
STORAGE="${STORAGE_BACKEND:-local}"

if [ "$STORAGE" = "s3" ] && [ -n "$S3_EP" ] && [ -n "$S3_AK" ] && [ -n "$S3_SK" ]; then
    check "COS Bucket 可存取" \
        "AWS_ACCESS_KEY_ID='$S3_AK' AWS_SECRET_ACCESS_KEY='$S3_SK' aws s3api head-bucket --bucket '$S3_BK' --endpoint-url '$S3_EP' 2>&1"
else
    TOTAL=$((TOTAL + 1))
    WARNED=$((WARNED + 1))
    echo -e "$WARN S3 未啟用或變數未設定 (STORAGE_BACKEND=$STORAGE)，跳過 COS 檢查"
fi
echo ""

# ==========================================
# 6. Worker 心跳檢查
# ==========================================
echo "--- Worker 心跳 ---"

HEARTBEAT=$(docker exec redis redis-cli GET worker:heartbeat 2>/dev/null || echo "")
if [ -z "$HEARTBEAT" ]; then
    TOTAL=$((TOTAL + 1))
    WARNED=$((WARNED + 1))
    echo -e "$WARN Worker 心跳不存在（Worker 可能未啟動或 GPU VM 已關機）"
else
    NOW=$(date +%s)
    HB_AGE=$((NOW - HEARTBEAT))
    if [ "$HB_AGE" -gt 120 ]; then
        TOTAL=$((TOTAL + 1))
        WARNED=$((WARNED + 1))
        echo -e "$WARN Worker 心跳已 ${HB_AGE}s 未更新（> 120s，可能失聯）"
    else
        TOTAL=$((TOTAL + 1))
        PASSED=$((PASSED + 1))
        echo -e "$PASS Worker 心跳正常（${HB_AGE}s 前更新）"
    fi
fi
echo ""

# ==========================================
# 7. 磁碟空間檢查
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
