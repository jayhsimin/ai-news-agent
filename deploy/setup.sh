#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  AI News Agent - Oracle Cloud / Ubuntu 22.04 一鍵部署腳本
#  用法：bash deploy/setup.sh
# ═══════════════════════════════════════════════════════════

set -e

REPO_URL="https://github.com/jayhsimin/ai-news-agent.git"
INSTALL_DIR="/opt/ai-news-agent"
SERVICE_NAME="ai-news-agent"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

step() { echo -e "\n${GREEN}[$(date +%H:%M:%S)] $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
die()  { echo -e "${RED}❌ $1${NC}"; exit 1; }

# ── 1. 系統更新 ──────────────────────────────────────────
step "1/7 更新系統套件..."
sudo apt-get update -y && sudo apt-get upgrade -y
sudo apt-get install -y curl git ca-certificates

# ── 2. 安裝 Docker ────────────────────────────────────────
step "2/7 安裝 Docker..."
if command -v docker &>/dev/null; then
    echo "  Docker 已存在：$(docker --version)"
else
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    warn "Docker 已安裝。請執行以下指令使群組生效，再重新執行此腳本："
    echo ""
    echo "    newgrp docker"
    echo "    bash $INSTALL_DIR/deploy/setup.sh"
    echo ""
    exit 0
fi

if ! docker compose version &>/dev/null; then
    sudo apt-get install -y docker-compose-plugin
fi
echo "  Docker Compose：$(docker compose version)"

# ── 3. 下載 / 更新專案 ────────────────────────────────────
step "3/7 下載專案..."
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "  已存在，執行 git pull..."
    sudo git -C "$INSTALL_DIR" pull
else
    sudo git clone "$REPO_URL" "$INSTALL_DIR"
fi
sudo chown -R "$USER:$USER" "$INSTALL_DIR"

# ── 4. 設定 .env ──────────────────────────────────────────
step "4/7 設定環境變數..."
cd "$INSTALL_DIR"

if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    warn "尚未填寫 .env，請先完成設定再繼續："
    echo ""
    echo "    nano $INSTALL_DIR/.env"
    echo ""
    echo "  必填項目："
    echo "    TELEGRAM_BOT_TOKEN=（從 @BotFather 取得）"
    echo "    TELEGRAM_CHAT_ID=（你的 Telegram chat ID）"
    echo ""
    echo "  填完後重新執行："
    echo "    bash $INSTALL_DIR/deploy/setup.sh"
    exit 0
fi

# 確認 Telegram token 已填寫
if grep -q "your_telegram_bot_token_here" .env; then
    die ".env 裡的 TELEGRAM_BOT_TOKEN 尚未填寫，請先編輯 .env"
fi

echo "  .env 已設定"

# ── 5. Oracle Cloud 防火牆（iptables 開放 outbound）─────
step "5/7 確認防火牆設定..."
# Oracle Cloud 預設封鎖大部分 inbound，但 outbound 應可正常運作
# 此腳本只需 outbound HTTPS（Telegram API、RSS feeds）
echo "  本服務只需 outbound HTTPS（443），Oracle Cloud 預設允許，無需額外設定"

# ── 6. 啟動 Docker Compose ───────────────────────────────
step "6/7 啟動所有服務..."
cd "$INSTALL_DIR"
docker compose pull   # 更新 image
docker compose up -d --remove-orphans

echo ""
echo "  等待服務健康檢查（最多 60 秒）..."
sleep 60
docker compose ps

# ── 7. 下載 Ollama 模型 ───────────────────────────────────
step "7/7 下載 LLM 模型（首次約需 5~10 分鐘）..."
bash "$INSTALL_DIR/scripts/init_ollama.sh"

# ── 安裝 systemd 服務（開機自動啟動）─────────────────────
step "設定開機自動啟動..."
sudo cp "$INSTALL_DIR/deploy/ai-news-agent.service" /etc/systemd/system/
# 更新 WorkingDirectory 為實際路徑
sudo sed -i "s|WorkingDirectory=.*|WorkingDirectory=$INSTALL_DIR|" \
    /etc/systemd/system/ai-news-agent.service
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
echo "  systemd 服務已啟用"

# ── 完成 ──────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       ✅  部署完成！                 ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo "常用指令："
echo "  查看所有容器狀態：  docker compose -f $INSTALL_DIR/docker-compose.yml ps"
echo "  即時 log：          docker compose -f $INSTALL_DIR/docker-compose.yml logs -f"
echo "  手動觸發 pipeline： docker compose -f $INSTALL_DIR/docker-compose.yml exec app \\"
echo "                        python -c \"import asyncio; from tasks.pipeline import _async_full_pipeline; asyncio.run(_async_full_pipeline())\""
echo "  重新啟動所有服務：  sudo systemctl restart $SERVICE_NAME"
echo "  查看服務狀態：      sudo systemctl status $SERVICE_NAME"
