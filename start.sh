#!/usr/bin/env bash
# BOT MATRIX — one-command start (Frontend + Backend)
# Usage:  chmod +x start.sh && ./start.sh
set -e
cd "$(dirname "$0")"

echo "=============================================="
echo "  BOT MATRIX — Starting"
echo "=============================================="

# Optional: start PostgreSQL via Docker
if command -v docker >/dev/null 2>&1; then
  if [ "${USE_POSTGRES:-0}" = "1" ]; then
    echo "[1/4] Starting PostgreSQL (docker compose)..."
    docker compose up -d postgres
    echo "      Waiting for Postgres health..."
    for i in $(seq 1 30); do
      if docker compose exec -T postgres pg_isready -U telebot -d telebot_db >/dev/null 2>&1; then
        echo "      Postgres is ready."
        break
      fi
      sleep 1
    done
    export DATABASE_URL="${DATABASE_URL:-postgresql://telebot:telebot_secret@127.0.0.1:5432/telebot_db}"
    export USE_POSTGRES=1
  else
    echo "[1/4] Using SQLite (set USE_POSTGRES=1 to use Docker Postgres)"
  fi
else
  echo "[1/4] Docker not found — using SQLite database"
fi

# Python deps
echo "[2/4] Installing Python backend dependencies..."
python3 -m pip install -q -r backend/requirements.txt 2>/dev/null || python3 -m pip install -q psycopg2-binary || true

# Node deps
echo "[3/4] Installing Node dependencies..."
if command -v bun >/dev/null 2>&1; then
  bun install
elif command -v npm >/dev/null 2>&1; then
  npm install
else
  echo "ERROR: npm or bun required"
  exit 1
fi

# Run (server.ts spawns Python backend + Vite)
echo "[4/4] Starting cluster (Express proxy + Vite + Python API)..."
echo "      Open: http://localhost:3000"
echo "=============================================="
export PYTHON_BACKEND_PORT=5001
if command -v bun >/dev/null 2>&1; then
  bun run dev
else
  npm run dev
fi
