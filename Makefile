# ═══════════════════════════════════════════════
#  AI News Agent - Makefile
#  常用操作指令
# ═══════════════════════════════════════════════

.PHONY: help setup up down logs pull-model trigger status clean

# 預設目標：顯示說明
help:
	@echo ""
	@echo "╔══════════════════════════════════════╗"
	@echo "║     AI News Agent - 指令說明          ║"
	@echo "╚══════════════════════════════════════╝"
	@echo ""
	@echo "  make setup        首次設定（複製 .env、建立 Docker 映像）"
	@echo "  make up           啟動所有服務"
	@echo "  make down         停止所有服務"
	@echo "  make logs         查看所有服務日誌"
	@echo "  make logs-worker  查看 Celery Worker 日誌"
	@echo "  make pull-model   下載 Ollama LLM 模型（首次必須執行）"
	@echo "  make trigger      手動觸發一次 pipeline"
	@echo "  make status       查看系統狀態"
	@echo "  make health       執行健康檢查"
	@echo "  make flower       開啟 Celery 監控介面"
	@echo "  make clean        清除所有 Docker 資源（危險！）"
	@echo ""

# 首次設定
setup:
	@echo "⚙️  首次設定中..."
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "✅ 已複製 .env.example 為 .env，請編輯 .env 填入必要設定"; \
	else \
		echo "ℹ️  .env 已存在，跳過複製"; \
	fi
	@docker compose build
	@echo ""
	@echo "⚠️  請完成以下步驟後執行 make up："
	@echo "  1. 編輯 .env，填入 REDDIT_CLIENT_ID、REDDIT_CLIENT_SECRET"
	@echo "  2. 編輯 .env，填入 TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID"
	@echo "  3. 執行 make up 啟動服務"
	@echo "  4. 執行 make pull-model 下載 LLM 模型"

# 啟動服務
up:
	@echo "🚀 啟動所有服務..."
	docker compose up -d
	@echo ""
	@echo "✅ 服務已啟動！"
	@echo "  API 文件：http://localhost:8000/docs"
	@echo "  Celery 監控：http://localhost:5555"
	@echo "  Qdrant UI：http://localhost:6333/dashboard"
	@echo ""
	@echo "⚠️  若 Ollama 模型尚未下載，請執行：make pull-model"

# 停止服務
down:
	@echo "⏹️  停止所有服務..."
	docker compose down

# 查看日誌
logs:
	docker compose logs -f --tail=100

logs-app:
	docker compose logs -f app --tail=100

logs-worker:
	docker compose logs -f celery-worker --tail=100

logs-beat:
	docker compose logs -f celery-beat --tail=100

# 下載 Ollama 模型（首次必須執行）
pull-model:
	@echo "📥 下載 LLM 模型（可能需要數分鐘，請耐心等候）..."
	@MODEL=$$(grep OLLAMA_MODEL .env 2>/dev/null | cut -d= -f2 || echo "qwen2.5:7b"); \
	echo "  模型：$$MODEL"; \
	docker exec ai-news-ollama ollama pull $$MODEL
	@echo "✅ 模型下載完成！"

# 手動觸發 pipeline
trigger:
	@echo "⚡ 手動觸發 pipeline..."
	curl -s -X POST http://localhost:8000/api/trigger/pipeline | python3 -m json.tool

# 查看系統狀態
status:
	@echo "📊 系統狀態："
	curl -s http://localhost:8000/api/status | python3 -m json.tool

# 健康檢查
health:
	@echo "🏥 執行健康檢查..."
	curl -s -X POST http://localhost:8000/api/trigger/health-check | python3 -m json.tool

# 開啟 Celery Flower 監控
flower:
	@echo "🌸 Celery 監控：http://localhost:5555"
	open http://localhost:5555 2>/dev/null || xdg-open http://localhost:5555 2>/dev/null || true

# 重建 Docker 映像
rebuild:
	docker compose build --no-cache

# 清除所有 Docker 資源（危險！會刪除資料！）
clean:
	@echo "⚠️  警告：此操作會刪除所有 Docker 容器、Volume 和資料！"
	@read -p "確定要繼續？(y/N) " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		docker compose down -v --remove-orphans; \
		echo "✅ 清除完成"; \
	else \
		echo "❌ 已取消"; \
	fi
