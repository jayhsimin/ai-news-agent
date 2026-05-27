# 🤖 AI News Agent

**完全免費、可本地部署的 AI 最新資訊自動推播系統**

自動從多個來源採集 AI 相關資訊，使用本地 LLM（Ollama）分析摘要，智慧去重後推播到 Telegram。

---

## 🏗 系統架構

```
┌─────────────────────────────────────────────────────┐
│                   Celery Beat（定時）                 │
│                每 N 分鐘觸發 pipeline                 │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│              CollectorAgent（採集層）                 │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌─────────┐  │
│  │  Reddit  │ │   HN     │ │ GitHub │ │  arXiv  │  │
│  │ (PRAW)   │ │(Firebase)│ │  (BS4) │ │  (lib)  │  │
│  └──────────┘ └──────────┘ └────────┘ └─────────┘  │
└─────────────────────┬───────────────────────────────┘
                      │  NewsItem[]
                      ▼
┌─────────────────────────────────────────────────────┐
│              AnalyzerAgent（分析層）                  │
│  1. Embed  → sentence-transformers all-MiniLM-L6-v2 │
│  2. Dedupe → Qdrant 語意相似度比對                   │
│  3. Summary→ Ollama LLM（繁體中文摘要）               │
│  4. Classify+Score → Ollama LLM（分類 + 0~10 評分）  │
└─────────────────────┬───────────────────────────────┘
                      │  NewsItem[]（已分析）
                      ▼
┌─────────────────────────────────────────────────────┐
│              PublisherAgent（推播層）                 │
│  篩選 score >= 閾值 → 排序 → Telegram Bot API        │
└─────────────────────────────────────────────────────┘
```

---

## 🧰 技術棧

| 元件 | 技術 | 說明 |
|------|------|------|
| Backend | Python 3.12 + FastAPI | REST API + 管理介面 |
| Task Queue | Celery + Redis | 背景任務 + 定時排程 |
| Vector DB | Qdrant | 語意去重 |
| LLM | Ollama (本地) | 摘要 + 分類 + 評分 |
| Embedding | sentence-transformers | all-MiniLM-L6-v2（384維） |
| 採集 | asyncpraw / httpx / beautifulsoup4 / arxiv | 各資料來源 |
| 推播 | Telegram Bot API | 免費，無需費用 |

**完全免費！不使用任何付費 API！**

---

## 🚀 快速開始

### 前置需求

- Docker + Docker Compose
- 8GB+ RAM（Ollama 模型需要）
- 網路連線（初始化時下載模型）

### 步驟一：取得設定

#### Reddit API（免費）
1. 前往 https://www.reddit.com/prefs/apps
2. 點擊「create another app」
3. 類型選「**script**」
4. 記下 `client_id`（app 名稱下方）和 `secret`

#### Telegram Bot（免費）
1. 在 Telegram 找 **@BotFather**
2. 發送 `/newbot`，依指示建立 bot
3. 記下 bot token（格式：`1234567890:ABC-xxx`）
4. 建立頻道或群組，將 bot 加為**管理員**
5. 取得 chat_id（可用 @userinfobot 查詢，或 API 取得）

### 步驟二：部署

```bash
# 1. 複製專案
git clone <this-repo>
cd ai-news-agent

# 2. 設定環境變數
cp .env.example .env
# 編輯 .env，填入 Reddit 和 Telegram 設定
nano .env  # 或 vim .env

# 3. 啟動所有服務
make up
# 或手動：docker compose up -d

# 4. 下載 Ollama 模型（首次必須，約需 5~15 分鐘）
make pull-model
# 或手動：docker exec -it ai-news-ollama ollama pull qwen2.5:7b

# 5. 手動觸發一次測試
make trigger
```

### 服務網址

| 服務 | 網址 |
|------|------|
| API 文件 | http://localhost:8000/docs |
| Celery 監控 | http://localhost:5555 |
| Qdrant Dashboard | http://localhost:6333/dashboard |

---

## ⚙️ 設定說明

編輯 `.env` 調整各項參數：

```bash
# 採集頻率（分鐘）
COLLECT_INTERVAL_MINUTES=30

# 推播門檻（0~10，越高越嚴格）
MIN_RELEVANCE_SCORE=6.0

# 去重相似度門檻（0~1，越高越嚴格）
SIMILARITY_THRESHOLD=0.85

# LLM 模型（可換成 llama3.1:8b）
OLLAMA_MODEL=qwen2.5:7b
```

---

## 📁 專案結構

```
ai-news-agent/
├── collectors/          # 資料來源採集器（各自獨立）
│   ├── base.py          # NewsItem schema + BaseCollector 介面
│   ├── reddit.py        # Reddit（asyncpraw）
│   ├── hackernews.py    # HackerNews（Firebase API）
│   ├── github.py        # GitHub Trending（BeautifulSoup）
│   └── arxiv_collector.py  # arXiv（arxiv library）
├── processors/          # 文章處理器
│   ├── embedder.py      # sentence-transformers 向量化
│   ├── deduplicator.py  # Qdrant 語意去重
│   ├── summarizer.py    # Ollama 摘要生成
│   └── classifier.py    # Ollama 分類 + 評分
├── agents/              # Agent 系統（可擴充 multi-agent）
│   ├── base.py          # BaseAgent 介面
│   ├── collector_agent.py   # 採集 Agent
│   ├── analyzer_agent.py    # 分析 Agent
│   └── publisher_agent.py   # 推播 Agent
├── tasks/               # Celery 任務定義
│   ├── celery_app.py    # Celery 設定 + 排程
│   └── pipeline.py      # Pipeline 任務
├── db/
│   └── qdrant_store.py  # Qdrant 操作層
├── notifiers/
│   └── telegram.py      # Telegram 推播
├── api/
│   ├── routes.py        # FastAPI 路由
│   └── schemas.py       # Request/Response schema
├── docker-compose.yml   # 完整服務編排
├── Dockerfile
├── Makefile             # 常用操作指令
└── .env.example         # 設定範本
```

---

## 🔌 API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/` | 系統資訊 |
| GET | `/api/status` | 服務狀態 |
| GET | `/api/health` | 健康檢查 |
| POST | `/api/trigger/pipeline` | 手動觸發完整 pipeline |
| POST | `/api/trigger/collect` | 只觸發採集 |
| POST | `/api/trigger/health-check` | 觸發服務健康檢查 |
| GET | `/api/task/{task_id}` | 查詢任務狀態 |

---

## 🔧 擴充指南

### 新增資料來源

1. 在 `collectors/` 建立新的 collector，繼承 `BaseCollector`
2. 實作 `collect()` 方法，回傳 `list[NewsItem]`
3. 在 `agents/collector_agent.py` 加入新 collector

### 新增推播管道

1. 在 `notifiers/` 建立新的 notifier（如 Discord、Slack）
2. 在 `agents/publisher_agent.py` 加入新 notifier

### 擴充成 Multi-Agent

Agent 間目前透過直接方法呼叫串接。
擴充為分散式 multi-agent 的建議方向：
- 用 Redis Pub/Sub 讓 Agent 間互相訂閱
- 每個 Agent 部署為獨立的 Celery Worker
- 加入 Agent Registry 進行動態服務發現

---

## 📊 Telegram 推播格式

```
🚀 [模型發布] GPT-5 正式發布，效能超越 o3

📝 OpenAI 今日發布 GPT-5，在多個主要基準測試中...

🟠 來源：REDDIT  |  🏷 模型發布
📊 重要性：⭐⭐⭐⭐⭐ 9.5/10

🔗 閱讀全文

#reddit #LocalLLaMA #模型發布
```

---

## 🆓 完全免費清單

- ✅ Reddit API：免費（需申請 App）
- ✅ HackerNews Firebase API：完全免費，無需申請
- ✅ GitHub Trending：公開頁面，無需 API Key
- ✅ arXiv API：完全免費，無需申請
- ✅ Ollama：本地 LLM，完全免費
- ✅ Qdrant：開源，Docker 部署
- ✅ Redis：開源，Docker 部署
- ✅ Telegram Bot API：免費

**總月費：$0**
