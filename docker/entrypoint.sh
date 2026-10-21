#!/bin/sh
set -eu

if [ "${1:-}" = "api" ]; then
  alembic upgrade head
  exec uvicorn ai_governance.api.app:create_app --factory --host 0.0.0.0 --port 8000
fi

if [ "${1:-}" = "dashboard" ]; then
  exec streamlit run frontend/app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
fi

exec "$@"
