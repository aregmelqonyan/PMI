#!/usr/bin/env bash
# One command to set up and open EngiReq-AI on http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x backend/.venv/bin/python ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install --no-fund --no-audit)
fi
(cd frontend && npm run build)

echo "EngiReq-AI is running at http://127.0.0.1:8000 (Ctrl+C to stop)"
cd backend
exec .venv/bin/python -m uvicorn engireq.api:app --host 127.0.0.1 --port 8000
