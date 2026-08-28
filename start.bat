@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PROJECT_ROOT=%CD%"
set "RUNTIME_MANIFEST=%PROJECT_ROOT%\.1kds\runtime.env"
set "STATE_DIR=%PROJECT_ROOT%\.1kds\state"
set "RUNTIME_DIR=%PROJECT_ROOT%\.runtime"
set "UV_DIR=%RUNTIME_DIR%\uv"
set "UV_EXE=%UV_DIR%\uv.exe"
set "VENV_DIR=%PROJECT_ROOT%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "BOOT_LOG=%PROJECT_ROOT%\logs\bootstrap.log"
set "PREPARE_ONLY=0"
set "DEV_MODE=0"
set "FINAL_EXIT=0"

:PARSE_ARGS
if "%~1"=="" goto ARGS_DONE
if /I "%~1"=="--prepare-only" set "PREPARE_ONLY=1"
if /I "%~1"=="--dev" set "DEV_MODE=1"
shift
goto PARSE_ARGS
:ARGS_DONE

if not exist "%PROJECT_ROOT%\logs" mkdir "%PROJECT_ROOT%\logs"
if not exist "%STATE_DIR%" mkdir "%STATE_DIR%"
if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"
type nul > "%BOOT_LOG%"

set "APP_VERSION="
if exist "%PROJECT_ROOT%\pyproject.toml" (
  for /f "tokens=3" %%V in ('findstr /b /c:"version = " "%PROJECT_ROOT%\pyproject.toml" 2^>nul') do set "APP_VERSION=%%~V"
)
if not defined APP_VERSION (
  call :BOOT_FAIL 9 "не удалось прочитать версию из pyproject.toml"
  goto END
)

if not exist "%RUNTIME_MANIFEST%" (
  call :BOOT_FAIL 10 "не найден .1kds\runtime.env"
  goto END
)
for /f "usebackq tokens=1,* delims==" %%A in ("%RUNTIME_MANIFEST%") do set "%%A=%%B"

set "UV_NO_MODIFY_PATH=1"
set "UV_PYTHON_INSTALL_DIR=%RUNTIME_DIR%\python"
set "UV_PYTHON_INSTALL_BIN=0"
set "UV_PYTHON_NO_REGISTRY=1"
set "UV_PYTHON_INSTALL_REGISTRY=0"
set "UV_CACHE_DIR=%RUNTIME_DIR%\cache"
set "UV_MANAGED_PYTHON=1"
set "UV_PROJECT_ENVIRONMENT=%VENV_DIR%"

call :LOG "[ПРОВЕРКА] Определяем архитектуру Windows..."
for /f "delims=" %%A in ('powershell -NoProfile -Command "[System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()"') do set "ARCH=%%A"
if /I "%ARCH%"=="X64" goto ARCH_X64
call :BOOT_FAIL 11 "архитектура Windows %ARCH% не поддерживается этой сборкой"
goto END
:ARCH_X64
set "UV_ASSET=%UV_WINDOWS_X64_ASSET%"
set "UV_SHA256=%UV_WINDOWS_X64_SHA256%"
title LapBase v%APP_VERSION%

call :LOG "============================================================"
call :LOG "LapBase v%APP_VERSION%"
call :LOG "Платформа: Windows x64"
call :LOG "Режим: Portable L2"
call :LOG "Кодировка: UTF-8"
call :LOG "============================================================"

call :LOG "[ПРОВЕРКА] Проверяем локальный uv %UV_VERSION%..."
call :CHECK_UV
if not errorlevel 1 goto UV_READY
call :LOG "[УСТАНОВКА] Загружаем проверяемый uv %UV_VERSION%..."
where powershell >nul 2>nul
if errorlevel 1 (
  call :BOOT_FAIL 12 "PowerShell не найден"
  goto END
)
set "UV_TMP=%RUNTIME_DIR%\uv-download.tmp.zip"
set "UV_URL=%UV_RELEASE_BASE%/%UV_VERSION%/%UV_ASSET%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '%UV_URL%' -OutFile '%UV_TMP%'" >>"%BOOT_LOG%" 2>&1
if errorlevel 1 (
  call :BOOT_FAIL 13 "не удалось скачать %UV_URL%"
  goto END
)
for /f "delims=" %%H in ('powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath '%UV_TMP%').Hash.ToLowerInvariant()"') do set "ACTUAL_SHA=%%H"
if /I not "%ACTUAL_SHA%"=="%UV_SHA256%" (
  call :BOOT_FAIL 15 "SHA-256 uv не совпал; файл не будет исполнен"
  goto END
)
if exist "%UV_DIR%" rmdir /s /q "%UV_DIR%"
mkdir "%UV_DIR%"
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%UV_TMP%' -DestinationPath '%UV_DIR%' -Force" >>"%BOOT_LOG%" 2>&1
if errorlevel 1 (
  call :BOOT_FAIL 17 "не удалось распаковать uv"
  goto END
)
del /q "%UV_TMP%" >nul 2>nul
call :CHECK_UV
if errorlevel 1 (
  call :BOOT_FAIL 20 "локальный uv имеет неверную версию после установки"
  goto END
)
:UV_READY
for /f "delims=" %%V in ('"%UV_EXE%" --version') do call :LOG "[OK] Локальный uv найден: %%V."

call :LOG "[ПРОВЕРКА] Проверяем локальный Python %PYTHON_VERSION%..."
call :FIND_MANAGED_PYTHON
if not errorlevel 1 goto PYTHON_READY

call :LOG "[УСТАНОВКА] Устанавливаем локальный Python %PYTHON_VERSION%..."
"%UV_EXE%" python install "%PYTHON_VERSION%" --managed-python --no-bin --no-registry >>"%BOOT_LOG%" 2>&1
if errorlevel 1 (
  call :BOOT_FAIL 21 "uv не смог установить Python %PYTHON_VERSION%"
  goto END
)

call :FIND_MANAGED_PYTHON
if errorlevel 1 (
  call :BOOT_FAIL 22 "uv не смог найти установленный Python"
  goto END
)

:PYTHON_READY
"%PYTHON_EXE%" -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3,14,7) else 1)" >>"%BOOT_LOG%" 2>&1
if errorlevel 1 (
  call :BOOT_FAIL 23 "локальный Python имеет неверную версию"
  goto END
)
call :LOG "[OK] Локальный Python найден: %PYTHON_VERSION%."

set "ENV_STATE=NORMAL_START"
if not exist "%VENV_PYTHON%" set "ENV_STATE=FIRST_INSTALL"
if exist "%VENV_PYTHON%" (
  "%VENV_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3,14,7) else 1)" >nul 2>nul
  if errorlevel 1 set "ENV_STATE=BROKEN_ENVIRONMENT"
)
if "%ENV_STATE%"=="BROKEN_ENVIRONMENT" (
  call :LOG "[ВОССТАНОВЛЕНИЕ] .venv повреждён или создан другой версией Python. Пересоздаём environment..."
  rmdir /s /q "%VENV_DIR%"
  set "ENV_STATE=FIRST_INSTALL"
)
if "%ENV_STATE%"=="FIRST_INSTALL" (
  call :LOG "[УСТАНОВКА] Создаём локальный .venv через Python %PYTHON_VERSION%..."
  "%UV_EXE%" venv "%VENV_DIR%" --python "%PYTHON_EXE%" --seed >>"%BOOT_LOG%" 2>&1
  if errorlevel 1 (
    call :BOOT_FAIL 25 "не удалось создать .venv"
    goto END
  )
)
if not exist "%VENV_PYTHON%" (
  call :BOOT_FAIL 26 "в .venv отсутствует python.exe"
  goto END
)

call :LOG "[ПРОВЕРКА] Проверяем dependency state..."
if exist "%PROJECT_ROOT%\uv.lock" goto LOCK_READY
call :LOG "[УСТАНОВКА] Создаём uv.lock для первого запуска..."
"%UV_EXE%" lock --python "%PYTHON_EXE%" >>"%BOOT_LOG%" 2>&1
if errorlevel 1 (
  call :BOOT_FAIL 27 "не удалось создать uv.lock"
  goto END
)
:LOCK_READY
for /f "delims=" %%H in ('powershell -NoProfile -Command "$h=[System.Security.Cryptography.SHA256]::Create(); $b=[Text.Encoding]::UTF8.GetBytes((Get-Content -Raw -LiteralPath 'pyproject.toml') + (Get-Content -Raw -LiteralPath 'uv.lock')); ([BitConverter]::ToString($h.ComputeHash($b))).Replace('-','').ToLowerInvariant()"') do set "FINGERPRINT=%%H"
set "STATE_FILE=%STATE_DIR%\deps-prod.sha256"
if "%DEV_MODE%"=="1" set "STATE_FILE=%STATE_DIR%\deps-dev.sha256"
set "OLD_FINGERPRINT="
if exist "%STATE_FILE%" set /p OLD_FINGERPRINT=<"%STATE_FILE%"
set "NEED_SYNC=0"
if /I not "%OLD_FINGERPRINT%"=="%FINGERPRINT%" set "NEED_SYNC=1"
if "%ENV_STATE%"=="FIRST_INSTALL" set "NEED_SYNC=1"

if "%NEED_SYNC%"=="0" goto DEPS_READY
call :LOG "[УСТАНОВКА] Синхронизируем зависимости по uv.lock..."
if "%DEV_MODE%"=="1" (
  "%UV_EXE%" sync --frozen --python "%PYTHON_EXE%" >>"%BOOT_LOG%" 2>&1
) else (
  "%UV_EXE%" sync --frozen --no-dev --python "%PYTHON_EXE%" >>"%BOOT_LOG%" 2>&1
)
if errorlevel 1 (
  call :BOOT_FAIL 28 "uv sync завершился ошибкой"
  goto END
)
>"%STATE_FILE%.tmp" echo %FINGERPRINT%
move /y "%STATE_FILE%.tmp" "%STATE_FILE%" >nul
:DEPS_READY
if "%NEED_SYNC%"=="0" call :LOG "[OK] Dependency fingerprint не изменился; переустановка не требуется."

call :LOG "[ПРОВЕРКА] Проверяем environment..."
"%VENV_PYTHON%" -c "import aiogram, discord, groq, asyncpg, dotenv" >>"%BOOT_LOG%" 2>&1
if errorlevel 1 (
  call :BOOT_FAIL 29 "не импортируются обязательные зависимости"
  goto END
)
call :LOG "[OK] Локальное окружение готово."

if "%PREPARE_ONLY%"=="1" (
  call :LOG "[OK] Подготовка завершена без запуска приложения."
  set "FINAL_EXIT=0"
  goto END
)
if not exist "%PROJECT_ROOT%\.env" (
  call :BOOT_FAIL 30 "не найден .env; скопируйте .env.example в .env и заполните значения"
  goto END
)

call :LOG "[ЗАПУСК] Запускаем LapBase v%APP_VERSION%..."
"%VENV_PYTHON%" -m app.main
set "APP_EXIT=%ERRORLEVEL%"
if "%APP_EXIT%"=="73" (
  call :APP_FAIL 73 "LapBase уже запущен; второй экземпляр заблокирован до миграций."
  goto END
)
if not "%APP_EXIT%"=="0" (
  call :APP_FAIL %APP_EXIT% "приложение завершилось с ошибкой"
  goto END
)
call :LOG "[OK] LapBase завершён штатно."
set "FINAL_EXIT=0"
goto END

:FIND_MANAGED_PYTHON
set "PYTHON_EXE="
set "PYTHON_PATH_FILE=%STATE_DIR%\python-path.tmp"
del /q "%PYTHON_PATH_FILE%" >nul 2>nul

"%UV_EXE%" python find "%PYTHON_VERSION%" --managed-python >"%PYTHON_PATH_FILE%" 2>>"%BOOT_LOG%"
if errorlevel 1 (
  del /q "%PYTHON_PATH_FILE%" >nul 2>nul
  exit /b 1
)

if not exist "%PYTHON_PATH_FILE%" exit /b 1
set /p "PYTHON_EXE="<"%PYTHON_PATH_FILE%"
del /q "%PYTHON_PATH_FILE%" >nul 2>nul

if not defined PYTHON_EXE exit /b 1
if not exist "%PYTHON_EXE%" exit /b 1
exit /b 0

:CHECK_UV
if not exist "%UV_EXE%" exit /b 1
set "FOUND_UV_VERSION="
for /f "tokens=2" %%V in ('"%UV_EXE%" --version 2^>nul') do set "FOUND_UV_VERSION=%%V"
if /I "%FOUND_UV_VERSION%"=="%UV_VERSION%" exit /b 0
exit /b 1

:LOG
set "MSG=%~1"
echo %MSG%
>>"%BOOT_LOG%" echo %MSG%
exit /b 0

:BOOT_FAIL
set "FINAL_EXIT=%~1"
call :LOG "[ОШИБКА] Не удалось подготовить LapBase."
call :LOG "Что произошло: %~2"
call :LOG "Что можно сделать: проверьте сообщение выше и .env; при повреждении runtime удалите только .runtime и .venv и запустите снова."
call :LOG "Техническая информация: exit code %~1"
call :LOG "Подробный bootstrap-лог: %BOOT_LOG%"
echo.
echo [ДЕТАЛИ] Последние строки bootstrap.log:
powershell -NoProfile -Command "if (Test-Path -LiteralPath '%BOOT_LOG%') { Get-Content -LiteralPath '%BOOT_LOG%' -Encoding UTF8 -Tail 20 }" 2>nul
echo [КОНЕЦ ДЕТАЛЕЙ]
exit /b 0

:APP_FAIL
set "FINAL_EXIT=%~1"
call :LOG "[ОШИБКА] LapBase завершился с ошибкой."
call :LOG "Что произошло: %~2"
if "%~1"=="73" (
  call :LOG "Что можно сделать: остановите уже работающий экземпляр LapBase и повторите запуск."
) else (
  call :LOG "Что можно сделать: проверьте последние строки logs\lapbase.log и сообщение Python выше."
)
call :LOG "Техническая информация: exit code %~1"
call :LOG "Основной лог: %PROJECT_ROOT%\logs\lapbase.log"
echo.
echo [ДЕТАЛИ] Последние строки lapbase.log:
powershell -NoProfile -Command "if (Test-Path -LiteralPath '%PROJECT_ROOT%\logs\lapbase.log') { Get-Content -LiteralPath '%PROJECT_ROOT%\logs\lapbase.log' -Encoding UTF8 -Tail 20 }" 2>nul
echo [КОНЕЦ ДЕТАЛЕЙ]
exit /b 0

:END
if not "%FINAL_EXIT%"=="0" if "%PREPARE_ONLY%"=="0" goto HOLD_ERROR
exit /b %FINAL_EXIT%

:HOLD_ERROR
echo.
echo Окно останется открытым, чтобы ошибка не потерялась.
:CONFIRM_CLOSE
set "CONFIRM_CLOSE="
set /p "CONFIRM_CLOSE=Введите CLOSE и нажмите Enter для закрытия: "
if /I not "%CONFIRM_CLOSE%"=="CLOSE" goto CONFIRM_CLOSE
exit /b %FINAL_EXIT%
