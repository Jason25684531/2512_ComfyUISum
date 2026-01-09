#!/bin/bash
# ============================================
# ComfyUI Studio - Linux Deployment Script
# ============================================

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "============================================"
echo "   ComfyUI Studio - Linux Deployment"
echo "============================================"
echo ""

# 切換到腳本所在目錄的上一層（專案根目錄）
cd "$(dirname "$0")/.."

# 檢查 .env 檔案
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}[WARNING]${NC} .env file not found!"
    if [ -f ".env.unified.example" ]; then
        echo "Creating .env from .env.unified.example..."
        cp .env.unified.example .env
        echo -e "${YELLOW}Please edit .env file and configure your environment.${NC}"
        echo ""
        exit 1
    else
        echo -e "${RED}[ERROR]${NC} .env.unified.example not found!"
        exit 1
    fi
fi

# 載入環境變數
export $(grep -v '^#' .env | xargs)

# 檢查 Docker
echo "[1/6] Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} Docker is not installed!"
    exit 1
fi

if ! docker ps &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} Docker daemon is not running!"
    exit 1
fi
echo -e "${GREEN}[OK]${NC} Docker is running"

# 檢查 docker-compose
if ! command -v docker-compose &> /dev/null; then
    echo -e "${YELLOW}[WARNING]${NC} docker-compose not found, trying docker compose..."
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

# 檢查 NVIDIA GPU (可選)
echo ""
echo "[2/6] Checking GPU..."
if command -v nvidia-smi &> /dev/null; then
    echo -e "${GREEN}[OK]${NC} NVIDIA GPU detected"
    nvidia-smi --query-gpu=name --format=csv,noheader
else
    echo -e "${YELLOW}[WARNING]${NC} NVIDIA GPU not detected (ComfyUI will run on CPU)"
fi

# 選擇部署模式
echo ""
echo "Select deployment mode:"
echo "[1] Development (linux-dev profile)"
echo "[2] Production (linux-prod profile)"
echo "[3] Infrastructure only (MySQL + Redis)"
echo "[4] Stop all services"
echo "[5] View logs"
echo "[6] Clean up (remove containers and volumes)"
echo ""
read -p "Please choose (1-6): " CHOICE

case $CHOICE in
    1)
        PROFILE="linux-dev"
        MODE="Development"
        ;;
    2)
        PROFILE="linux-prod"
        MODE="Production"
        ;;
    3)
        PROFILE="infra-only"
        MODE="Infrastructure Only"
        ;;
    4)
        echo ""
        echo "[INFO] Stopping all services..."
        $COMPOSE_CMD -f docker-compose.unified.yml --profile linux-dev --profile linux-prod down
        echo -e "${GREEN}[OK]${NC} All services stopped"
        exit 0
        ;;
    5)
        echo ""
        echo "[INFO] Viewing logs (Press Ctrl+C to exit)..."
        $COMPOSE_CMD -f docker-compose.unified.yml logs -f
        exit 0
        ;;
    6)
        echo ""
        echo -e "${RED}[WARNING]${NC} This will remove all containers and volumes!"
        read -p "Are you sure? (yes/no): " CONFIRM
        if [ "$CONFIRM" = "yes" ]; then
            $COMPOSE_CMD -f docker-compose.unified.yml --profile linux-dev --profile linux-prod down -v
            echo -e "${GREEN}[OK]${NC} Cleanup completed"
        else
            echo "Cancelled"
        fi
        exit 0
        ;;
    *)
        echo -e "${RED}[ERROR]${NC} Invalid choice"
        exit 1
        ;;
esac

# 創建必要的目錄
echo ""
echo "[3/6] Creating required directories..."
mkdir -p storage/inputs storage/outputs storage/models logs redis_data mysql_data
echo -e "${GREEN}[OK]${NC} Directories created"

# 拉取最新映像
echo ""
echo "[4/6] Pulling latest images..."
if [ "$PROFILE" = "infra-only" ]; then
    $COMPOSE_CMD -f docker-compose.unified.yml pull redis mysql
else
    $COMPOSE_CMD -f docker-compose.unified.yml --profile $PROFILE pull
fi

# 啟動服務
echo ""
echo "[5/6] Starting services in $MODE mode..."
if [ "$PROFILE" = "infra-only" ]; then
    $COMPOSE_CMD -f docker-compose.unified.yml up -d redis mysql
else
    $COMPOSE_CMD -f docker-compose.unified.yml --profile $PROFILE up -d
fi

if [ $? -ne 0 ]; then
    echo -e "${RED}[ERROR]${NC} Failed to start services!"
    exit 1
fi

echo -e "${GREEN}[OK]${NC} Services started"

# 等待服務就緒
echo ""
echo "[6/6] Waiting for services to be ready..."
sleep 5

# 檢查服務狀態
echo ""
echo "Service status:"
echo "----------------------------------------"
$COMPOSE_CMD -f docker-compose.unified.yml ps

# 顯示連接資訊
echo ""
echo "Service information:"
echo "----------------------------------------"
echo -e "MySQL:    ${GREEN}localhost:${MYSQL_PORT:-3307}${NC}"
echo -e "Redis:    ${GREEN}localhost:${REDIS_PORT:-6379}${NC}"
echo -e "Backend:  ${GREEN}http://localhost:${BACKEND_PORT:-5000}${NC}"
if [ "$PROFILE" != "infra-only" ]; then
    echo -e "ComfyUI:  ${GREEN}http://localhost:${COMFYUI_PORT:-8188}${NC}"
fi
echo "----------------------------------------"
echo ""
echo -e "${GREEN}[SUCCESS]${NC} Deployment completed!"
echo ""
echo "Useful commands:"
echo "  $COMPOSE_CMD -f docker-compose.unified.yml logs -f              (view logs)"
echo "  $COMPOSE_CMD -f docker-compose.unified.yml --profile $PROFILE down    (stop)"
echo "  $COMPOSE_CMD -f docker-compose.unified.yml ps                   (status)"
echo "  $COMPOSE_CMD -f docker-compose.unified.yml restart <service>    (restart)"
echo ""
