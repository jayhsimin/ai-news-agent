#!/bin/bash
# ═══════════════════════════════════════════════
# Ollama 初始化腳本
# 等待 Ollama 服務啟動後自動下載指定模型
# ═══════════════════════════════════════════════

set -e

MODEL=${OLLAMA_MODEL:-"qwen2.5:7b"}
OLLAMA_URL=${OLLAMA_BASE_URL:-"http://ollama:11434"}
MAX_WAIT=120  # 最多等待 120 秒

echo "🔄 等待 Ollama 服務啟動..."
for i in $(seq 1 $MAX_WAIT); do
    if curl -sf "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; then
        echo "✅ Ollama 服務已就緒"
        break
    fi
    if [ $i -eq $MAX_WAIT ]; then
        echo "❌ Ollama 服務啟動逾時（${MAX_WAIT}s）"
        exit 1
    fi
    echo "  等待中... ${i}/${MAX_WAIT}s"
    sleep 1
done

# 檢查模型是否已下載
echo "🔍 檢查模型 ${MODEL} 是否已下載..."
MODELS=$(curl -sf "${OLLAMA_URL}/api/tags" | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = [m['name'] for m in data.get('models', [])]
print('\n'.join(models))
" 2>/dev/null || echo "")

if echo "$MODELS" | grep -q "^${MODEL}"; then
    echo "✅ 模型 ${MODEL} 已存在，無需重新下載"
else
    echo "📥 開始下載模型 ${MODEL}..."
    echo "   這可能需要數分鐘，請耐心等候..."
    curl -sf -X POST "${OLLAMA_URL}/api/pull" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"${MODEL}\"}" \
        | python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        data = json.loads(line)
        status = data.get('status', '')
        if 'total' in data and 'completed' in data:
            pct = int(data['completed'] / data['total'] * 100)
            print(f'  下載進度：{pct}%', end='\r', flush=True)
        elif status:
            print(f'  {status}')
    except:
        pass
print()
"
    echo "✅ 模型 ${MODEL} 下載完成！"
fi

echo ""
echo "🎉 Ollama 初始化完成！"
echo "   可用模型："
curl -sf "${OLLAMA_URL}/api/tags" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for m in data.get('models', []):
    print(f\"   - {m['name']}\")
" 2>/dev/null || echo "   （無法取得模型列表）"
