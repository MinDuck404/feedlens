#!/usr/bin/env bash
# FeedLens - chạy toàn bộ trên máy bằng một lệnh (macOS / Linux): ./start.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"; FRONTEND="$ROOT/frontend"; VENV="$BACKEND/.venv"
PORT="${FEEDLENS_PORT:-8765}"
step() { printf '\033[36m==> %s\033[0m\n' "$1"; }
fail() { printf '\033[31mLỗi: %s\033[0m\n' "$1"; exit 1; }
has() { command -v "$1" >/dev/null 2>&1; }

if [ ! -x "$VENV/bin/python" ]; then
  step "Tạo môi trường Python (lần đầu)…"
  if has uv; then uv venv "$VENV" --python 3.11 -q
  elif has python3; then python3 -m venv "$VENV"
  else fail "Chưa có Python 3.10+. Tải tại https://www.python.org/downloads/"; fi
fi
HASH="$(cksum "$BACKEND/pyproject.toml" | cut -d' ' -f1)"
if [ "$(cat "$VENV/.feedlens-installed" 2>/dev/null)" != "$HASH" ]; then
  step "Cài thư viện Python…"
  if has uv; then uv pip install -e "$BACKEND" -q --python "$VENV/bin/python"
  else "$VENV/bin/python" -m pip install -q --upgrade pip && "$VENV/bin/python" -m pip install -q -e "$BACKEND"; fi
  echo "$HASH" > "$VENV/.feedlens-installed"
fi

DIST="$FRONTEND/dist/index.html"
if [ ! -f "$DIST" ] || [ -n "$(find "$FRONTEND/src" "$FRONTEND/index.html" "$FRONTEND/package.json" -newer "$DIST" -print -quit)" ]; then
  has npm || fail "Cần Node.js để build giao diện lần đầu. Tải tại https://nodejs.org (bản LTS)."
  step "Build giao diện…"
  (cd "$FRONTEND" && { [ -d node_modules ] || npm ci --no-audit --no-fund --loglevel=error; } && VITE_API_URL="" npm run build --silent)
fi

unset FEEDLENS_MODE
step "FeedLens đang chạy tại http://127.0.0.1:$PORT  (Ctrl+C để dừng)"
exec "$VENV/bin/feedlens" serve --port "$PORT" --open
