#!/bin/sh
# 覆核 API 容器的啟動順序：建立資料表 → 第一次啟動時向 mock 同步一次 → 啟動 API
set -e
alembic upgrade head
if ! ls /data/state/snapshots/*.json >/dev/null 2>&1; then
  echo "還沒有同步快照，向 mock 做第一次同步…"
  python -m app.sync --full
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
