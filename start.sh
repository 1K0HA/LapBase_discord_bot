#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"

RUNTIME_DIR="$PWD/.runtime"
UV_BIN_DIR="$RUNTIME_DIR/uv-bin"
UV_EXE="$UV_BIN_DIR/uv"
export UV_INSTALL_DIR="$UV_BIN_DIR"
export UV_NO_MODIFY_PATH=1
export UV_PYTHON_INSTALL_DIR="$RUNTIME_DIR/python"
export UV_PYTHON_BIN_DIR="$RUNTIME_DIR/python-bin"
export UV_CACHE_DIR="$RUNTIME_DIR/cache"
export UV_MANAGED_PYTHON=1

fail() {
  code="${1:-1}"
  echo
  echo "[ERROR] LapBase could not start. Read the error above."
  if [ -t 0 ]; then
    read -r -p "Press Enter to close..." _
  fi
  exit "$code"
}

[ -f .env ] || { echo "[ERROR] .env not found."; fail 1; }
[ -f requirements.txt ] || { echo "[ERROR] requirements.txt not found."; fail 1; }
mkdir -p "$UV_BIN_DIR" "$RUNTIME_DIR"

if [ ! -x "$UV_EXE" ]; then
  echo "[LapBase] Installing private uv runtime..."
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh || fail 1
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://astral.sh/uv/install.sh | sh || fail 1
  else
    echo "[ERROR] curl or wget is required for first launch."
    fail 1
  fi
fi

"$UV_EXE" --version || fail 1

echo "[LapBase] Installing/locating private Python 3.14..."
"$UV_EXE" python install 3.14 --managed-python || fail 1
PYTHON_314="$($UV_EXE python find 3.14 --managed-python)" || fail 1
[ -x "$PYTHON_314" ] || { echo "[ERROR] Managed Python not found: $PYTHON_314"; fail 1; }

echo "[LapBase] Managed Python: $PYTHON_314"
"$PYTHON_314" -c "import sys; print('[LapBase] Managed version:', sys.version); raise SystemExit(0 if sys.version_info[:2] == (3,14) else 1)" || fail 1

if [ -x .venv/bin/python ]; then
  .venv/bin/python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,14) else 1)" >/dev/null 2>&1 || {
    echo "[LapBase] Existing .venv is not Python 3.14. Rebuilding..."
    rm -rf .venv
  }
fi

if [ ! -x .venv/bin/python ]; then
  echo "[LapBase] Creating .venv from exact managed Python 3.14..."
  "$UV_EXE" venv .venv --python "$PYTHON_314" --seed || fail 1
fi

.venv/bin/python -c "import sys; print('[LapBase] Venv Python:', sys.executable); print('[LapBase] Venv version:', sys.version); raise SystemExit(0 if sys.version_info[:2] == (3,14) else 1)" || fail 1

echo "[LapBase] Synchronizing dependencies into .venv..."
"$UV_EXE" pip install --python .venv/bin/python -r requirements.txt || fail 1

echo "[LapBase] Verifying dependencies..."
.venv/bin/python -c "import aiogram, discord, groq, asyncpg, dotenv; print('[OK] aiogram', aiogram.__version__); print('[OK] discord.py', discord.__version__); print('[OK] groq', groq.__version__); print('[OK] asyncpg', asyncpg.__version__)" || fail 1

echo "[LapBase] Starting..."
.venv/bin/python -m app.main
code=$?
[ "$code" -eq 0 ] || fail "$code"
