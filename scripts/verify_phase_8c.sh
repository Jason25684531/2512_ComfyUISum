#!/bin/bash
# Phase 8c 後端快速驗證脚本 (Linux/Mac)
# 用途: 快速啟動後端並驗證監控儀表板的改進

set -e

echo "🚀 ComfyUI Studio Backend - Phase 8c Verification"
echo "=================================================="
echo ""

# 檢查 Python 版本
echo "📋 檢查環境..."
python_version=$(python --version 2>&1 || python3 --version 2>&1)
echo "✓ Python: $python_version"

# 檢查虛擬環境
if [ -d "backend/venv" ]; then
    echo "✓ 虛擬環境存在"
    source backend/venv/bin/activate
    echo "✓ 虛擬環境已激活"
else
    echo "⚠️ 警告: 虛擬環境不存在"
    echo "建議執行: cd backend && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
fi

echo ""
echo "📊 驗證清單:"
echo "──────────────────────────────────────────"
echo "[ ] 儀表板在啟動時立即顯示（置頂）"
echo "[ ] Redis 連接成功（無錯誤信息）"
echo "[ ] MySQL 連接成功"
echo "[ ] 日誌帶有 [User#XXX] 標籤"
echo "[ ] 儀表板每 5 秒更新一次"
echo "[ ] 日誌自然滾動（不覆蓋儀表板）"
echo ""

echo "🎬 啟動 Backend 應用..."
echo "──────────────────────────────────────────"
echo ""
echo "💡 提示："
echo "  • 儀表板應該在頂部（使用 Rich Live）"
echo "  • 日誌應該在儀表板下方"
echo "  • 按 Ctrl+C 優雅關閉"
echo ""
echo "──────────────────────────────────────────"
echo ""

# 啟動後端
cd backend/src
python app.py

# 清理
echo ""
echo "✓ Backend 已關閉"
