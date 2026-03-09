#!/bin/bash
# ============================================
# TWCC GPU VM 初次設定腳本
# ============================================
# 用途：在 A100 GPU VM 上一次性安裝所有依賴
#       設定 ComfyUI + Worker 的 systemd 自啟動服務
#
# 使用方式：
#   scp -r . ubuntu@<GPU_VM_IP>:/opt/studio-worker/
#   ssh ubuntu@<GPU_VM_IP> "bash /opt/studio-worker/scripts/twcc_gpu_setup.sh"
#
# 前提：Ubuntu 22.04 + NVIDIA Driver 已安裝
# ============================================

set -euo pipefail

echo "============================================"
echo "🚀 Studio Core - GPU VM 初始設定"
echo "============================================"

# ============================================
# 1. 基礎路徑設定
# ============================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WORKER_DIR="/opt/studio-worker"
COMFYUI_DIR="/opt/comfyui"
ENV_FILE="${WORKER_DIR}/.env.twcc"

echo "📁 Worker 目錄: $WORKER_DIR"
echo "📁 ComfyUI 目錄: $COMFYUI_DIR"

# ============================================
# 2. 系統套件安裝
# ============================================
echo ""
echo "📦 安裝系統套件..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3.10 python3.10-venv python3-pip \
    redis-tools \
    git curl wget

# ============================================
# 3. Worker Python 環境
# ============================================
echo ""
echo "🐍 建立 Worker Python 虛擬環境..."
if [ ! -d "${WORKER_DIR}/venv" ]; then
    python3.10 -m venv "${WORKER_DIR}/venv"
fi
source "${WORKER_DIR}/venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "${WORKER_DIR}/requirements.txt"
echo "✅ Worker 依賴安裝完成"

# ============================================
# 4. ComfyUI 環境（如果尚未安裝）
# ============================================
echo ""
if [ ! -d "${COMFYUI_DIR}" ]; then
    echo "📥 安裝 ComfyUI..."
    sudo mkdir -p "${COMFYUI_DIR}"
    sudo chown ubuntu:ubuntu "${COMFYUI_DIR}"
    git clone https://github.com/comfyanonymous/ComfyUI.git "${COMFYUI_DIR}"
    
    echo "🐍 建立 ComfyUI Python 虛擬環境..."
    python3.10 -m venv "${COMFYUI_DIR}/venv"
    source "${COMFYUI_DIR}/venv/bin/activate"
    pip install --quiet --upgrade pip
    pip install --quiet torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    pip install --quiet -r "${COMFYUI_DIR}/requirements.txt"
    echo "✅ ComfyUI 安裝完成"
else
    echo "ℹ️ ComfyUI 已存在: ${COMFYUI_DIR}"
fi

# ============================================
# 5. 模型路徑設定
# ============================================
echo ""
MODEL_DIR="/data/models"
if [ ! -d "$MODEL_DIR" ]; then
    echo "📁 建立模型目錄: $MODEL_DIR"
    sudo mkdir -p "$MODEL_DIR"
    sudo chown ubuntu:ubuntu "$MODEL_DIR"
    echo "⚠️ 請手動將模型檔案複製到 $MODEL_DIR"
fi

# ============================================
# 6. 讀取 Base VM IP（從 .env.twcc）
# ============================================
echo ""
if [ -f "$ENV_FILE" ]; then
    BASE_VM_IP=$(grep "^GPU_VM_REDIS_HOST=" "$ENV_FILE" | cut -d'=' -f2 | xargs)
    echo "📡 Base VM IP: ${BASE_VM_IP:-'未設定'}"
    
    if [ -z "$BASE_VM_IP" ] || [ "$BASE_VM_IP" = "10.x.x.x" ]; then
        echo "⚠️  請先在 .env.twcc 中設定 GPU_VM_REDIS_HOST 為 Base VM 的私有 IP"
        echo "    例如: GPU_VM_REDIS_HOST=10.0.0.5"
    fi
else
    echo "⚠️ 找不到 .env.twcc，請先複製到 ${WORKER_DIR}/"
fi

# ============================================
# 7. 安裝 Systemd 服務
# ============================================
echo ""
echo "⚙️ 安裝 Systemd 服務..."

# ComfyUI 服務
COMFYUI_SERVICE="/etc/systemd/system/comfyui.service"
if [ -f "${WORKER_DIR}/worker/comfyui.service.template" ]; then
    sudo cp "${WORKER_DIR}/worker/comfyui.service.template" "$COMFYUI_SERVICE"
    echo "  ✅ comfyui.service 已安裝"
elif [ -f "${PROJECT_DIR}/worker/comfyui.service.template" ]; then
    sudo cp "${PROJECT_DIR}/worker/comfyui.service.template" "$COMFYUI_SERVICE"
    echo "  ✅ comfyui.service 已安裝"
else
    echo "  ⚠️ 找不到 comfyui.service.template"
fi

# Worker 服務
WORKER_SERVICE="/etc/systemd/system/studio-worker.service"
if [ -f "${WORKER_DIR}/worker/worker.service.template" ]; then
    sudo cp "${WORKER_DIR}/worker/worker.service.template" "$WORKER_SERVICE"
    echo "  ✅ studio-worker.service 已安裝"
elif [ -f "${PROJECT_DIR}/worker/worker.service.template" ]; then
    sudo cp "${PROJECT_DIR}/worker/worker.service.template" "$WORKER_SERVICE"
    echo "  ✅ studio-worker.service 已安裝"
else
    echo "  ⚠️ 找不到 worker.service.template"
fi

# 如果有 Base VM IP，替換 systemd service 中的變數
if [ -n "${BASE_VM_IP:-}" ] && [ "$BASE_VM_IP" != "10.x.x.x" ]; then
    if [ -f "$WORKER_SERVICE" ]; then
        sudo sed -i "s/\${GPU_VM_REDIS_HOST}/${BASE_VM_IP}/g" "$WORKER_SERVICE"
        echo "  ✅ Worker service 中 Redis/DB host 已設為 ${BASE_VM_IP}"
    fi
fi

# 重新載入 systemd
sudo systemctl daemon-reload
sudo systemctl enable comfyui studio-worker
echo "✅ Systemd 服務已啟用（開機自動啟動）"

# ============================================
# 8. 確認 TWCC CLI 安裝
# ============================================
echo ""
if command -v twccli &> /dev/null; then
    echo "✅ twccli 已安裝: $(which twccli)"
else
    echo "📦 安裝 twccli..."
    pip install twccli
    echo "✅ twccli 安裝完成"
fi

# ============================================
# 完成
# ============================================
echo ""
echo "============================================"
echo "🎉 GPU VM 初始設定完成！"
echo "============================================"
echo ""
echo "📋 後續步驟："
echo "  1. 確認 .env.twcc 中的 GPU_VM_REDIS_HOST 已設為 Base VM IP"
echo "  2. 將模型檔案複製到 ${MODEL_DIR}"
echo "  3. 啟動服務: sudo systemctl start comfyui studio-worker"
echo "  4. 檢查日誌: journalctl -u comfyui -f"
echo "             journalctl -u studio-worker -f"
echo "  5. 驗證連線: redis-cli -h <Base_VM_IP> -a mysecret ping"
echo ""
echo "⚠️ 安全提醒："
echo "  - 確認 Base VM Security Group 允許此 VM 存取 6379/3306"
echo "  - 確認 GPU VM Security Group 僅開放 SSH (22)"
