#!/usr/bin/env bash
set -u

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1

# Не меняем системную locale: используем UTF-8 locale только если она уже доступна.
if command -v locale >/dev/null 2>&1; then
  if locale -a 2>/dev/null | grep -Eiq '^C\.UTF-8$'; then
    export LANG=C.UTF-8
    export LC_ALL=C.UTF-8
  elif locale -a 2>/dev/null | grep -Eiq '^C\.utf8$'; then
    export LANG=C.utf8
    export LC_ALL=C.utf8
  fi
fi

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$PROJECT_ROOT" || exit 90

RUNTIME_MANIFEST="$PROJECT_ROOT/.1kds/runtime.env"
STATE_DIR="$PROJECT_ROOT/.1kds/state"
RUNTIME_DIR="$PROJECT_ROOT/.runtime"
UV_DIR="$RUNTIME_DIR/uv"
UV_EXE="$UV_DIR/uv"
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
BOOT_LOG="$PROJECT_ROOT/logs/bootstrap.log"
PREPARE_ONLY=0
DEV_MODE=0

for arg in "$@"; do
  case "$arg" in
    --prepare-only) PREPARE_ONLY=1 ;;
    --dev) DEV_MODE=1 ;;
    *) echo "[ВНИМАНИЕ] Неизвестный аргумент: $arg" ;;
  esac
done

mkdir -p "$PROJECT_ROOT/logs" "$STATE_DIR" "$RUNTIME_DIR" || exit 91
: > "$BOOT_LOG"

log() { printf '%s\n' "$*" | tee -a "$BOOT_LOG"; }
bootstrap_fail() {
  code="${1:-1}"; shift || true
  log "[ОШИБКА] Не удалось подготовить LapBase."
  log "Что произошло: ${*:-неизвестная ошибка}"
  log "Что можно сделать: проверьте сообщение выше и файл .env; при повреждении runtime удалите только .runtime и .venv и запустите снова."
  log "Техническая информация: exit code $code"
  log "Подробный лог: $BOOT_LOG"
  printf '\n[ДЕТАЛИ] Последние строки bootstrap.log:\n'
  if [ -f "$BOOT_LOG" ]; then
    tail -n 20 "$BOOT_LOG" 2>/dev/null || true
  fi
  printf '[КОНЕЦ ДЕТАЛЕЙ]\n'
  if [ -t 0 ] && [ "$PREPARE_ONLY" -eq 0 ]; then
    printf 'Нажмите Enter, чтобы закрыть окно...'
    read -r _
  fi
  exit "$code"
}

application_fail() {
  code="${1:-1}"; shift || true
  log "[ОШИБКА] LapBase завершился с ошибкой."
  log "Что произошло: ${*:-неизвестная ошибка}"
  if [ "$code" -eq 73 ]; then
    log "Что можно сделать: остановите уже работающий экземпляр LapBase и повторите запуск."
  else
    log "Что можно сделать: проверьте последние строки logs/lapbase.log и сообщение Python выше."
  fi
  log "Техническая информация: exit code $code"
  log "Основной лог: $PROJECT_ROOT/logs/lapbase.log"
  printf '\n[ДЕТАЛИ] Последние строки lapbase.log:\n'
  if [ -f "$PROJECT_ROOT/logs/lapbase.log" ]; then
    tail -n 20 "$PROJECT_ROOT/logs/lapbase.log" 2>/dev/null || true
  fi
  printf '[КОНЕЦ ДЕТАЛЕЙ]\n'
  if [ -t 0 ] && [ "$PREPARE_ONLY" -eq 0 ]; then
    printf 'Нажмите Enter, чтобы закрыть окно...'
    read -r _
  fi
  exit "$code"
}

[ -f "$PROJECT_ROOT/pyproject.toml" ] || bootstrap_fail 9 "не найден pyproject.toml"
APP_VERSION="$(awk -F'"' '/^version = "/ {print $2; exit}' "$PROJECT_ROOT/pyproject.toml")"
[ -n "$APP_VERSION" ] || bootstrap_fail 9 "не удалось прочитать версию из pyproject.toml"

[ -f "$RUNTIME_MANIFEST" ] || bootstrap_fail 10 "не найден .1kds/runtime.env"
# shellcheck disable=SC1090
. "$RUNTIME_MANIFEST"

export UV_NO_MODIFY_PATH=1
export UV_PYTHON_INSTALL_DIR="$RUNTIME_DIR/python"
export UV_PYTHON_INSTALL_BIN=0
export UV_PYTHON_NO_REGISTRY=1
export UV_PYTHON_INSTALL_REGISTRY=0
export UV_CACHE_DIR="$RUNTIME_DIR/cache"
export UV_MANAGED_PYTHON=1
export UV_PROJECT_ENVIRONMENT="$VENV_DIR"

arch="$(uname -m)"
case "$arch" in
  x86_64|amd64)
    UV_ASSET="$UV_LINUX_X64_ASSET"
    UV_SHA256="$UV_LINUX_X64_SHA256"
    PLATFORM_LABEL="Linux x86_64"
    ;;
  aarch64|arm64)
    UV_ASSET="$UV_LINUX_ARM64_ASSET"
    UV_SHA256="$UV_LINUX_ARM64_SHA256"
    PLATFORM_LABEL="Linux arm64"
    ;;
  *) bootstrap_fail 11 "архитектура Linux '$arch' не поддерживается этой сборкой" ;;
esac

log "============================================================"
log "LapBase v$APP_VERSION"
log "Платформа: $PLATFORM_LABEL"
log "Режим: Portable L2"
log "Кодировка: UTF-8"
log "============================================================"

check_uv() {
  [ -x "$UV_EXE" ] || return 1
  version="$($UV_EXE --version 2>/dev/null | awk '{print $2}')"
  [ "$version" = "$UV_VERSION" ]
}

download() {
  url="$1" output="$2"
  if command -v curl >/dev/null 2>&1; then
    curl --proto '=https' --tlsv1.2 -fL "$url" -o "$output" >>"$BOOT_LOG" 2>&1
  elif command -v wget >/dev/null 2>&1; then
    wget --https-only -O "$output" "$url" >>"$BOOT_LOG" 2>&1
  else
    return 127
  fi
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    return 127
  fi
}

log "[ПРОВЕРКА] Проверяем локальный uv $UV_VERSION..."
if ! check_uv; then
  log "[УСТАНОВКА] Загружаем проверяемый uv $UV_VERSION для $arch..."
  command -v tar >/dev/null 2>&1 || bootstrap_fail 12 "не найден системный tar, необходимый только для bootstrap"
  tmp="$RUNTIME_DIR/uv-download.tmp"
  url="$UV_RELEASE_BASE/$UV_VERSION/$UV_ASSET"
  download "$url" "$tmp" || bootstrap_fail 13 "не удалось скачать $url"
  actual="$(sha256_file "$tmp")" || bootstrap_fail 14 "не найден sha256sum/shasum"
  [ "$actual" = "$UV_SHA256" ] || bootstrap_fail 15 "SHA-256 uv не совпал; файл не будет исполнен"
  rm -rf "$UV_DIR"
  mkdir -p "$UV_DIR" || bootstrap_fail 16 "не удалось создать $UV_DIR"
  tar -xzf "$tmp" -C "$RUNTIME_DIR" >>"$BOOT_LOG" 2>&1 || bootstrap_fail 17 "не удалось распаковать uv"
  extracted="$RUNTIME_DIR/uv-$([[ "$arch" = aarch64 || "$arch" = arm64 ]] && echo aarch64 || echo x86_64)-unknown-linux-gnu/uv"
  [ -x "$extracted" ] || bootstrap_fail 18 "uv не найден после распаковки"
  mv "$extracted" "$UV_EXE" || bootstrap_fail 19 "не удалось переместить uv"
  rm -rf "$RUNTIME_DIR/uv-"*"-unknown-linux-gnu" "$tmp"
  check_uv || bootstrap_fail 20 "локальный uv имеет неверную версию после установки"
fi
log "[OK] Локальный uv найден: $($UV_EXE --version)."

log "[ПРОВЕРКА] Проверяем локальный Python $PYTHON_VERSION..."
PYTHON_EXE="$($UV_EXE python find "$PYTHON_VERSION" --managed-python 2>>"$BOOT_LOG" || true)"
if [ -z "$PYTHON_EXE" ] || [ ! -x "$PYTHON_EXE" ]; then
  log "[УСТАНОВКА] Устанавливаем локальный Python $PYTHON_VERSION..."
  "$UV_EXE" python install "$PYTHON_VERSION" --managed-python --no-bin --no-registry >>"$BOOT_LOG" 2>&1 || bootstrap_fail 21 "uv не смог установить Python $PYTHON_VERSION"
  PYTHON_EXE="$($UV_EXE python find "$PYTHON_VERSION" --managed-python 2>>"$BOOT_LOG")" || bootstrap_fail 22 "uv не смог найти установленный Python"
fi
"$PYTHON_EXE" -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3,14,7) else 1)" >>"$BOOT_LOG" 2>&1 || bootstrap_fail 23 "локальный Python имеет неверную версию"
log "[OK] Локальный Python найден: $PYTHON_VERSION."

ENV_STATE="NORMAL_START"
if [ ! -x "$VENV_PYTHON" ]; then
  ENV_STATE="FIRST_INSTALL"
else
  "$VENV_PYTHON" -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3,14,7) else 1)" >/dev/null 2>&1 || ENV_STATE="BROKEN_ENVIRONMENT"
fi

if [ "$ENV_STATE" = "BROKEN_ENVIRONMENT" ]; then
  log "[ВОССТАНОВЛЕНИЕ] .venv повреждён или создан другой версией Python. Пересоздаём только environment..."
  case "$VENV_DIR" in "$PROJECT_ROOT"/*) rm -rf "$VENV_DIR" ;; *) bootstrap_fail 24 "небезопасный путь .venv" ;; esac
  ENV_STATE="FIRST_INSTALL"
fi

if [ "$ENV_STATE" = "FIRST_INSTALL" ]; then
  log "[УСТАНОВКА] Создаём локальный .venv через Python $PYTHON_VERSION..."
  "$UV_EXE" venv "$VENV_DIR" --python "$PYTHON_EXE" --seed >>"$BOOT_LOG" 2>&1 || bootstrap_fail 25 "не удалось создать .venv"
fi

[ -x "$VENV_PYTHON" ] || bootstrap_fail 26 "в .venv отсутствует python"

log "[ПРОВЕРКА] Проверяем dependency state..."
if [ ! -f "$PROJECT_ROOT/uv.lock" ]; then
  log "[УСТАНОВКА] Создаём uv.lock для первого запуска..."
  "$UV_EXE" lock --python "$PYTHON_EXE" >>"$BOOT_LOG" 2>&1 || bootstrap_fail 27 "не удалось создать uv.lock"
fi

fingerprint="$(cat "$PROJECT_ROOT/pyproject.toml" "$PROJECT_ROOT/uv.lock" | sha256_file /dev/stdin 2>/dev/null || true)"
if [ -z "$fingerprint" ]; then
  fingerprint="$(sha256_file "$PROJECT_ROOT/uv.lock")-$(sha256_file "$PROJECT_ROOT/pyproject.toml")"
fi
state_file="$STATE_DIR/deps-prod.sha256"
[ "$DEV_MODE" -eq 1 ] && state_file="$STATE_DIR/deps-dev.sha256"
old_fingerprint=""
[ -f "$state_file" ] && old_fingerprint="$(cat "$state_file")"

need_sync=0
[ "$old_fingerprint" != "$fingerprint" ] && need_sync=1
[ "$ENV_STATE" = "FIRST_INSTALL" ] && need_sync=1

if [ "$need_sync" -eq 1 ]; then
  log "[УСТАНОВКА] Синхронизируем зависимости по uv.lock..."
  if [ "$DEV_MODE" -eq 1 ]; then
    "$UV_EXE" sync --frozen --python "$PYTHON_EXE" >>"$BOOT_LOG" 2>&1 || bootstrap_fail 28 "uv sync завершился ошибкой"
  else
    "$UV_EXE" sync --frozen --no-dev --python "$PYTHON_EXE" >>"$BOOT_LOG" 2>&1 || bootstrap_fail 28 "uv sync завершился ошибкой"
  fi
  printf '%s\n' "$fingerprint" > "$state_file.tmp"
  mv "$state_file.tmp" "$state_file"
else
  log "[OK] Dependency fingerprint не изменился; переустановка не требуется."
fi

log "[ПРОВЕРКА] Проверяем environment..."
"$VENV_PYTHON" -c "import aiogram, discord, groq, asyncpg, dotenv" >>"$BOOT_LOG" 2>&1 || bootstrap_fail 29 "не импортируются обязательные зависимости"
log "[OK] Локальное окружение готово."

if [ "$PREPARE_ONLY" -eq 1 ]; then
  log "[OK] Подготовка завершена без запуска приложения."
  exit 0
fi

[ -f "$PROJECT_ROOT/.env" ] || bootstrap_fail 30 "не найден .env; скопируйте .env.example в .env и заполните значения"

log "[ЗАПУСК] Запускаем LapBase v$APP_VERSION..."
"$VENV_PYTHON" -m app.main
code=$?
if [ "$code" -eq 73 ]; then
  application_fail 73 "LapBase уже запущен; второй экземпляр заблокирован до миграций."
fi
[ "$code" -eq 0 ] || application_fail "$code" "приложение завершилось с ошибкой"
log "[OK] LapBase завершён штатно."
