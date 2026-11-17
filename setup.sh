#!/bin/sh
# 產生 .env（mock 用的隨機憑證）。已存在就不覆蓋。
set -eu
cd "$(dirname "$0")"

if [ -f .env ]; then
  echo ".env 已存在，略過。"
  exit 0
fi

rand() { python3 -c "import secrets; print(secrets.token_urlsafe(24))"; }
uuid() { python3 -c "import uuid; print(uuid.uuid4())"; }

cat > .env <<EOF
MOCK_GRAPH_READER_ID=$(uuid)
MOCK_GRAPH_READER_SECRET=$(rand)
MOCK_GRAPH_WRITER_ID=$(uuid)
MOCK_GRAPH_WRITER_SECRET=$(rand)
MOCK_GITHUB_READ_TOKEN=$(rand)
MOCK_GITHUB_ADMIN_TOKEN=$(rand)
MOCK_PORT=8391
POSTGRES_PASSWORD=$(rand)
JWT_SECRET=$(rand)$(rand)
# demo = 從 HR 名冊選人登入，只供本機示範
AUTH_MODE=demo
# 選用：AI 規則提案。沒設定就停用 AI 功能，其他功能照常。接本機 Ollama 的範例：
# LLM_PROVIDER=openai_compatible
# LLM_BASE_URL=http://host.docker.internal:11434/v1
# LLM_MODEL=qwen3.5:9b
# LLM_REASONING_EFFORT=none
# 改用 Claude：LLM_PROVIDER=anthropic、LLM_MODEL=claude-haiku-5-5、LLM_API_KEY=...
EOF
chmod 600 .env
echo "已產生 .env。接著執行：docker compose up -d --build"
