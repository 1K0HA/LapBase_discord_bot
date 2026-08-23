@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

set "FINAL_EXIT=0"
set "RUNTIME_DIR=%CD%\.runtime"
set "UV_BIN_DIR=%RUNTIME_DIR%\uv-bin"
set "UV_EXE=%UV_BIN_DIR%\uv.exe"
set "UV_INSTALL_DIR=%UV_BIN_DIR%"
set "UV_NO_MODIFY_PATH=1"
set "UV_PYTHON_INSTALL_DIR=%RUNTIME_DIR%\python"
set "UV_PYTHON_BIN_DIR=%RUNTIME_DIR%\python-bin"
set "UV_CACHE_DIR=%RUNTIME_DIR%\cache"
set "UV_PYTHON_INSTALL_REGISTRY=0"
set "UV_MANAGED_PYTHON=1"

echo ========================================
echo           LapBase Launcher v1.0.9
echo ========================================
echo.

if not exist ".env" (
    echo [ERROR] File .env was not found.
    echo Copy .env.example to .env and fill it in.
    goto FAIL
)

if not exist "requirements.txt" (
    echo [ERROR] requirements.txt was not found.
    goto FAIL
)

if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"
if not exist "%UV_BIN_DIR%" mkdir "%UV_BIN_DIR%"

if not exist "%UV_EXE%" (
    echo [LapBase] Installing private uv runtime...
    where powershell >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] PowerShell was not found.
        goto FAIL
    )
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if errorlevel 1 (
        echo [ERROR] uv installation failed.
        goto FAIL
    )
)

if not exist "%UV_EXE%" (
    echo [ERROR] uv.exe was not found at: %UV_EXE%
    goto FAIL
)

"%UV_EXE%" --version
if errorlevel 1 goto FAIL

echo [LapBase] Installing/locating private Python 3.14...
"%UV_EXE%" python install 3.14 --managed-python
if errorlevel 1 (
    echo [ERROR] Failed to install private Python 3.14.
    goto FAIL
)

set "PYTHON_314="
for /f "usebackq delims=" %%I in (`"%UV_EXE%" python find 3.14 --managed-python`) do (
    if not defined PYTHON_314 set "PYTHON_314=%%I"
)

if not defined PYTHON_314 (
    echo [ERROR] uv could not locate its managed Python 3.14.
    goto FAIL
)

if not exist "%PYTHON_314%" (
    echo [ERROR] Managed Python executable was not found:
    echo %PYTHON_314%
    goto FAIL
)

echo [LapBase] Managed Python: %PYTHON_314%
"%PYTHON_314%" -c "import sys; print('[LapBase] Managed version:', sys.version); raise SystemExit(0 if sys.version_info[:2] == (3, 14) else 1)"
if errorlevel 1 (
    echo [ERROR] uv returned a Python that is not 3.14.
    goto FAIL
)

rem Always validate the existing venv. Rebuild it if it is not exactly Python 3.14.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,14) else 1)" >nul 2>nul
    if errorlevel 1 (
        echo [LapBase] Existing .venv is not Python 3.14. Rebuilding...
        rmdir /s /q ".venv"
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo [LapBase] Creating .venv from the exact managed Python 3.14 executable...
    "%UV_EXE%" venv ".venv" --python "%PYTHON_314%" --seed
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv.
        goto FAIL
    )
)

echo [LapBase] Verifying .venv Python...
".venv\Scripts\python.exe" -c "import sys; print('[LapBase] Venv Python:', sys.executable); print('[LapBase] Venv version:', sys.version); raise SystemExit(0 if sys.version_info[:2] == (3,14) else 1)"
if errorlevel 1 (
    echo [ERROR] .venv is not running Python 3.14.
    echo Delete .venv and .runtime, then run this BAT again.
    goto FAIL
)

echo [LapBase] Synchronizing dependencies...
"%UV_EXE%" pip install --python ".venv\Scripts\python.exe" -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    goto FAIL
)

echo [LapBase] Verifying dependencies...
".venv\Scripts\python.exe" -c "import aiogram, discord, groq, asyncpg, dotenv; print('[OK] aiogram', aiogram.__version__); print('[OK] discord.py', discord.__version__); print('[OK] groq', groq.__version__); print('[OK] asyncpg', asyncpg.__version__)"
if errorlevel 1 (
    echo [ERROR] Dependency verification failed.
    goto FAIL
)

echo.
echo [LapBase] Starting...
".venv\Scripts\python.exe" -m app.main
set "APP_EXIT=%ERRORLEVEL%"

if not "%APP_EXIT%"=="0" (
    echo.
    echo [ERROR] LapBase exited with code %APP_EXIT%.
    goto FAIL
)

echo.
echo [LapBase] Stopped normally.
set "FINAL_EXIT=0"
goto HOLD

:FAIL
set "FINAL_EXIT=1"
echo.
echo ----------------------------------------
echo LapBase could not start. Read the error above.
echo ----------------------------------------

:HOLD
echo.
echo ========================================
echo This window will stay open.
echo Type CLOSE and press Enter to close it.
echo ========================================

:CONFIRM_CLOSE
set "CONFIRM_CLOSE="
set /p "CONFIRM_CLOSE=Confirm close: "
if /I not "%CONFIRM_CLOSE%"=="CLOSE" (
    echo Window remains open. Type CLOSE to exit.
    goto CONFIRM_CLOSE
)

exit /b %FINAL_EXIT%
