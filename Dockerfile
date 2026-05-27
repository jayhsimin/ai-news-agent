FROM python:3.12-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴清單並安裝（分離此步驟以利用 Docker cache）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 預先下載 sentence-transformers 模型，避免執行時下載
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# 複製應用程式碼
COPY . .

# 設定預設環境變數
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 預設啟動 FastAPI（可被 docker-compose 覆蓋）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
