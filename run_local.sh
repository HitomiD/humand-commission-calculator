#!/usr/bin/env bash
# Runs the tool locally: the payments mock and the calculator.
# It does the same steps as the README's "by hand" commands. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")"

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
command -v node >/dev/null || { echo "node is required" >&2; exit 1; }

# 1. Python environment: created the first time, requirements checked every time.
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements-dev.txt

# 2. Settings: .env is created from the example the first time.
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example."
fi
if ! grep -q '^GEMINI_API_KEY=.' .env; then
  echo "GEMINI_API_KEY is empty in .env: the page will work, but every line will go to review." >&2
fi

# 3. Payments mock on :4000, in the background; stopped when this script exits.
node mock-api/dev-server.cjs &
mock_pid=$!
trap 'kill "$mock_pid" 2>/dev/null || true' EXIT
sleep 1
kill -0 "$mock_pid" 2>/dev/null || { echo "The payments mock didn't start (is port 4000 in use?)" >&2; exit 1; }

# 4. The calculator on :8000, in the foreground.
echo "Open http://localhost:8000"
.venv/bin/uvicorn api.index:app --reload --port 8000
