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
  if ! has uv && ! has python3; then
    # Máy chưa có Python: cài uv (của Astral), uv tự tải Python 3.11 riêng cho FeedLens.
    step "Chưa có Python - đang cài uv (chỉ lần đầu)…"
    if has curl; then curl -LsSf https://astral.sh/uv/install.sh | sh
    elif has wget; then wget -qO- https://astral.sh/uv/install.sh | sh
    else fail "Cần curl hoặc wget để cài uv, hoặc cài Python 3.10+ tại https://www.python.org/downloads/"; fi
    export PATH="$HOME/.local/bin:$PATH"
    has uv || fail "Cài uv xong nhưng chưa thấy lệnh uv. Mở terminal mới rồi chạy lại ./start.sh"
  fi
  if has uv; then uv venv "$VENV" --python 3.11 -q
  else python3 -m venv "$VENV"; fi
fi
HASH="$(cksum "$BACKEND/pyproject.toml" | cut -d' ' -f1)"
if [ "$(cat "$VENV/.feedlens-installed" 2>/dev/null)" != "$HASH" ]; then
  step "Cài thư viện Python…"
  if has uv; then uv pip install -e "$BACKEND" -q --python "$VENV/bin/python"
  else "$VENV/bin/python" -m pip install -q --upgrade pip && "$VENV/bin/python" -m pip install -q -e "$BACKEND"; fi
  echo "$HASH" > "$VENV/.feedlens-installed"
fi

DIST="$FRONTEND/dist/index.html"
NEED_BUILD=0
if [ ! -f "$DIST" ] || [ -n "$(find "$FRONTEND/src" "$FRONTEND/index.html" "$FRONTEND/package.json" -newer "$DIST" -print -quit)" ]; then NEED_BUILD=1; fi
if [ "$NEED_BUILD" = 1 ] && [ -f "$DIST" ] && ! has npm; then
  # Bản tải từ GitHub Releases có giao diện dựng sẵn; không có Node thì dùng luôn bản đó.
  printf '\033[33m%s\033[0m\n' "Không có Node.js, dùng giao diện dựng sẵn."
  NEED_BUILD=0
fi
if [ "$NEED_BUILD" = 1 ]; then
  has npm || fail "Cần Node.js để build giao diện. Tải bản dựng sẵn ở https://github.com/MinDuck404/feedlens/releases (không cần Node), hoặc cài Node.js LTS tại https://nodejs.org."
  step "Build giao diện…"
  (cd "$FRONTEND" && { [ -d node_modules ] || npm ci --no-audit --no-fund --loglevel=error; } && VITE_API_URL="" npm run build --silent)
fi

unset FEEDLENS_MODE
step "FeedLens đang chạy tại http://127.0.0.1:$PORT  (Ctrl+C để dừng)"
exec "$VENV/bin/feedlens" serve --port "$PORT" --open
