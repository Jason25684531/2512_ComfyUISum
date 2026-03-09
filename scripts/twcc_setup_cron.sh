#!/bin/bash
# ============================================
# TWCC Cron 排程安裝工具
# ============================================
# 用途：自動安裝 GPU VM 定時啟停的 crontab 條目
# 預設：週一到週五 09:00 啟動、18:00 關閉
# ============================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

START_SCRIPT="${SCRIPT_DIR}/twcc_start_gpu.sh"
STOP_SCRIPT="${SCRIPT_DIR}/twcc_stop_gpu.sh"

# 確認腳本存在
for script in "$START_SCRIPT" "$STOP_SCRIPT"; do
    if [ ! -f "$script" ]; then
        echo "❌ 找不到腳本: $script"
        exit 1
    fi
    chmod +x "$script"
done

# ============================================
# 設定 Cron 排程
# ============================================
echo "📅 即將安裝以下 Cron 排程："
echo "   週一到週五 09:00 啟動 GPU VM"
echo "   週一到週五 18:00 停止 GPU VM"
echo ""

# 預設排程（可自訂）
START_CRON="${START_CRON:-0 9 * * 1-5}"
STOP_CRON="${STOP_CRON:-0 18 * * 1-5}"

# 標記用於識別 Studio Core 的 crontab 條目
MARKER="# STUDIO-CORE-TWCC-SCHEDULE"

# 移除舊的 Studio Core 排程（如有）
crontab -l 2>/dev/null | grep -v "$MARKER" | crontab - 2>/dev/null || true

# 加入新排程
(
    crontab -l 2>/dev/null || true
    echo "${START_CRON} ${START_SCRIPT} ${MARKER}-START"
    echo "${STOP_CRON} ${STOP_SCRIPT} ${MARKER}-STOP"
) | crontab -

echo "✅ Cron 排程已安裝！"
echo ""
echo "📋 目前的 crontab："
crontab -l | grep -E "(STUDIO-CORE|twcc_)" || echo "   （無匹配條目）"
echo ""
echo "💡 提示："
echo "   - 修改時間: 編輯此腳本的 START_CRON / STOP_CRON 變數"
echo "   - 移除排程: crontab -e 刪除含 STUDIO-CORE 的行"
echo "   - 查看日誌: tail -f logs/twcc-schedule.log"
